# ParkinSense-PK — roadmap analysis and implementation audit

Audit date: 3 October 2026, Pakistan time. Source: `docs/implementation-roadmap.md`, copied without modifying the supplied document.

## Overall finding

The roadmap describes a plausible staged functional-monitoring application, but it combines software implementation with clinical evidence generation and a later production deployment. Those are different acceptance gates. The repository was empty at the start; this implementation builds the local application, real measurement pipelines and controlled extension points. It does not claim the entire clinically validated roadmap is complete.

The implementation follows the recommended early order: isolated Python → Git/dependencies → dark Streamlit shell → registration/roles → PostgreSQL/private storage → modular tasks → shared live/upload CV → estimated 3D → quality checks → voice/ADL/history → measured fusion/reporting. Later research/model work is kept outside app navigation. There is no researcher role or research menu.

## Decisions made after reviewing the complete document

1. **Patient monitoring is the product scope.** Diagnosis, medication changes and unvalidated clinical scores are excluded from the implemented outputs. Model-derived geometric and acoustic values are identified as measurements or proxies.
2. **The modular hub takes precedence over the earlier sequential diagram.** Patients can complete individual tasks and resume draft visits. Completing a visit does not require every modality; reports explicitly show missing inputs.
3. **Account permissions are enforced in Python services.** Patients register themselves; administrators create staff. Only linked clinicians review patient data. Changing session state or entering a page URL is not sufficient to grant patient access.
4. **Use the current MediaPipe Tasks API.** Models are small official downloads with recorded checksums. Legacy `mp.solutions` examples are not assumed compatible with the installed version. Both capture sources converge on a single final analysis function.
5. **Approximate 3D is not an absolute walking path.** The viewer uses aspect-corrected image coordinates with relative depth; world landmarks are estimated and centered on the body/hand. Foot/wrist/hip trajectories are camera-space proxies, with fixed animation axes. No calibrated distance or laboratory motion-capture claim is made.
6. **Task recognition is limited.** Rules check landmark visibility and movement consistency. They cannot establish successful object contact, clinical freezing, failed transfers, safe gait, or true completion of every task. Grasp/transfer results explicitly disclose absent object detection; clinician review is still needed.
7. **Live timing is checked.** Disk capture normalizes playback fps, but duplicated frames cannot count as adequate camera sampling. Frame gaps or low unique camera fps invalidate a live recording before accepted measurements.
8. **Quality rejection precedes measurements.** Corrupt files, unsuitable metadata, dark/blurred clips, missing landmarks and inadequate movement return actionable feedback and no features. A missing model produces an unavailable error; no example skeleton is substituted.
9. **Voice tasks are distinct.** Vowel, sentence and natural speech have separate stored module IDs. Baseline comparison also checks method and language. Audio activity and periodicity are signal proxies; no unsupported jitter/shimmer or speech-rate estimate is reported.
10. **Manual reviewed text is the current multilingual path.** Urdu, Pashto, Roman Urdu and English dictionaries retain self-report provenance and heuristic uncertainty. Automatic ASR, language detection and multilingual embeddings are not implemented as functioning models.
11. **The custom ADL form is labelled correctly.** It gathers complete bounded responses atomically. Selection/licensing/translation of a validated instrument belongs with the clinical team.
12. **Patient-independent splits are necessary but insufficient validation.** The training CLI prevents patient overlap and fits preprocessing on training data. It records calibration and metrics. The test suite's synthetic fixtures are not evidence of clinical model performance.
13. **Missing modality coverage is usable now.** Without supplied trained weights, fusion returns only measurements and coverage. Missing data are not filled with normal scores or synthetic predictions.
14. **Reports remain deterministic until grounded GenAI is configured.** Fixed templates consume structured accepted measurements. Empty approved evidence is explicit. The auditable stages are ordinary deterministic services, not a claim of seven autonomous LLM agents.
15. **MCP follows working services.** The optional server uses typed IDs, ownership checks, a fixed authenticated actor and audit logs. It has no arbitrary SQL or patient-file path tool and is not exposed publicly.
16. **Local delivery is different from production.** PostgreSQL, Streamlit and the private media gateway bind locally. Expiring revocable media/export links, password recovery/session invalidation, encrypted backups and isolated restore drills are implemented and tested. Patients can withdraw monitoring and file data requests. HTTPS, off-site backups, key custody, a retention policy, stronger operator identity controls and clinical operating procedures remain deployment gates.

## Phase-by-phase implementation

Status meanings: **Implemented** = working code exists; **Verified** = meaningful automated or local smoke checks ran; **Partial** = a defined subset exists and its gap is named; **Requires input** = cannot honestly complete without clinical data, approved content, trained artifacts or deployment decisions.

| Phase | Result and evidence | Remaining acceptance gate |
|---|---|---|
| 1 Python 3.11 | Verified `.venv` on CPython 3.11.15 using uv | None for local runtime |
| 2 Git and private exclusions | Initialized main; ignore rules exclude credentials, media, generated data and weights | User chooses remote/backups |
| 3 Structure | App, backend, ML, docs, scripts, tests, infra and model directories | None; callable role navigation replaces duplicate numbered page scripts |
| 4 Dependencies | Installed CPU-focused stack; `uv.lock` and exported requirements | GPU libraries stay optional until needed |
| 5 Configuration | Dark responsive Streamlit configuration; upload cap and XSRF enabled | Real mobile device usability trial |
| 6 Launch | Local server health and login page verified | None for local launch |
| 7 Registration | Verified identity validation, consent, password hashing, patient-only creation | Clinical consent policy/version review |
| 8 Login | Verified login/logout, inactive account denial, role routes, admin-verified single-use recovery and password session invalidation | MFA, external notification and operator identity policy |
| 9 Session state | User/role/current patient/visit/step; DB holds permanent records; resume tested | Production expiry/session operating policy |
| 10 PostgreSQL | All fourteen core tables plus module_results; test suite ran on PostgreSQL | Reviewed migrations for schema upgrades |
| 11 Storage | UUID hierarchy, private modes, revocable authorized streaming, encrypted snapshots and isolated restore testing | Source disk encryption, approved retention, scheduled off-site backups and production restore procedure |
| 12 Patient home | Visit count, resume/start, recent history and profile | Clinical usability review |
| 13 Modular hub | Independent task pages, saved drafts and repeats | User acceptance on real tasks |
| 13A Video upload | MP4/MOV/AVI/MKV signatures, metadata and streaming decoding | Codec/camera matrix with representative recordings |
| 14 Camera | WebRTC overlay, disk capture, timers/visibility/lighting and timing guard; browser panel observed actively processing frames | Accepted real task recording not verified |
| 14A Separate pathways | Task specification controls landmark kind, joints, side, activity rules and feature extractor | Clinical task accuracy/threshold validation |
| 15 Walking/turning | Instructions, timestamps, pose results and dedicated tasks | Authorized full-body recordings needed |
| 16 Pose | Real official model loading/inference; knee/arm/ankle/cadence proxies | Accuracy against reference capture |
| 17 Tapping | Separate anatomical sides; amplitude/rhythm/cycle proxies | Side classification and tapping accuracy on real clips |
| 18 Open/close | Opening/cycle/range consistency proxies | Reference task validation |
| 19 Sit-to-stand | Knee extension, transition and dedicated review | Failed attempts/stability/clinical transfer scoring not established |
| 20 Reach/grasp | Reach range/wrist path/aperture proxies; object detection absence disclosed | True target contact/grasp success and smoothness validation |
| 20A 3D body | Plotly skeleton replay with rotation/zoom/frame controls | Patient/clinician review of real extracted movement |
| 20B Gait trajectory | Foot/hip/arm camera-space paths, knee curves and baseline overlay | No absolute metric walking path; reference validation required |
| 20C 3D hand | Separate 21-landmark skeleton, fingertip trajectory and hand curves | Real hand recording and side confirmation |
| 21 Quality | Tests cover dark/no-hand/corrupt/metadata/movement gates | Threshold sensitivity/specificity on representative devices |
| 22 Live indicators | Camera-active frame processing and brightness/visibility indicators observed in browser; timers and recording safeguards tested | Accepted body/hand recording on target hardware |
| 23 Voice | Microphone/WAV, three distinct task records and language choice | Actual microphone permission trial; translated fixed prompt review |
| 24 Preprocessing | Original kept; working-copy DC removal, resampling, normalization and activity segmentation | Noise handling/VAD validation; no validated denoiser claimed |
| 25 Audio features | Real spectrum/MFCC/energy/pause/pitch estimates; silence/clipping tests | Biomarker accuracy/repeatability; jitter/shimmer excluded |
| 26 Deep audio | Explicit unavailable model status; trusted artifact extension pattern | GPU training/data/embeddings |
| 27 ASR | Manual reviewed transcript fallback and unavailable ASR status | Local/provider ASR, language detection, error validation |
| 28 Functional NLP | Multilingual dictionaries, clauses/negation, side/time/severity and self-report flags | Reviewed clinical corpus, translation and embedding models |
| 29 ADL | Nine bounded items in atomic form; custom scale disclosure | Clinician-selected validated instrument |
| 30 Feature tables | Authorized, private Parquet export with aligned visit IDs, UTC time, methods and accepted features; missing modalities preserved | Approved cohort and clinical reference targets |
| 31 Baseline ML | Logistic/RF classifier and ridge/RF regressor training + trusted offline inference | Real training, external validation; SVM/XGBoost/CatBoost comparison |
| 32 Leakage | Tested patient-disjoint split and training-only imputation/scaling | Site/device/time confound protocol and sufficient cohort |
| 33 Deep learning | CPU app stays lightweight; advanced models explicit unavailable | Remote training, reproducible notebooks and validated exports |
| 34 Embeddings | Real engineered features available, no invented embeddings | Trained modality embeddings |
| 35 Simple fusion | Available/missing measurement coverage implemented | Learned concatenation/MLP and proper target validation |
| 36 Attention | Explicit unavailable advanced status | Only after a validated baseline and adequate dataset |
| 37 Missing modality | Missing measurements excluded and surfaced | Trained masking/dropout if learned fusion is adopted |
| 38 Personal baseline | First accepted task with compatible method/language; rejected/abandoned excluded | Matched setup/reference selection with care team |
| 39 Timeline | Accepted task trends and repeat history | Clinical longitudinal dataset/reliability studies |
| 40 Temporal model | Measured chronological deltas only | Sufficient repeated data before LSTM/Transformer |
| 41 XAI | Plain measured deltas; held-out permutation importance in training manifest | Neural attribution only for implemented validated neural models |
| 42 Uncertainty | Reports disclose not calibrated; offline metrics have bootstrap intervals/calibration | Individual prediction uncertainty and clinician review thresholds |
| 43 Approved evidence | Versioned approved-document retrieval implementation; empty default | Clinician-approved, licensed knowledge library |
| 44 Structured report input | Results, history, explanations, coverage and evidence passed structurally | Optional external provider/privacy contract if later selected |
| 45 Summaries | Deterministic patient/clinician reports, translated template variants, persisted JSON download | Clinical/translation review; functioning grounded LLM not claimed |
| 46 Agents | Purposeful deterministic orchestration stages | No autonomous multi-LLM system configured |
| 47 Safety workflow | Fixed supported templates, provenance, review flags and audited stages | Independent safety evaluation for later GenAI |
| 48 MCP | Optional typed authorization/audit HTTP facade and bearer tests | Deployment auth lifecycle/integration trial; server remains off |
| 49 Clinician dashboard | Assigned patient overview, movement/3D, speech, ADL, measured explanations, clinical context and review | Clinical usability and representative media trial |
| 50 Patient progress | Accepted measurement charts and understandable summary/status | Clinical usability and interpretation review |
| 51 Software tests | Registration/login/roles/private storage/transactions/resume/report/deactivation/review | Actual hardware capture permissions and browser recording |
| 52 Pipeline tests | Corruption/silence/clipping/invalid forms/no-hand/dark/missing model/missing modality/repeats | Real clinical edge-case recordings |
| 53 Validation metrics | Consent/source-scoped measurement studies, independent reference entry, participant-balanced errors/bootstrap, matched repeats and camera/lighting strata; offline split/failure manifest | Genuine reference measurements, representative prospective evaluation and independent review |
| 54 Local development | Streamlit → ordinary services → PostgreSQL + private disk | None for initialized local prototype |
| 55 Production | Local Compose, private gateway, recovery, encrypted backups/drills, patient data controls and clinic feasibility workflow | HTTPS/private network, disk encryption, off-site/scheduled backups, operations and clinical governance; not publicly deployed |

## Recommended first twenty tasks

1–9 are implemented, including PostgreSQL-backed registration, role routing and modular pages. 10–17 have working capture/upload/landmark/viewer/quality code, official models and negative inference tests; successful human camera recordings remain a user acceptance gate. 18–19 are implemented with tested engineered audio, ADL and timeline, with microphone capture hardware unverified. Task 20 has an offline training/inference workflow; connecting a **validated** baseline or learned multimodal model requires a supplied approved dataset and completed evaluation.

## Acceptance criteria that remain open

The roadmap's final definition of done is **not fully satisfied**. The following must stay unchecked:

- Real camera and microphone permission/capture on target hardware, plus accepted walking, turning, both hands, transfers and reaching recordings.
- Landmark/quality/task accuracy and test-retest reliability against appropriate references, including representative phones, lighting and mobility aids.
- Clinician-approved ADL instrument, translated instructions and Urdu/Pashto language/report review.
- Functioning ASR with language/error metadata; deep audio/pose/text embedding exports.
- Genuine supervised baseline training and validation; learned multimodal missing-input handling; individual calibrated uncertainty and neural XAI where applicable.
- Learned longitudinal models, only when repeated data are sufficient.
- Populated approved evidence library and grounded, independently evaluated GenAI if an LLM is adopted.
- Production operator identity/MFA, approved retention and fulfilment procedures, disk encryption, HTTPS, audited migrations, off-site/scheduled backups and operational monitoring. Private media, consent withdrawal, recovery and encrypted restore-drill tooling now exist; clinic operations still require configuration.
- Clinical operating approval and production deployment.

## Immediate next actions

1. Create the first administrator with `scripts/bootstrap_admin.py`, create the care-team accounts and assign patients. No real accounts or patient history were seeded.
2. Perform a supervised user trial of camera/microphone and each supported task. Use matched setup and task duration for repeated recordings.
3. Have the clinical team approve the tasks, quality thresholds, ADL instrument, consent language and translations.
4. Supply an approved deidentified cohort with patient IDs, reference targets, device/site metadata and repeated sessions. Keep all resulting files outside Git.
5. Train/evaluate the classical baseline, audit calibration and subgroup/device performance, then decide whether deep/attention/ASR additions are justified.
6. Populate approved evidence and evaluate reports before enabling an external GenAI provider or deployment.

## Implementation sources

The implementation checked current primary documentation: [Streamlit navigation](https://docs.streamlit.io/develop/concepts/multipage-apps/page-and-navigation), [microphone recording](https://docs.streamlit.io/develop/api-reference/widgets/st.audio_input), [streamlit-webrtc](https://github.com/whitphx/streamlit-webrtc), and [MediaPipe Pose Landmarker](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/PoseLandmarker). The webrtc callback lifecycle and per-thread locking requirements informed capture cleanup; the MediaPipe Tasks API informed model loading. Local installed code and actual runtime/tests are the evidence for delivered behavior.
