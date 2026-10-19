"""Patient-only native app gateway over the same authorized persistence services."""
from contextlib import asynccontextmanager
import os
from pathlib import Path
import tempfile
import threading
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.concurrency import run_in_threadpool

from backend import services
from backend.config import get_settings
from backend.mobile_auth import SESSION_SECONDS, RateLimiter, SessionRegistry, authenticate_token, decode_token, issue_token, load_secret
from backend.services.privacy import monitoring_status, set_monitoring_consent
from backend.services.reporting import get_patient_report
from ml.vision.tasks import TASKS

LANGUAGE = Literal["English", "Urdu", "Pashto", "Mixed", "Roman Urdu"]
VOICE_TASK = Literal["vowel", "sentence", "natural"]
_upload_lock = threading.Lock()


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class Register(Input):
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    language: LANGUAGE = "English"
    consent: StrictBool


class Login(Input):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class Notes(Input):
    text: str = Field(min_length=3, max_length=5000)


class Activities(Input):
    responses: dict[str, StrictInt]
    other_difficulty: str = Field(default="", max_length=2000)


class ConsentInput(Input):
    acknowledged: StrictBool


class TooLarge(HTTPException):
    def __init__(self):
        # Preserve 413 through FastAPI's request-body exception handling.
        super().__init__(413, "The request exceeds the size limit.")


class PrivateMiddleware:
    def __init__(self, app: ASGIApp, owner: FastAPI):
        self.app, self.owner = app, owner

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        path = scope.get("path", "")
        public = path in {"/health", "/auth/register", "/auth/login"}
        if not public:
            try:
                authorization = headers.get(b"authorization", b"").decode("ascii")
                if not authorization.startswith("Bearer ") or not self.owner.state.secret:
                    raise PermissionError()
                # Authenticate before multipart parsing can spool a recording.
                await run_in_threadpool(authenticate_token, authorization[7:], self.owner.state.secret,
                                        self.owner.state.registry)
            except (PermissionError, UnicodeError):
                return await JSONResponse({"detail": "Please sign in to continue."}, status_code=401,
                    headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"})(scope, receive, send)
        upload = path.endswith("/video") or path.endswith("/audio")
        maximum = min(get_settings().max_upload_bytes, 100 * 1024 * 1024) + 1024 * 1024 if upload else 32 * 1024
        try:
            length = headers.get(b"content-length")
            if length is not None and (not length.isdigit() or int(length) > maximum):
                raise TooLarge()
            total = 0

            async def bounded_receive():
                nonlocal total
                message = await receive()
                if message["type"] == "http.request":
                    total += len(message.get("body", b""))
                    if total > maximum:
                        raise TooLarge()
                return message

            async def private_send(message):
                if message["type"] == "http.response.start":
                    message["headers"] = message.get("headers", []) + [
                        (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                await send(message)

            await self.app(scope, bounded_receive, private_send)
        except TooLarge:
            await JSONResponse({"detail": "The request exceeds the size limit."}, status_code=413,
                headers={"Cache-Control": "no-store"})(scope, receive, send)


def public_user(user: dict) -> dict:
    return {name: user[name] for name in ("id", "full_name", "email", "role", "language", "patient_id")}


def public_session(record: dict) -> dict:
    result = {name: record[name] for name in ("id", "status", "created_at", "updated_at", "completed_at", "modules", "module_revisions")}
    result["files"] = [{name: row[name] for name in ("id", "module", "mime_type", "size_bytes", "created_at")}
                       for row in record["files"]]
    result["has_report"] = bool(record["reports"])
    return result


def accepted(result: dict) -> bool:
    quality = result.get("quality", {})
    return (result.get("status") in {"accepted", "completed", "ACCEPT"}
            and isinstance(quality, dict) and quality.get("accepted") is not False
            and quality.get("decision") not in {"REPEAT", "REJECT"}
            and (quality.get("accepted") is True or quality.get("decision") == "ACCEPT"))


def create_app(*, secret: bytes | None = None, initialize_database: bool = True,
               rate_limit: bool = True, registry_path: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        if initialize_database:
            services.init_db()
        application.state.secret = secret or load_secret()
        application.state.registry = SessionRegistry(registry_path or get_settings().storage_root / "mobile-api-sessions.sqlite3")
        yield

    application = FastAPI(title="ParkinSense PK Patient API", version="1.0.0", lifespan=lifespan,
                          docs_url=None, redoc_url=None, openapi_url=None)
    application.state.secret = secret
    application.state.limiter = RateLimiter()
    application.add_middleware(PrivateMiddleware, owner=application)

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request, _error):
        # Pydantic's default errors echo rejected input, including passwords.
        return JSONResponse({"detail": "Check the required fields and try again."}, status_code=422)

    @application.exception_handler(PermissionError)
    async def permission_error(_request, _error):
        return JSONResponse({"detail": "This action is unavailable for your account or monitoring consent."}, status_code=403)

    @application.exception_handler(ValueError)
    async def value_error(_request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @application.exception_handler(LookupError)
    async def missing_error(_request, _error):
        return JSONResponse({"detail": "The requested record is unavailable."}, status_code=404)

    def actor(request: Request) -> dict:
        authorization = request.headers.get("authorization", "")
        try:
            if not authorization.startswith("Bearer ") or not request.app.state.secret:
                raise PermissionError()
            return authenticate_token(authorization[7:], request.app.state.secret, request.app.state.registry)
        except PermissionError:
            raise HTTPException(401, "Your session has expired. Please sign in again.",
                                headers={"WWW-Authenticate": "Bearer"}) from None

    Actor = Annotated[dict, Depends(actor)]

    def throttle(request, operation):
        identity = (request.client.host if request.client else "unknown") + ":" + operation
        if rate_limit and not application.state.limiter.check(identity, limit=6 if operation == "register" else 10):
            raise HTTPException(429, "Too many attempts. Wait one minute and try again.", headers={"Retry-After": "60"})

    def token_response(user):
        token = issue_token(user, application.state.secret)
        application.state.registry.issue(decode_token(token, application.state.secret))
        return {"access_token": token, "token_type": "bearer",
                "expires_in": SESSION_SECONDS, "user": public_user(user)}

    @application.get("/health")
    def health():
        return {"status": "ok", "application": "ParkinSense PK"}

    @application.post("/auth/register", status_code=201)
    def register(body: Register, request: Request):
        throttle(request, "register")
        user = services.register_patient(body.full_name, body.email, body.password, body.language, body.consent)
        # Authenticate after atomic registration to capture the current security revision.
        return token_response(services.authenticate(user["email"], body.password))

    @application.post("/auth/login")
    def login(body: Login, request: Request):
        throttle(request, "login")
        try:
            user = services.authenticate(body.email, body.password)
            if user["role"] != "patient":
                raise PermissionError()
            return token_response(user)
        except PermissionError:
            raise HTTPException(401, "Email or password is incorrect, or the patient account is inactive.") from None

    @application.post("/auth/logout")
    def logout(user: Actor):
        application.state.registry.logout(user)
        return {"signed_out": True}

    @application.get("/profile")
    def profile(user: Actor):
        return public_user(user) | {"monitoring_consent": monitoring_status(user["id"])}

    @application.post("/profile/consent")
    def consent(body: ConsentInput, user: Actor):
        set_monitoring_consent(user["id"], acknowledged=body.acknowledged)
        return monitoring_status(user["id"])

    @application.get("/sessions")
    def history(user: Actor):
        return [public_session(record) for record in services.list_assessments(user["id"])]

    @application.post("/sessions", status_code=201)
    def start(user: Actor):
        return public_session(services.create_assessment(user["id"]))

    @application.get("/sessions/{session_id}")
    def session(session_id: str, user: Actor):
        return public_session(services.get_assessment(user["id"], session_id))

    @application.post("/sessions/{session_id}/notes")
    def notes(session_id: str, body: Notes, user: Actor):
        from ml.nlp import analyze_text
        services.ensure_assessment_writable(user["id"], session_id)
        result = analyze_text(body.text, user["language"])
        return public_session(services.save_module(user["id"], session_id, "nlp", result))

    @application.post("/sessions/{session_id}/activities")
    def activities(session_id: str, body: Activities, user: Actor):
        from ml.tabular.adl import analyze_adl
        services.ensure_assessment_writable(user["id"], session_id)
        result = analyze_adl(body.responses | {"other_difficulty": body.other_difficulty})
        return public_session(services.save_module(user["id"], session_id, "adl", result))

    def analyze_upload(user, session_id, file, task, media_kind):
        # Authorize before expensive decoding and before creating any private file.
        services.ensure_assessment_writable(user["id"], session_id)
        if media_kind == "video" and task not in TASKS:
            raise ValueError("Choose a supported movement task.")
        extension = Path(file.filename or "").suffix.lower()
        if (media_kind == "video" and extension not in {".mp4", ".mov", ".avi", ".mkv"}) or (media_kind == "audio" and extension != ".wav"):
            raise ValueError("Upload an MP4 movement recording or a WAV voice recording.")
        limit = min(get_settings().max_upload_bytes, (72 if media_kind == "audio" else 100) * 1024 * 1024)
        if not _upload_lock.acquire(blocking=False):
            raise HTTPException(429, "A recording is being analyzed. Try again when it finishes.", headers={"Retry-After": "5"})
        try:
            root = get_settings().storage_root
            if root.is_symlink():
                raise ValueError("Private storage root cannot be a symlink.")
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            root.chmod(0o700)
            with tempfile.TemporaryDirectory(prefix="mobile-analysis-", dir=root) as directory:
                path = Path(directory) / ("recording" + extension)
                size = 0
                with path.open("xb") as handle:
                    os.chmod(path, 0o600)
                    while data := file.file.read(1024 * 1024):
                        size += len(data)
                        if size > limit:
                            raise HTTPException(413, "Trim the recording to fit the upload limit.")
                        handle.write(data)
                if not size:
                    raise ValueError("Record a clip before uploading.")
                if media_kind == "video":
                    from ml.vision.pipeline import analyze_video
                    result = analyze_video(path, task)
                    module = task
                else:
                    from ml.audio import analyze_audio
                    result = analyze_audio(path, user["language"], task)
                    result["voice_task"] = task
                    module = "voice_" + task
                # Decoder errors can include its temporary path. Keep paths private.
                def sanitize(value):
                    if isinstance(value, str):
                        return value.replace(str(path), "recording").replace(str(directory), "temporary recording")
                    if isinstance(value, dict):
                        return {name: sanitize(item) for name, item in value.items()}
                    if isinstance(value, list):
                        return [sanitize(item) for item in value]
                    return value
                result = sanitize(result)
                is_accepted = accepted(result)
                if is_accepted:
                    # Recheck authorization/consent/draft after analysis in store/save services.
                    with path.open("rb") as handle:
                        key = services.store_upload(user["id"], session_id, module, path.name, handle)
                    services.save_module(user["id"], session_id, module, result, media_path=key)
                return {"accepted": is_accepted, "result": result,
                        "session": public_session(services.get_assessment(user["id"], session_id))}
        finally:
            file.file.close()
            _upload_lock.release()

    @application.post("/sessions/{session_id}/video")
    def video(session_id: str, user: Actor, file: UploadFile = File(), task: str = Form()):
        return analyze_upload(user, session_id, file, task, "video")

    @application.post("/sessions/{session_id}/audio")
    def audio(session_id: str, user: Actor, file: UploadFile = File(), task: VOICE_TASK = Form("natural")):
        return analyze_upload(user, session_id, file, task, "audio")

    @application.post("/sessions/{session_id}/complete")
    def complete(session_id: str, user: Actor):
        return public_session(services.finish_assessment(user["id"], session_id))

    @application.get("/sessions/{session_id}/report")
    def report(session_id: str, user: Actor):
        row = get_patient_report(user["id"], session_id)
        if row is None:
            raise HTTPException(404, "Save an accepted recording, activity response, or note to generate a report.")
        content = row["content"]
        keys = ("patient_summary", "sections", "comparison_note", "coverage_note", "generated_at", "generated_at_local", "limitations", "accepted", "assessment_status")
        return {name: content.get(name) for name in keys} | {"outdated": row.get("outdated", False)}

    @application.get("/sessions/{session_id}/media/{file_id}")
    def media(session_id: str, file_id: str, user: Actor):
        record = services.get_assessment(user["id"], session_id)
        if not monitoring_status(user["id"])["active"]:
            raise PermissionError("Current monitoring consent is required.")
        row = next((item for item in record["files"] if item["id"] == file_id), None)
        if row is None:
            raise LookupError("Media is unavailable.")
        path = services.get_media_path(user["id"], session_id, row["storage_key"])
        return FileResponse(path, media_type=row["mime_type"], filename="recording" + Path(path).suffix)

    return application


app = create_app()
