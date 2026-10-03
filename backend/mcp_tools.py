"""Optional typed MCP facade over ordinary authorized services.

HTTP server binds only to localhost. A high-entropy bearer token is mapped to
one server-configured actor; callers cannot supply an actor or arbitrary path.
No raw media, SQL, model-loading paths, cloud services or external LLMs are tools.
"""
from __future__ import annotations

import os
import secrets
from contextlib import contextmanager
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend import services
from ml.audio import analyze_audio
from ml.inference import build_report
from ml.inference.evidence import ApprovedKnowledgeBase
from ml.multimodal import fuse_results
from ml.nlp import analyze_text

Language = Literal["english", "urdu", "pashto", "roman urdu", "mixed"]
GaitTask = Literal["gait", "turning"]
HandTask = Literal["finger_left", "finger_right", "hand_open_close", "grasp", "object_transfer"]
BodyTask = Literal["sit_to_stand", "reach"]


class AssessmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessment_id: UUID


class AudioInput(AssessmentInput):
    file_id: UUID
    language: Language = "english"
    task: Literal["natural", "vowel", "sentence"] = "natural"


class NLPInput(AssessmentInput):
    text: str = Field(min_length=3, max_length=5000)
    language: Language = "english"


def _structured(value):
    """Return derived measurements; exclude raw prose/media and storage details."""
    omitted = {"storage_key", "transcript", "text", "source_excerpt", "source_text", "other_difficulty",
               "review_note", "content", "landmark_frames", "landmarks", "frames", "curves", "raw_media", "raw_audio", "raw_video"}
    if isinstance(value, dict):
        return {key: _structured(item) for key, item in value.items() if key not in omitted}
    if isinstance(value, list):
        return [_structured(item) for item in value]
    return value


class AuthorizedTools:
    """Construct only from an authenticated server-side session/identity binding."""
    def __init__(self, actor_id: UUID | str, knowledge_base: ApprovedKnowledgeBase | None = None):
        self.actor_id = str(UUID(str(actor_id)))
        self.knowledge_base = knowledge_base or ApprovedKnowledgeBase()

    @contextmanager
    def _audit(self, tool: str, assessment_id: str | None = None):
        try:
            # Active account and ownership/link checked before any tool work.
            if assessment_id:
                services.get_assessment(self.actor_id, assessment_id)
            else:
                services.get_user(self.actor_id)
            yield
            services.record_tool_audit(self.actor_id, tool, assessment_id, success=True)
        except Exception:
            # Log the denial without leaking an inaccessible resource identifier.
            try:
                services.record_tool_audit(self.actor_id, tool, success=False)
            except (PermissionError, ValueError, LookupError):
                pass
            raise

    def get_patient_timeline(self, patient_id: UUID | None = None) -> list[dict]:
        with self._audit("get_patient_timeline"):
            return [_structured(item) for item in services.get_timeline(self.actor_id, str(patient_id) if patient_id else None)]

    def get_assessment(self, assessment_id: UUID) -> dict:
        assessment_id = str(UUID(str(assessment_id)))
        with self._audit("get_assessment", assessment_id):
            return _structured(services.get_assessment(self.actor_id, assessment_id))

    def _file(self, assessment_id: str, file_id: UUID, module: str) -> tuple[str, str]:
        # Reject closed/abandoned/unconsented assessments before expensive decode.
        assessment = services.ensure_assessment_writable(self.actor_id, assessment_id)
        record = next((item for item in assessment["files"] if item["id"] == str(file_id)), None)
        if record is None:
            raise LookupError("Recording does not belong to this assessment.")
        aliases = {"voice", "speech", "audio", module} if module.startswith("voice_") else {module}
        if record["module"] not in aliases:
            raise ValueError("Select a recording saved for this assessment task.")
        return (services.get_media_path(self.actor_id, assessment_id, record["storage_key"]), record["storage_key"])

    def _run_movement(self, assessment_id: UUID, file_id: UUID, task: str, tool: str) -> dict:
        from ml.vision.pipeline import analyze_video
        assessment_id = str(UUID(str(assessment_id)))
        with self._audit(tool, assessment_id):
            path, key = self._file(assessment_id, file_id, task)
            result = analyze_video(path, task)
            services.save_module(self.actor_id, assessment_id, task, result, media_path=key)
            return _structured(result)

    def run_gait_analysis(self, assessment_id: UUID, file_id: UUID, task: GaitTask = "gait") -> dict:
        if task not in {"gait", "turning"}:
            raise ValueError("Unsupported gait task.")
        return self._run_movement(assessment_id, file_id, task, "run_gait_analysis")

    def run_hand_analysis(self, assessment_id: UUID, file_id: UUID, task: HandTask) -> dict:
        if task not in {"finger_left", "finger_right", "hand_open_close", "grasp", "object_transfer"}:
            raise ValueError("Unsupported hand task.")
        return self._run_movement(assessment_id, file_id, task, "run_hand_analysis")

    def run_body_analysis(self, assessment_id: UUID, file_id: UUID, task: BodyTask) -> dict:
        if task not in {"sit_to_stand", "reach"}:
            raise ValueError("Unsupported transfer/reach task.")
        return self._run_movement(assessment_id, file_id, task, "run_body_analysis")

    def run_audio_analysis(self, request: AudioInput) -> dict:
        assessment_id = str(request.assessment_id)
        with self._audit("run_audio_analysis", assessment_id):
            module = f"voice_{request.task}"
            path, key = self._file(assessment_id, request.file_id, module)
            result = analyze_audio(path, request.language, request.task)
            services.save_module(self.actor_id, assessment_id, module, result, media_path=key)
            return _structured(result)

    def run_nlp_analysis(self, request: NLPInput) -> dict:
        assessment_id = str(request.assessment_id)
        with self._audit("run_nlp_analysis", assessment_id):
            services.ensure_assessment_writable(self.actor_id, assessment_id)
            result = analyze_text(request.text, request.language)
            services.save_module(self.actor_id, assessment_id, "nlp", result)
            return _structured(result)

    def run_multimodal_inference(self, assessment_id: UUID) -> dict:
        assessment_id = str(UUID(str(assessment_id)))
        with self._audit("run_multimodal_inference", assessment_id):
            return fuse_results(services.get_assessment(self.actor_id, assessment_id)["modules"])

    def _report(self, assessment_id: str, language: Language = "english") -> dict:
        assessment = services.get_assessment(self.actor_id, assessment_id)
        history = [item for item in services.get_timeline(self.actor_id, assessment["patient_id"])
                   if item["id"] != assessment_id and item["created_at"] < assessment["created_at"]]
        return build_report(assessment["modules"], history, language, self.knowledge_base)

    def get_explanation(self, assessment_id: UUID) -> dict:
        assessment_id = str(UUID(str(assessment_id)))
        with self._audit("get_explanation", assessment_id):
            return self._report(assessment_id)["explanation"]

    def retrieve_approved_evidence(self, query: str, limit: int = 3) -> list[dict]:
        with self._audit("retrieve_approved_evidence"):
            return self.knowledge_base.retrieve(query, limit)

    def save_report(self, assessment_id: UUID, language: Language = "english") -> dict:
        assessment_id = str(UUID(str(assessment_id)))
        with self._audit("save_report", assessment_id):
            # Recompute from authorized saved measurements, never accept caller prose.
            return services.save_report(self.actor_id, assessment_id, self._report(assessment_id, language))


def create_server():
    """Optional local HTTP MCP server with fixed-actor bearer authentication."""
    from mcp.server.fastmcp import FastMCP
    from mcp.server.auth.provider import AccessToken
    from mcp.server.auth.settings import AuthSettings
    from pydantic import AnyHttpUrl

    actor_id = os.environ.get("PARKINSENSE_MCP_ACTOR_ID", "")
    token = os.environ.get("PARKINSENSE_MCP_TOKEN", "")
    if not actor_id or len(token) < 32:
        raise ValueError("Configure an active PARKINSENSE_MCP_ACTOR_ID and a random PARKINSENSE_MCP_TOKEN of at least 32 characters.")
    facade = AuthorizedTools(actor_id)
    # Validate the configured actor before starting a server.
    services.record_tool_audit(facade.actor_id, "server_started")
    resource_url = "http://127.0.0.1:8766/"

    class FixedActorVerifier:
        async def verify_token(self, supplied: str):
            if not secrets.compare_digest(token, supplied):
                return None
            return AccessToken(token=supplied, client_id=facade.actor_id, subject=facade.actor_id,
                               scopes=["patient_tools"], resource=resource_url)

    server = FastMCP("ParkinSense-PK authorized services", host="127.0.0.1", port=8766,
                     token_verifier=FixedActorVerifier(),
                     auth=AuthSettings(issuer_url=AnyHttpUrl(resource_url), resource_server_url=AnyHttpUrl(resource_url),
                                       required_scopes=["patient_tools"], validate_token_resource=True))
    for name in ["get_patient_timeline", "get_assessment", "run_gait_analysis", "run_hand_analysis", "run_body_analysis",
                 "run_audio_analysis", "run_nlp_analysis", "run_multimodal_inference", "get_explanation", "retrieve_approved_evidence", "save_report"]:
        server.tool(name=name)(getattr(facade, name))
    return server


if __name__ == "__main__":
    create_server().run(transport="streamable-http")
