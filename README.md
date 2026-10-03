# ParkinSense-PK

Streamlit application for patient and clinician longitudinal functional monitoring. Patient, clinician and administrator are the only roles. The source roadmap is preserved in `docs/implementation-roadmap.md`; the implementation audit is in `docs/roadmap-analysis.md`.

This is a working development implementation, not a clinically validated release. It records real task measurements and self-reports, supports quality-gated 3D movement review, and compares accepted recordings over time. Clinical predictions, autonomous diagnosis and medication recommendations are not provided. The professional 3D and human care upgrade is documented in `docs/professional-3d-upgrade.md`.

Every analysis module now includes a native-unit **3D statistical review**, automatic printable patient reports after saving, and numbered fault guidance. The workflow, sources and data rules are described in `docs/statistics-reports-guidance.md`.

Live movement capture also has task-focused depth-styled joint lines on the camera and an adjacent **live world-XYZ 3D view**, with short fading trails and automatic clearing when tracking is lost. Both displays start enabled. Setup, controls and geometry rules are in `docs/live-tracking.md`.

## Run locally

Use Python 3.11 in the project environment. The system Python is not changed.

```bash
cd "/home/shaiby/Parkinsense PK"
uv python install 3.11
uv sync --group dev
uv run python scripts/setup_local.py
docker compose --env-file .env -f infra/compose.yaml -p parkinsense_pk up -d --wait db
uv run python scripts/download_landmark_models.py
uv run python scripts/secure_media_server.py  # Separate terminal; keep it running.
uv run streamlit run app/Home.py --server.address 127.0.0.1
```

Open [the local app](http://127.0.0.1:8501). The current workspace already has its private `.env`, healthy PostgreSQL container and downloaded landmark models. You can register your own patient account in the application.

To create the **first administrator**, run this interactive command and choose your own credentials:

```bash
uv run python scripts/bootstrap_admin.py
```

There are no default administrator credentials. Administrators create clinician accounts and assign patients. Only a patient and their linked clinicians can read that patient's assessments or recordings. Administrators manage accounts and assignments without receiving assessment/media access.

After setup, `bash scripts/run_local.sh` starts PostgreSQL and the app. Stop only this project's database with:

```bash
docker compose --env-file .env -f infra/compose.yaml -p parkinsense_pk stop db
```

The Docker volume persists when the container stops. Keep `.env` safe: its generated database password is needed to reopen that database. Regenerating `.env` does not change a password in an existing database volume.

## Patient workflow

1. Register with monitoring consent, or log in.
2. Open **Start Assessment**, then start a new visit or resume a saved draft.
3. Choose **Walking / Gait**, **Hand / Finger**, **Sit-to-Stand**, **Reach / Grasp**, **Voice / Speech**, or **Daily Activities**.
4. Movement tasks accept either live camera capture or uploaded MP4/MOV/AVI/MKV. Select the task before recording. In **Live Camera**, press camera **START** to see focused joint lines and the rotating 3D preview; choose **Start recording**, then **Finish & analyze**. All final movement measurements use the same OpenCV/MediaPipe pipeline.
5. Review numbered quality guidance, the **3D Movement Studio**, and **3D statistical review**. Rotate the graph, choose a viewpoint/unit, inspect exact values, or compare compatible visits. Only accepted results can be saved through the patient UI.
6. Saving an accepted movement, voice, description or daily-activity result updates the **automatic patient report** in the same transaction. Complete the visit, then review **My Results**, **Progress** and **Reports**. Download a printable HTML report, or open it in a browser and use Print → Save as PDF.

An unsuccessful attempt has its own downloadable recording-quality report with step-by-step instructions. A failed replacement does not overwrite an earlier accepted saved result. The latest attempt and the saved visit report are labelled separately. Older assessments can generate a patient report from the Reports page without repeating the analysis.

Each movement clip is limited to **45 seconds and 100 MB**. Gait/tapping/open-close need at least 5 seconds; turning/transfer/reach/grasp need at least 3 seconds. Capture is written to disk rather than retaining video frames in memory. Camera gaps and insufficient unique camera frame rate require a repeat. No synthetic skeleton is substituted when a person or hand is missing.

The microphone widget records WAV. Sustained vowel, fixed sentence and natural speech are saved as separate tasks. Audio processing checks silence/clipping, resamples a working copy, and extracts energy, MFCC, spectrum, pause and optional periodicity/pitch estimates. Speech recognition is unconfigured; enter a reviewed transcript for Urdu, Pashto, English or Roman Urdu keyword analysis. This rule-based language pathway is limited and requires review.

The daily-activity questionnaire uses custom 0–4 self-report items. It is explicitly labelled **unvalidated** and is not a replacement for a clinician-selected instrument.

**My Care** adds explicit daily wellbeing check-ins, optional falls/context, personal goals and clinician-authored follow-up. A planned review date is a care note rather than an appointment booking. These human-authored records remain separate from automated task features and diagnosis. Assigned clinicians can read them and write follow-up from **Patient follow-up**, including before a patient has recorded any assessments.

The studio uses estimated world XYZ in meters around the body hips or hand center. Missing world data never becomes a pseudo-3D replay. A single camera does not supply calibrated global walking distance, floor contact or a wrist route through the room. Meshes are stylized shapes around observed joints. Statistical graphs use true 3D lines, mesh bars or visit markers; their third axis is a measured value in a single unit. Missing/rejected data stay blank, and the graph does not interpolate new patient observations.

## Data and security

- SQLAlchemy creates the PostgreSQL schema for accounts, consent, linked care teams, assessments, module results, media references, clinical measurements, ADL, daily check-ins, personal goals, care plans, model runs/outputs, explanations, reports and audit events.
- Passwords use salted scrypt hashing; public registration always creates a patient.
- The authenticated identity remains server-side in Streamlit session state. Every service repeats ownership/link checks; navigation visibility is not the authorization mechanism.
- Media use UUID paths under ignored `data/private`, with owner-only directories and files. Filenames, arbitrary paths and SQL are not exposed as MCP inputs.
- Result/file/model-output writes use transactions and uploads are size-bounded. Audit details omit raw recordings, names, transcripts and passwords.
- Assessment times are stored in UTC and displayed in Pakistan time.
- `.env`, patient media, processed features and model weights are excluded from Git. File permissions are **not encryption at rest**; encrypted disks/storage and tested backups are deployment prerequisites.

Recordings and report/replay downloads now use a separate private gateway on loopback port 8503. Temporary opaque links repeat patient/care-team/consent checks on every request and expire after three minutes. Logout, password reset and monitoring withdrawal revoke access. Private recording/export bytes never use Streamlit's public media download storage. Keep both local servers running; `scripts/run_local.sh` starts them together. Remote phones require a trusted HTTPS media origin and HTTPS app URL configured by an operator.

Account recovery uses administrator-issued, identity-verified, expiring single-use codes; public recovery accepts the code and a confirmed new password. No recovery emails are sent automatically. Password reset invalidates previous sessions. Encrypted database/media snapshots and safe isolated restore drills have executable CLI tools; backup scheduling/off-site custody and the clinic's retention policy remain operator responsibilities. See [production readiness](docs/production-readiness.md).

Patients can withdraw/resume monitoring and request access, a full export or erasure in **Data & privacy**. Withdrawal denies new monitoring writes/media links; existing records remain stored pending an operator review. The admin request queue tracks that review and does not silently delete or export health data.

## Evaluation and clinic feasibility

Clinicians now have **Measurement validation** and **Clinic pilot** pages. Validation protocols pin a task, native-unit metric, extractor version, independent reference method and planned targets. Cases require actual stored recording provenance and separate patient participation. Accuracy/repeatability and camera/lighting coverage use actual entered evidence, with an actual-data 3D comparison. An offline manifest includes failed capture attempts and checks local participant split overlap. See [real recording validation](docs/real-world-validation.md).

Clinic pilots track planned/attempted/completed tasks, usable/all recording attempts, paired baseline/app review times, patient-reported usability and clinic payment intentions. Patient participation is separate and optional; denominators and unknown outcomes remain visible. Payment intent is a reported discussion, not a transaction. See [clinic pilot protocol](docs/clinic-pilot.md).

Patient task instructions, recording controls and all 33 fault-guidance codes have English, Urdu and Roman Urdu copy. Urdu prose uses native script and RTL; mobile controls wrap, stack and have larger touch targets. Phones can use front/rear lens preferences or upload a normal-speed clip from their camera app. Physical-device and bilingual clinician review remain necessary; see [patient usability](docs/patient-usability.md).

SQLite requires explicit `PARKINSENSE_ALLOW_SQLITE=1` and is intended only for isolated tests/development. Normal startup uses PostgreSQL. `create_all` initializes a new schema; existing production schema upgrades need a reviewed migration process.

## Intelligence status

Baseline comparisons use the first accepted result for the same task, method and voice language. Abandoned visits and failed quality checks do not contribute. Trends describe measured changes; they do not label improvement or deterioration.

Fusion currently reports **available/missing measurements**, not a learned multimodal score. Reports use fixed, safe templates and auditable quality → analysis → history → evidence → safety → report stages. The evidence library is empty until approved versioned documents are supplied. No external LLM or paid provider receives patient media.

Developer-only training and trusted artifact inference are available separately. To export quality-gated numeric features, run `uv run python scripts/export_features.py --filename visit-features.parquet` and authenticate as the patient, or add `--patient-id UUID` as an assigned clinician. The export stays in ignored `data/features` with private permissions, preserves missing modalities, and excludes names, transcripts and raw landmarks. UUIDs are pseudonyms, not proof of anonymization. Reference labels must be added through an approved clinical data process.

Supply an approved, deidentified feature CSV with repeated `patient_id`, numeric feature columns and an appropriate clinical reference target:

```bash
uv run python scripts/train_baseline.py /path/to/approved-features.csv \
  --output models/artifacts/baseline \
  --features feature_one feature_two \
  --target reference_target --patient-column patient_id \
  --kind regression --model ridge --data-origin deidentified_clinical \
  --target-description "Describe the reference measure and provenance"
```

The CLI supports logistic regression/random forest classification and ridge/random forest regression. It uses patient-disjoint train/validation/test groups, training-only preprocessing, validation-set probability calibration for classification, held-out metrics, patient bootstrap metric intervals and permutation importance. Its manifest records data/artifact checksums, group splits and **clinical_validated=false**. At least 12 distinct patients are required by the software; that threshold does not establish adequate statistical power. No dataset was supplied, so no genuine clinical baseline model has been trained or connected to patient reports. Synthetic datasets in unit tests exercise software only.

Heavy audio/pose/attention/temporal networks, ASR and LLM reporting remain unconfigured. Do remote GPU training only after the supervised baseline and dataset protocol are established.

## Optional MCP

Ordinary services work independently of MCP. The optional local server offers typed authorized timeline, assessment, task-analysis, measured fusion, explanation, evidence and report tools. It uses a high-entropy bearer token bound to a single server-configured actor; clients cannot choose another identity.

```bash
uv sync --group dev --group mcp
# Set PARKINSENSE_MCP_ACTOR_ID and PARKINSENSE_MCP_TOKEN privately.
uv run --group mcp python -m backend.mcp_tools
```

It binds only to `127.0.0.1:8766` and does not start automatically. See `backend/mcp_tools.py` for the tool schemas. Use one server identity per actor and do not expose this development server publicly.

## Validation

```bash
uv run --group dev --group mcp pytest -q
PARKINSENSE_RUN_MODEL_TESTS=1 uv run --group dev --group mcp pytest tests/test_vision.py -q
uv run --group dev ruff check .
```

Tests isolate their database and storage. **339 tests passed with real model smoke tests enabled; three PostgreSQL-only races passed separately**. New checks cover participant-balanced accuracy, split leakage, consent/source provenance, private downloads, Urdu/mobile instructions, recovery replay/session invalidation, actual HTTP ranges and encrypted DB/media restoration. Real model smoke tests confirm model loading and rejection of blank clips; they do not establish accuracy on clinical recordings. Browser checks use a separate synthetic test database; no patient history or default account was seeded into the normal app database. See `docs/verification.md` for evidence and limits.

Camera/microphone permission and successful recording on the user's hardware still require an actual user trial. HTTPS and suitable private STUN/TURN configuration are needed for remote capture. Public deployment, clinical validation and production hardening are not complete.

The full implementation decisions and outstanding acceptance criteria are in `docs/roadmap-analysis.md`.
# Parkinsense_PK
