# ParkinSense-PK — Complete Step-by-Step Streamlit App Implementation Roadmap

> **Goal:** Build a real patient-facing and clinician-facing Parkinson’s functional monitoring application using **Streamlit**, Machine Learning, Deep Learning, Computer Vision, Audio AI, NLP, Multimodal AI, XAI, GenAI, Agentic AI and MCP.
>
> **Development machine:** Intel i5 6th Gen, 12 GB RAM. This is suitable for Streamlit development, classical ML, preprocessing, lightweight Computer Vision, audio feature extraction and compact-model inference. Use **Google Colab/Kaggle/cloud GPU** for heavy deep-learning training.
>
> **App scope:** Patient monitoring and rehabilitation decision-support. The app must **not** autonomously diagnose Parkinson’s disease or change medication.
>
> **Important:** The research paper is a separate deliverable. There is **no Researcher role, research dashboard, research menu, research experiment page, or research option inside this application**.

---

# 0. What You Are Building

## Final Application

**ParkinSense-PK** is a Streamlit-based application that captures and analyzes:

- walking and turning video;
- finger tapping;
- hand opening/closing;
- sit-to-stand;
- reach/grasp functional tasks;
- **interactive 3D body/hand skeleton visualization and gait trajectory playback**;
- voice recordings;
- Urdu/Pashto/English natural speech;
- Activities of Daily Living (ADL) information;
- relevant clinical metadata;
- previous assessments for longitudinal comparison.

## Final user roles

Only three app roles are required:

1. **Patient** — completes assessments and sees simple progress information.
2. **Clinician/Therapist** — reviews patient assessments, trends, explanations and reports.
3. **Admin** — manages accounts, permissions, configuration and system status.

**Do not create a Researcher role.**

## Final user flow

```text
Patient Login / Registration
        ↓
Patient Home
        ↓
Start Assessment
        ↓
Camera + Microphone Permission
        ↓
Walking / Turning Test
        ↓
Finger / Hand Test
        ↓
Sit-to-Stand / Reach Test
        ↓
Voice Recording
        ↓
Urdu / Pashto / English Speech
        ↓
ADL Questionnaire
        ↓
Data Quality Check
        ↓
2D/3D Pose + Hand Reconstruction
        ↓
Interactive 3D Skeleton / Motion View
        ↓
CV + Audio + NLP Processing
        ↓
Multimodal AI
        ↓
Personal Baseline Comparison
        ↓
Longitudinal Trend Analysis
        ↓
Uncertainty + XAI
        ↓
Safe GenAI Report
        ↓
Patient Summary + Clinician Dashboard
```

---

# PART A — COMPUTER AND PROJECT SETUP

## Phase 1 — Use Python 3.11

For ML library compatibility, use **Python 3.11** instead of the newest Kali system Python.

Recommended with `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.11
mkdir -p ~/Projects/parkinsense-pk
cd ~/Projects/parkinsense-pk
uv venv --python 3.11 .venv
source .venv/bin/activate
```

Do not modify Kali's system Python packages.

## Phase 2 — Initialize Git

```bash
git init
git branch -M main
mkdir -p app backend ml data docs scripts tests infra models
```

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
.env
.env.*
data/raw/
data/private/
models/private/
mlruns/
.streamlit/secrets.toml
.DS_Store
```

Never commit patient video/audio, credentials or identifying information.

## Phase 3 — Recommended repository structure

```text
parkinsense-pk/
├── app/
│   ├── Home.py
│   ├── pages/
│   │   ├── 1_Login.py
│   │   ├── 2_Register.py
│   │   ├── 3_Patient_Home.py
│   │   ├── 4_Start_Assessment.py
│   │   ├── 5_Walking_Test.py
│   │   ├── 6_Hand_Test.py
│   │   ├── 7_Sit_Stand_Reach.py
│   │   ├── 8_Voice_Test.py
│   │   ├── 9_ADL_Assessment.py
│   │   ├── 10_3D_Visualizer.py
│   │   ├── 11_Results.py
│   │   ├── 12_Progress.py
│   │   ├── 13_Clinician_Dashboard.py
│   │   └── 14_Admin.py
│   ├── components/
│   │   ├── pose_3d_viewer.py
│   │   └── hand_3d_viewer.py
│   ├── state/
│   └── utils/
├── backend/
│   ├── db/
│   ├── services/
│   ├── security/
│   ├── storage/
│   └── config.py
├── ml/
│   ├── common/
│   ├── tabular/
│   ├── vision/
│   │   ├── pose2d.py
│   │   ├── pose3d.py
│   │   ├── gait_3d.py
│   │   └── hand_3d.py
│   ├── audio/
│   ├── nlp/
│   ├── multimodal/
│   ├── temporal/
│   ├── xai/
│   └── inference/
├── data/
│   ├── public/
│   ├── processed/
│   └── features/
├── models/
├── docs/
├── scripts/
├── tests/
├── infra/
├── requirements.txt
└── README.md
```

### Acceptance criterion

- Python 3.11 environment activates.
- Streamlit starts successfully.
- Repository contains no patient/private data.

---

# PART B — STREAMLIT APPLICATION FOUNDATION

## Phase 4 — Install lightweight dependencies first

```bash
uv pip install streamlit streamlit-webrtc sqlalchemy psycopg[binary] alembic \
  pydantic-settings python-multipart passlib[bcrypt] pyjwt \
  numpy pandas scipy scikit-learn joblib pyarrow plotly
```

Add Computer Vision/audio libraries when needed:

```bash
uv pip install opencv-python mediapipe librosa soundfile
```

Add heavier AI libraries later:

```bash
uv pip install torch torchvision torchaudio transformers sentence-transformers \
  xgboost catboost shap mlflow
```

Do not install every heavy dependency on day one.

## Phase 5 — Streamlit configuration

Create:

```text
.streamlit/config.toml
```

Example:

```toml
[theme]
base = "dark"

[server]
maxUploadSize = 500
```

Keep the app in **dark theme**.

## Phase 6 — Start the app

Create `app/Home.py`:

```python
import streamlit as st

st.set_page_config(
    page_title="ParkinSense-PK",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("ParkinSense-PK")
st.caption("AI-assisted longitudinal functional monitoring for Parkinson's disease")
```

Run:

```bash
streamlit run app/Home.py
```

---

# PART C — AUTHENTICATION AND USER MANAGEMENT

## Phase 7 — Registration

The application must contain a **Register** option.

Patient registration fields can include:

```text
Full name
Email / username
Password
Preferred language
Date of birth / age where clinically needed
Consent acknowledgement
```

Use password hashing. Never save plain-text passwords.

## Phase 8 — Login

After login, route based on role:

```text
Patient   -> Patient Home
Clinician -> Clinician Dashboard
Admin     -> Admin Panel
```

There is **no Researcher option**.

## Phase 9 — Session state

Use `st.session_state` for:

```text
logged_in
user_id
role
active_patient_id
active_assessment_id
current_step
```

Do not rely on session state as permanent storage. Persist important data in PostgreSQL.

---

# PART D — DATABASE AND STORAGE

## Phase 10 — PostgreSQL schema

Core tables:

```text
users
patients
clinicians
patient_clinician_links
consents
assessments
assessment_files
clinical_measurements
adl_responses
model_runs
model_outputs
explanations
reports
audit_logs
```

Key principle:

- PostgreSQL stores structured metadata.
- Video/audio are stored in secure file/object storage.
- Database stores the file path/object key.

## Phase 11 — Storage layout

Example:

```text
data/private/
└── patient_<uuid>/
    └── assessment_<uuid>/
        ├── walking.mp4
        ├── finger_left.mp4
        ├── finger_right.mp4
        ├── sit_to_stand.mp4
        ├── voice.wav
        └── metadata.json
```

Use UUIDs rather than patient names in storage paths.

---

# PART E — STREAMLIT PATIENT EXPERIENCE

## Phase 12 — Patient Home

Display:

```text
Welcome
Start New Assessment
Previous Assessments
Progress
Reports
Profile
```

Do not expose internal ML probability outputs unnecessarily.

## Phase 13 — Modular Assessment Hub

Do **not** force all body parts into one combined capture screen. The patient should first enter an **Assessment Hub** and choose the body part / functional task to assess. Each module must have its own instructions, live capture, video upload, quality checks, 2D/3D visualization, extracted features and results.

```text
Start Assessment
    │
    ├── Lower Body / Gait
    │     ├── Walking
    │     └── Turning
    │
    ├── Hand / Finger
    │     ├── Finger Tapping — Left
    │     ├── Finger Tapping — Right
    │     └── Hand Open / Close
    │
    ├── Trunk / Transfer
    │     └── Sit-to-Stand
    │
    ├── Upper Limb / Functional Reach
    │     ├── Reach
    │     ├── Grasp
    │     └── Object Transfer
    │
    ├── Voice / Speech
    └── ADL Questionnaire
```

Every visual assessment module should offer **two input modes**:

```text
[ Live Camera ]      [ Upload Recorded Video ]
```

The same analysis pipeline must be used after either input path, so live and uploaded recordings remain comparable.

### Suggested Streamlit module cards

```text
┌────────────────────┐  ┌────────────────────┐
│ WALKING / GAIT     │  │ FINGER TAPPING     │
│ Lower body         │  │ Hand / fingers     │
│ Live | Upload      │  │ Live | Upload      │
└────────────────────┘  └────────────────────┘

┌────────────────────┐  ┌────────────────────┐
│ SIT-TO-STAND       │  │ REACH / GRASP      │
│ Trunk + legs       │  │ Upper limb / hand  │
│ Live | Upload      │  │ Live | Upload      │
└────────────────────┘  └────────────────────┘
```

When the user opens one module, use a guided sequence:

```text
Step 1 — Instructions
Step 2 — Choose Live Camera or Video Upload
Step 3 — Capture / Upload
Step 4 — Quality Check
Step 5 — 2D + 3D Analysis
Step 6 — Review
Step 7 — Save Result
```

Use `st.progress()` for each module independently. This makes the app easier to use and lets a clinician repeat only one affected body-part test instead of repeating the entire assessment.

---

# PART F — LIVE CAMERA AND COMPUTER VISION

## Phase 13A — Video Upload Option

Every movement module must support previously recorded video in addition to live camera capture.

Recommended Streamlit control:

```python
uploaded_video = st.file_uploader(
    "Upload assessment video",
    type=["mp4", "mov", "avi", "mkv"]
)
```

For an uploaded video:

```text
Uploaded Video
    ↓
Validate format / size / duration
    ↓
Decode with OpenCV
    ↓
Run the same MediaPipe Pose or MediaPipe Hands pipeline
    ↓
Quality Check
    ↓
Feature Extraction
    ↓
2D Overlay + 3D Visualization
    ↓
ML / DL Inference
    ↓
Save Assessment Result
```

The user must select the correct assessment type before upload, for example:

```text
Video Type:
○ Walking / Turning
○ Finger Tapping — Left
○ Finger Tapping — Right
○ Hand Open / Close
○ Sit-to-Stand
○ Reach / Grasp / Object Transfer
```

Do not automatically treat every uploaded video as the same task. Each task has its own landmark set, feature extractor and validation rules.

### Upload validation

Check:

- supported file type;
- file size;
- duration;
- frame rate;
- resolution;
- body/hand visibility;
- orientation;
- whether the selected task appears to be present;
- whether enough valid frames exist for analysis.

If the video is unsuitable, show a clear message rather than generating a prediction.

---

## Phase 14 — Live camera capture

Use **`streamlit-webrtc`** for live video when possible.

Flow:

```text
Browser Camera
    ↓
Streamlit WebRTC
    ↓
OpenCV frame
    ↓
MediaPipe Pose / Hands
    ↓
Live landmarks overlay
    ↓
Feature buffer
```

The UI should show:

```text
Camera active
Body detected ✓
Lighting quality
Full body visible
Recording timer
Task instruction
```

## Phase 14A — Separate Body-Part Analysis Modules

Keep each movement pathway isolated in code as well as in the UI. This avoids mixing hand landmarks with gait landmarks and makes model testing easier.

Recommended structure:

```text
app/services/cv/
├── gait/
│   ├── capture.py
│   ├── quality.py
│   ├── pose.py
│   ├── features.py
│   ├── model.py
│   └── visualizer_3d.py
│
├── hand/
│   ├── capture.py
│   ├── quality.py
│   ├── landmarks.py
│   ├── tapping_features.py
│   ├── open_close_features.py
│   ├── model.py
│   └── visualizer_3d.py
│
├── sit_to_stand/
│   ├── quality.py
│   ├── features.py
│   ├── model.py
│   └── visualizer_3d.py
│
└── reach_grasp/
    ├── quality.py
    ├── features.py
    ├── model.py
    └── visualizer_3d.py
```

### Lower Body / Gait module

Analyze primarily:

- hips;
- knees;
- ankles;
- feet;
- trunk;
- arm swing where relevant.

Display:

```text
Walking Video
   ↓
2D Pose Overlay
   ↓
3D Lower-Body Skeleton
   ↓
Gait Path / Joint Trajectories
   ↓
Gait Metrics
```

### Hand / Finger module

Analyze primarily:

- wrist;
- thumb;
- index finger;
- remaining finger landmarks;
- left and right hands separately.

Display:

```text
Finger / Hand Video
   ↓
2D Hand Landmarks
   ↓
3D Hand Skeleton
   ↓
Fingertip Trajectory
   ↓
Tapping / Open-Close Metrics
```

### Sit-to-Stand module

Analyze primarily:

- trunk;
- hips;
- knees;
- ankles.

Display the transition as a dedicated 3D movement replay instead of mixing it with walking.

### Reach / Grasp module

Analyze primarily:

- shoulder;
- elbow;
- wrist;
- hand;
- target/object interaction when detectable.

Display 3D upper-limb trajectory, reach path and hand movement separately from gait.

Each module should save its own result object so it can be repeated, compared with baseline and reviewed independently.

---

## Phase 15 — Walking / turning test

Instruction:

```text
1. Place the device on a stable stand.
2. Make sure the full body is visible.
3. Stand at the starting point.
4. Press Start.
5. Walk the defined distance.
6. Turn safely.
7. Walk back.
8. Press Finish or allow automatic completion.
```

Capture:

- body landmarks;
- timestamps;
- task duration;
- quality metadata.

## Phase 16 — Pose extraction

Use MediaPipe first because it is lightweight enough for your laptop.

Pipeline:

```text
Frame
  ↓
MediaPipe Pose
  ↓
Hip / Knee / Ankle / Shoulder / Wrist landmarks
  ↓
Normalized coordinate sequence
```

Candidate gait features:

- cadence proxy;
- step/cycle timing;
- left/right symmetry;
- arm swing amplitude;
- turning duration;
- trunk movement;
- movement variability.

## Phase 17 — Finger tapping

Use MediaPipe Hands.

For thumb-index distance:

```text
d(t) = sqrt((x_thumb-x_index)^2 + (y_thumb-y_index)^2)
```

Extract:

- tapping frequency;
- mean amplitude;
- amplitude decrement;
- rhythm variability;
- left/right asymmetry.

## Phase 18 — Hand open/close

Track hand landmarks over time and compute:

- open-close cycle count;
- cycle speed;
- range;
- decrement;
- movement consistency.

## Phase 19 — Sit-to-stand

Track hip, knee, ankle and trunk trajectory.

Measure:

- transition duration;
- trunk angle;
- movement smoothness;
- failed/extra attempts;
- stability proxies.

## Phase 20 — Reach and grasp

Track:

- shoulder;
- elbow;
- wrist;
- fingers;
- target/object when feasible.

Extract:

- reach duration;
- path length;
- smoothness;
- grasp timing;
- endpoint stability.

## Phase 20A — Interactive 3D body skeleton

Add a **3D motion viewer inside Streamlit** so the patient/clinician can rotate, zoom and inspect the captured body movement.

Use MediaPipe Pose first because it exposes normalized landmarks and approximate world landmarks. Convert the selected joints into a 3D skeleton:

```text
Camera video
   ↓
MediaPipe Pose
   ↓
(x, y, z) landmarks
   ↓
Joint connection graph
   ↓
Plotly Scatter3d
   ↓
Interactive 3D skeleton in Streamlit
```

Recommended joints:

- shoulders;
- elbows;
- wrists;
- hips;
- knees;
- ankles;
- heels;
- foot indices.

Render with Plotly:

```python
import plotly.graph_objects as go
import streamlit as st

fig = go.Figure()
fig.add_trace(go.Scatter3d(
    x=x, y=y, z=z,
    mode="markers+lines",
))
fig.update_layout(
    scene=dict(
        xaxis_title="X",
        yaxis_title="Y",
        zaxis_title="Z",
        aspectmode="data",
    ),
    margin=dict(l=0, r=0, t=30, b=0),
)
st.plotly_chart(fig, use_container_width=True)
```

For animation, keep a time-indexed landmark buffer and expose a frame/slider or Plotly animation so the user can replay:

```text
Frame 1 → Frame 2 → Frame 3 → ... → Frame N
                  ↓
            3D motion replay
```

### Important accuracy note

A single RGB camera does **not** provide laboratory-grade metric 3D motion capture. The first app version should label this as **relative/estimated 3D pose visualization**. Do not present monocular depth values as clinically validated distances. If later you need higher-accuracy 3D, add multi-view cameras or depth-capable hardware as a separate advanced phase.

## Phase 20B — 3D gait trajectory and joint-angle view

On the same 3D page, add:

```text
3D Skeleton
3D Walking Path
Left/Right Foot Trajectory
Hip/Knee/Ankle Trajectory
Joint Angle Charts
Center-of-body trajectory proxy
Baseline vs Current overlay
```

Useful derived visualizations:

- left and right ankle trajectories through time;
- knee flexion/extension angle curves;
- hip trajectory;
- arm-swing path;
- turning path;
- asymmetry overlay;
- baseline skeleton vs current-session skeleton.

The Streamlit layout can use two columns:

```text
┌─────────────────────────────┬─────────────────────────────┐
│  Interactive 3D Skeleton    │  Joint / Gait Metrics       │
│  rotate / zoom / replay     │  cadence, symmetry, angles  │
└─────────────────────────────┴─────────────────────────────┘
```

## Phase 20C — 3D hand/finger visualization

For finger tapping and hand open/close, use MediaPipe Hands landmarks and display a rotatable 3D hand skeleton:

```text
Hand video
   ↓
21 hand landmarks
   ↓
(x, y, z) sequence
   ↓
3D hand skeleton
   ↓
Tap amplitude / rhythm / decrement visualization
```

Show:

- thumb-index distance;
- fingertip trajectories;
- hand opening range;
- left/right comparison;
- current vs baseline movement path.

---

# PART G — LIVE QUALITY CHECKER

## Phase 21 — Video quality checker

Before accepting a recording, automatically check:

- brightness;
- blur;
- body visibility;
- hand visibility;
- valid landmark percentage;
- recording duration;
- excessive occlusion;
- task completion.

Example rule:

```python
if valid_pose_fraction < threshold:
    status = "REPEAT"
else:
    status = "ACCEPT"
```

Streamlit should immediately show messages such as:

```text
Move farther from the camera.
Full body is not visible.
Lighting is too low.
Hand left the frame.
Good recording — continue.
```

## Phase 22 — Live analysis panel

During supported tasks, show live non-diagnostic indicators:

```text
Pose detected
Hands detected
Frames analyzed
Task duration
Recording quality
```

Do not display a final medical prediction while the task is still being recorded.

---

# PART H — AUDIO AND VOICE CAPTURE

## Phase 23 — Voice tasks

Collect:

1. sustained vowel;
2. fixed sentence;
3. natural speech.

Example natural-language prompt:

> "Aaj aapko rozmarra ke kaamon mein kya mushkil hui?"

Support:

```text
Urdu
Pashto
English
Mixed speech
```

## Phase 24 — Audio preprocessing

```text
Raw audio
   ↓
Resample
   ↓
Noise handling
   ↓
Silence segmentation
   ↓
Normalization
```

Store the original securely and process a working copy.

## Phase 25 — Engineered audio features

Use `librosa`/`torchaudio` for:

- MFCC;
- pitch/F0 statistics;
- energy;
- spectral measures;
- pause duration;
- speech rate.

Use jitter/shimmer only if technically validated in your implementation.

## Phase 26 — Deep audio embeddings

Do heavy Wav2Vec2/HuBERT processing on Colab/Kaggle GPU.

Recommended workflow:

```text
Audio dataset
   ↓
GPU notebook
   ↓
Speech embeddings
   ↓
Export Parquet/NPY
   ↓
Local app/inference pipeline
```

---

# PART I — NLP FOR URDU / PASHTO / ENGLISH

## Phase 27 — Speech-to-text

Pipeline:

```text
Audio
  ↓
ASR
  ↓
Transcript
  ↓
Language detection
  ↓
NLP processing
```

Store ASR confidence/error metadata when available.

## Phase 28 — Functional NLP

Extract information such as:

```text
activity: dressing
problem: buttoning
side: right
severity: self-reported moderate
time: morning
```

Target domains:

- dressing;
- feeding;
- grooming;
- writing;
- walking;
- transfers;
- freezing descriptions;
- falls;
- fatigue;
- hand-use difficulty;
- daily-life limitations.

Start with dictionaries/rules + multilingual embeddings. Add larger NLP models later only if justified.

---

# PART J — ADL MODULE

## Phase 29 — ADL form

Streamlit form can contain:

```text
Dressing
Feeding
Grooming
Bathing
Writing
Phone use
Walking
Transfers
Household activities
Other daily-life difficulty
```

Prefer validated clinical/functional scales when the clinician team selects them.

Use `st.form()` so the complete form is submitted atomically.

---

# PART K — BASELINE MACHINE LEARNING

## Phase 30 — Prepare feature tables

For each modality create normalized feature tables:

```text
patient_id
assessment_id
session_date
features...
target/clinical reference
```

## Phase 31 — Classical models

Start with:

- Logistic Regression;
- Random Forest;
- SVM;
- XGBoost;
- CatBoost.

These are your baseline models and can train on your laptop for sensible dataset sizes.

## Phase 32 — Prevent data leakage

Never place recordings from the same patient in both train and test sets.

Correct:

```text
Patient A -> train only
Patient B -> train only
Patient C -> validation only
Patient D -> test only
```

Use patient/group-aware splits.

---

# PART L — DEEP LEARNING

## Phase 33 — Lightweight local inference, heavy remote training

Train heavier models on Colab/Kaggle:

- 1D CNN;
- LSTM/BiLSTM;
- temporal CNN;
- speech Transformer;
- temporal pose Transformer;
- multimodal Transformer.

After training:

```text
GPU model
   ↓
Export weights / ONNX / TorchScript where appropriate
   ↓
Optimize
   ↓
Load compact inference model in app/backend
```

Do not train raw-video Transformers locally on the i5/12 GB machine.

---

# PART M — MULTIMODAL AI

## Phase 34 — Build modality embeddings

Create fixed-size representations:

```text
E_gait
E_hand
E_audio
E_text
E_adl
E_clinical
```

## Phase 35 — Simple fusion first

Start with concatenation:

```text
E = [E_gait || E_hand || E_audio || E_text || E_adl || E_clinical]
        ↓
      MLP
        ↓
Functional outputs
```

If data quality is poor, fix the data before adding a Transformer.

## Phase 36 — Attention fusion

After a stable baseline:

```text
Modality embeddings
       ↓
Modality tokens
       ↓
Multi-head / Cross Attention
       ↓
Fused representation
       ↓
Prediction heads
```

Potential outputs:

```text
Mobility
Upper-limb function
Speech function
ADL function
Overall functional change
```

Only label outputs as clinical scores if they have been validated against appropriate clinical reference measures.

## Phase 37 — Missing-modality support

The app must still work when one modality is unavailable.

Train with modality masking/dropout:

```text
No audio
No video
No text
Multiple missing modalities
```

At runtime show which modalities contributed to the output.

---

# PART N — PERSONAL BASELINE AND LONGITUDINAL MONITORING

## Phase 38 — Personal baseline

For each patient:

```text
B_patient = first reliable/reference assessment
```

For a later assessment:

```text
Delta = Current - Baseline
```

This lets the app answer:

> "How is this patient different from their own earlier state?"

rather than only comparing them with a population average.

## Phase 39 — Longitudinal timeline

Store each reliable assessment:

```text
T0 -> T1 -> T2 -> T3 -> ...
```

Plot trends in Streamlit using Plotly:

- mobility;
- hand function;
- speech features;
- ADL;
- selected measured features.

## Phase 40 — Temporal model

Use simple time-series methods first. If repeated data is sufficient, test:

- LSTM;
- temporal Transformer.

Do not use a large sequence model with only a few patients/sessions.

---

# PART O — XAI, CALIBRATION AND UNCERTAINTY

## Phase 41 — Explainable AI

Use:

- SHAP/permutation importance for tabular models;
- integrated gradients for neural sequence models;
- temporal attribution for time-series;
- Grad-CAM only for suitable raw-image models.

Clinician view should say things like:

```text
Turning duration increased
Right-hand tapping amplitude decreased
Gait asymmetry increased
Speech pauses increased
ADL dressing difficulty increased
```

Not just:

```text
SHAP = 0.183
```

## Phase 42 — Uncertainty

Estimate uncertainty using methods such as:

- model ensembles;
- bootstrap confidence intervals;
- calibrated probabilities;
- MC dropout when appropriate.

Rule:

```text
High uncertainty -> clinician review required
```

---

# PART P — GENAI AND RAG

## Phase 43 — Approved knowledge base

Build RAG only from approved sources such as:

- Parkinson rehabilitation guidance;
- occupational therapy guidance;
- approved patient education;
- selected peer-reviewed clinical evidence.

Store document metadata and versions.

## Phase 44 — Structured GenAI input

The LLM should receive structured data:

```json
{
  "measured_features": {},
  "model_outputs": {},
  "uncertainty": {},
  "change_from_baseline": {},
  "retrieved_evidence": []
}
```

It should **not** directly inspect arbitrary raw patient data and improvise a diagnosis.

## Phase 45 — GenAI outputs

Generate two separate outputs:

### Clinician summary

- measured changes;
- predicted functional changes;
- confidence/uncertainty;
- key contributing factors;
- evidence references;
- items needing clinician review.

### Patient summary

Use simple Urdu/Roman Urdu/English language according to preference.

Do not prescribe medication or declare a definitive diagnosis.

---

# PART Q — AGENTIC AI

## Phase 46 — Initial agents

Use only agents that have a clear purpose:

1. **Supervisor Agent**
2. **Data Quality Agent**
3. **Analysis Agent**
4. **History Agent**
5. **Evidence Agent**
6. **Safety Agent**
7. **Report Agent**

The deterministic ML/DL pipeline remains the source of measurements and predictions. Agents coordinate the workflow.

## Phase 47 — Agent workflow

```text
Supervisor
    ↓
Data Quality Agent
    ↓
Analysis Agent
    ↓
History Agent
    ↓
Evidence Agent
    ↓
Safety Agent
    ↓
Report Agent
```

The Safety Agent should reject or flag:

- unsupported diagnosis claims;
- medication changes;
- contradictions;
- high-confidence wording when model uncertainty is high.

---

# PART R — MCP

## Phase 48 — Add MCP only after normal services work

First build and test ordinary Python functions/services.

Then expose controlled MCP tools such as:

```text
get_patient_timeline
get_assessment
run_gait_analysis
run_hand_analysis
run_audio_analysis
run_nlp_analysis
run_multimodal_inference
get_explanation
retrieve_approved_evidence
save_report
```

Requirements:

- authorization on each tool;
- strict input schemas;
- audit logs;
- no arbitrary SQL access;
- no uncontrolled patient-file access;
- no raw patient media sent to an LLM by default.

---

# PART S — STREAMLIT CLINICIAN DASHBOARD

## Phase 49 — Clinician dashboard

Use Streamlit tabs/containers for:

```text
Patient Overview
Latest Assessment
Functional Trends
Gait
3D Motion Viewer
Hand Function
Voice / Speech
ADL
AI Explanation
Reports
```

Show:

- assessment date/time;
- recording quality;
- available/missing modalities;
- current functional estimates;
- change from personal baseline;
- longitudinal charts;
- **interactive 3D body skeleton and gait playback**;
- **3D hand/finger visualization**;
- baseline-vs-current 3D overlay;
- uncertainty;
- measured feature changes;
- XAI explanation;
- safe generated summary.

## Phase 50 — Patient progress page

Show only understandable information:

```text
Assessment completed
Movement measures compared with previous visit
Progress charts
3D movement replay / skeleton view
Simple explanation
Clinician review status
```

Avoid alarming red/green diagnostic labels.

---

# PART T — APP TESTING

## Phase 51 — Software tests

Test:

- registration;
- login/logout;
- permissions;
- camera access;
- microphone access;
- file saving;
- database writes;
- assessment resume/restart;
- role protection;
- report loading.

## Phase 52 — AI pipeline tests

Test:

- bad video;
- missing hand;
- poor lighting;
- silent audio;
- corrupted file;
- unavailable modality;
- model load failure;
- extreme/invalid form values;
- repeated assessments.

## Phase 53 — Model validation metrics

Depending on the task:

### Classification

```text
AUROC
PR-AUC
F1
Sensitivity
Specificity
Precision
Recall
Calibration
```

### Regression / functional estimate

```text
MAE
RMSE
R²
Pearson/Spearman correlation
```

### Longitudinal monitoring

```text
change error
agreement with clinical change
sensitivity to change
test-retest reliability
```

These belong to model validation and system testing; they do **not** require a research option in the app.

---

# PART U — YOUR i5 6th GEN / 12 GB RAM WORKFLOW

## Run locally

Your laptop is suitable for:

- Streamlit;
- PostgreSQL;
- Git/VS Code;
- Pandas on moderate datasets;
- scikit-learn;
- XGBoost with sensible sizes;
- OpenCV;
- MediaPipe one stream/video at a time;
- Plotly interactive 3D skeleton/trajectory rendering;
- audio feature extraction;
- cached embeddings;
- compact-model inference;
- plotting/report generation;
- tests.

## Do not train locally

Avoid locally training:

- large Wav2Vec/HuBERT models;
- Whisper-scale models;
- raw-video Transformers;
- large multimodal Transformers;
- LLMs;
- large hyperparameter sweeps.

Use Colab/Kaggle/cloud GPU.

## Memory-saving rules

1. Process one video at a time.
2. Do not hold all frames in RAM.
3. Save pose/hand landmarks immediately to Parquet/NPY.
4. Cache speech/text embeddings.
5. Use Parquet instead of very large CSV files.
6. Use float32 locally.
7. Use float16/bfloat16 on supported GPU workloads.
8. Run only required Docker/database services.
9. Avoid multiple heavy notebooks/browser tabs during CV processing.
10. Prefer MediaPipe landmark processing before heavy raw-video DL.

---

# PART V — DEPLOYMENT

## Phase 54 — Local development

For the simplest version:

```text
Streamlit
   ↓
Python services
   ↓
PostgreSQL
   ↓
Secure file storage
```

You do not need Kubernetes.

## Phase 55 — Production deployment

Recommended later:

```text
Browser / Mobile Browser
        ↓ HTTPS
Streamlit App
        ↓
Backend services
        ↓
PostgreSQL + object storage
        ↓
CPU inference
        ↓
Optional remote GPU inference
```

Potential deployment platforms can be selected later based on data-security requirements.

---

# PART W — FINAL APP NAVIGATION

The final Streamlit sidebar/navigation should look approximately like:

```text
ParkinSense-PK

Patient
 ├── Home
 ├── Start Assessment
 │    ├── Walking / Gait
 │    ├── Finger Tapping / Hand
 │    ├── Sit-to-Stand
 │    ├── Reach / Grasp
 │    ├── Voice / Speech
 │    └── ADL
 ├── Upload Assessment Video
 ├── 3D Motion View
 │    ├── 3D Gait / Lower Body
 │    ├── 3D Hand / Finger
 │    ├── 3D Sit-to-Stand
 │    └── 3D Reach / Upper Limb
 ├── My Results
 ├── Progress
 └── Profile

Clinician
 ├── Dashboard
 ├── Patients
 ├── Assessments
 │    ├── Gait
 │    ├── Hand / Finger
 │    ├── Sit-to-Stand
 │    └── Reach / Grasp
 ├── Uploaded Videos
 ├── 3D Motion Review
 ├── Trends
 └── Reports

Admin
 ├── Users
 ├── Permissions
 ├── System Status
 └── Audit Logs
```

### Explicitly excluded

Do **not** add:

```text
Research
Research Dashboard
Researcher Role
Experiments Page
Paper Generator
Dataset Explorer for ordinary users
```

The research paper remains separate from the application.

---

# PART X — DEFINITION OF DONE

The first serious ParkinSense-PK Streamlit release is complete when:

- [ ] Registration works.
- [ ] Login and role-based access work.
- [ ] There is no Researcher role or Research menu.
- [ ] Streamlit dark-theme interface works on desktop/mobile browser.
- [ ] Patient can open a modular Assessment Hub.
- [ ] Walking/Gait, Hand/Finger, Sit-to-Stand and Reach/Grasp are separate modules.
- [ ] Each movement module offers both Live Camera and Video Upload.
- [ ] Uploaded MP4/MOV/AVI/MKV videos pass format and quality validation before analysis.
- [ ] Live camera opens successfully.
- [ ] Live body/hand detection works.
- [ ] Interactive 3D body skeleton renders in Streamlit.
- [ ] 3D gait/lower-body view is separate from hand/finger analysis.
- [ ] 3D gait trajectory playback works.
- [ ] 3D hand/finger skeleton and fingertip trajectory render in a dedicated hand module.
- [ ] Sit-to-Stand and Reach/Grasp have their own 3D review views.
- [ ] Baseline-vs-current 3D movement comparison works.
- [ ] Video quality feedback works.
- [ ] Walking/turning recording works.
- [ ] Finger-tapping capture works.
- [ ] Hand open/close capture works.
- [ ] Sit-to-stand/reach capture works.
- [ ] Voice recording works.
- [ ] Urdu/Pashto/English speech pipeline works.
- [ ] ADL form works.
- [ ] Media and structured metadata are stored securely.
- [ ] CV/audio/NLP feature pipelines are reproducible.
- [ ] Baseline ML models run with patient-independent validation.
- [ ] Multimodal inference works.
- [ ] Personal baseline comparison works.
- [ ] Repeat assessments appear on a longitudinal timeline.
- [ ] Missing modalities are clearly shown.
- [ ] XAI explanation is available to clinicians.
- [ ] Uncertainty is visible.
- [ ] RAG/GenAI report is grounded and safety checked.
- [ ] Agent workflow is controlled and auditable.
- [ ] MCP tools are authorized, typed and logged.
- [ ] Clinician dashboard works.
- [ ] Patient progress page works.
- [ ] Application does not prescribe medication or make autonomous definitive diagnoses.

---

# Recommended First 20 Tasks — Do These in Order

1. Create Python 3.11 virtual environment.
2. Initialize Git repository.
3. Install Streamlit and lightweight dependencies.
4. Create the dark-theme Streamlit shell.
5. Build Register + Login.
6. Add Patient / Clinician / Admin roles only.
7. Set up PostgreSQL tables.
8. Build Patient Home + modular Assessment Hub.
9. Create separate Walking/Gait, Hand/Finger, Sit-to-Stand and Reach/Grasp pages.
10. Add live camera using `streamlit-webrtc`.
11. Add `st.file_uploader` video input to every movement module.
12. Route uploaded videos through the same OpenCV/MediaPipe pipeline used for live recordings.
13. Add MediaPipe Pose live 2D skeleton for gait/body tasks.
14. Add Plotly-based 3D gait/lower-body view.
15. Add MediaPipe Hands finger-tapping + dedicated 3D hand/finger view.
16. Add separate 3D Sit-to-Stand and Reach/Grasp views.
17. Add task-specific video quality checks.
18. Add voice recording + audio feature extraction.
19. Add ADL questionnaire and patient timeline.
20. Then connect baseline ML models and proceed to multimodal AI.

After these work reliably:

```text
Deep Learning
    ↓
Urdu/Pashto NLP
    ↓
Multimodal Fusion
    ↓
Personal Baseline
    ↓
Longitudinal AI
    ↓
XAI
    ↓
RAG + GenAI
    ↓
Agentic AI
    ↓
MCP
```

---

# Technology Map

| Technology | Role in the App |
|---|---|
| Streamlit | Complete web application UI |
| `st.file_uploader` | Upload recorded assessment videos for task-specific analysis |
| streamlit-webrtc | Live camera/audio streams |
| PostgreSQL | Users, assessments, structured patient history |
| OpenCV | Frame/video processing |
| MediaPipe | Lightweight pose and hand landmarks, including relative 3D landmark coordinates |
| Plotly 3D | Interactive body/hand skeleton, trajectories and baseline-vs-current motion views |
| ML | Baseline/tabular/engineered-feature prediction |
| Deep Learning | Temporal and learned signal patterns |
| Computer Vision | Gait, hand, sit-to-stand, reach/grasp analysis |
| Audio AI | Voice and speech biomarkers |
| NLP | Urdu/Pashto/English functional complaints |
| Multimodal AI | Combine complementary patient signals |
| Personal Baseline | Compare patient with themself |
| Longitudinal AI | Analyze repeat assessments over time |
| XAI | Explain measurable contributors |
| GenAI + RAG | Generate grounded understandable summaries |
| Agentic AI | Coordinate quality, analysis, history, evidence and safety |
| MCP | Standardize controlled access to AI/data tools |
| Colab/Kaggle | Heavy DL training outside your laptop |

---

# Final System in One Line

```text
Patient
→ Streamlit App
→ Live Camera/Microphone Capture
→ 2D/3D Pose + Hand Visualization
→ CV + Audio + NLP + ADL
→ Multimodal AI
→ Personal Baseline
→ Longitudinal Monitoring
→ XAI + Uncertainty
→ Safe Agentic RAG/MCP Workflow
→ Patient + Clinician Report
```

The final ParkinSense-PK application is therefore a **Streamlit-based patient and clinician functional-monitoring platform**, with **no research option inside the app**. The research paper and academic analysis remain completely separate.
