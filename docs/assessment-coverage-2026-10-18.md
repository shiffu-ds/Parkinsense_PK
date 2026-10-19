# Assessment coverage — 18 October 2026

Follow-up: the broader [project audit](project-audit-2026-10-18.md) adds
PD-labelled MDVR-KCL voice evidence and 19 October report-control fixes.
The counts and voice-coverage statements below describe the earlier run.

The application has six assessment sections containing nine movement tasks,
three voice tasks, a reviewed daily-life description and daily-activity ratings.
The real account inspected on 16 October contained one empty draft, not six
completed visits. Its recordings and answers were not changed by these tests.

## What was exercised

| Section | Tasks | Evidence and remaining gap |
| --- | --- | --- |
| Walking / balance | Gait, turning | Two real gait excerpts of one published Parkinson’s case; synthetic landmark tests for turning and hidden rotation across tracking gaps. No matched real turning recording tested. |
| Hand | Left tapping, right tapping, opening/closing | Real research finger-tapping video analysed separately for each side; synthetic hand-opening tests. Source does not document participant diagnosis. |
| Sit-to-stand | Sit-to-stand | Synthetic knee-extension sequence, missing-transition rejection and section navigation. No matched real patient recording tested. |
| Reach / grasp / transfer | Reach, grasp, object transfer | Synthetic movement, visibility and gap tests; reach excludes unsupported knee measurements. No matched real patient recordings tested. Object contact or successful transfer is not detected. |
| Voice / description | Sustained vowel, sentence, natural speech, reviewed text | Real narration through natural-speech processing; all three voice save flows exercised with a generated tone, then a silent failed repeat; reviewed text restored after reopening. A tone does not validate speaking-task completion. No documented Parkinson’s voice tested. |
| Daily activities | Patient ratings and optional note | Saved answers restored, incomplete submission retained, notes isolated between visits, saved report preserved after failure. These are self-reports, not observations inferred from video. |

Every section was opened through an actual login form in a disposable test
database, with every task selector exercised. Test accounts and generated
signals are isolated from the real account. Browser testing additionally
verified the public hand replay and voice result. Webcam acquisition, microphone
hardware, clinical accuracy, and mobile camera reliability are not established
by these automated checks.

## Installed public examples and actual pipeline results

| Example | Result | Details |
| --- | --- | --- |
| Parkinson’s case: outdoor gait | Accepted | 49/60 sampled frames; 81.7% tracking coverage |
| Same case: indoor visual cues | Accepted | 60/60; arm swing withheld because wrist observations are unreliable |
| Research finger tapping: left | Accepted | 177/177; 21 detected cycles, 1.79 Hz cycle-frequency proxy |
| Same recording: right | Accepted | 177/177; 21 detected cycles, 1.79 Hz cycle-frequency proxy |
| Real book narration | Accepted | 14.84 seconds; 69.8% signal-active frames; four internal pauses |

Acceptance refers to recording checks, not diagnosis or measurement accuracy.
There are no independent reference labels for the reported measurements.

Sources and transformations:

- Gait: Schaeffer, Linke and Berg (2016), [“Cueing” for Levodopa-Induced Dyskinesias in Parkinson’s Disease](https://www.frontiersin.org/journals/neurology/articles/10.3389/fneur.2016.00237/full), CC BY 4.0. Publication documents diagnosis and consent for video publication. Two excerpts of the same patient, with medication/cueing and camera limitations; see the earlier demo document for exact excerpt ranges.
- Hand: Narongrit Kasemsap (2025), [Example Video Finger tapping for bradykinesia detection](https://figshare.com/articles/dataset/Example_Video_Finger_tapping_for_bradykinesia_detection/28930706), DOI 10.6084/m9.figshare.28930706.v1, CC BY 4.0. Full original 11.8-second MP4, unchanged; face blurring already present in source. Diagnosis unspecified.
- Speech: Garth Comira, LibriSpeech SLR12 / [librosa example recordings](https://librosa.org/doc/main/recordings.html), `5703-47212-0000`, CC BY 4.0. Full original Ogg decoded to PCM16 WAV at 22050 Hz; no trimming, speed change or denoising. Book narration, not a documented Parkinson’s recording.

SHA-256 hashes, source details, raw results, attributed reports and 3D replays
are stored under
`artifacts/public-recording-checks/20261018T070600870732Z/`.
The originals and source metadata remain in the earlier dated artifact folders.

## Corrections made

- Temporal smoothing, peaks, wrist travel and turning derivatives respect tracking gaps. Time with no observations does not dilute cycle frequency or invent a sit-to-stand transition.
- Double-precision filtering and stable handling of equal peaks remove small numerical artefacts from stationary segments and translated copies of a signal.
- Reach analysis omits knees because the reach task does not require visible legs. Gait arm swing requires usable observations of both arms.
- ADL answers, notes and reviewed text resume from the accepted visit. Text fields use visit-specific keys; incomplete attempts preserve previous accepted results and reports.
- The public demo now supports hash-verified WAV narration as well as body/hand video, with audio-specific metrics and 3D acoustic statistics. Audio never displays a missing-body-joints warning or fabricates a body replay.
- Demo reports use the selected assessment module even when the audio pipeline has a different internal task identifier. Every export carries source and licence attribution.
- Movement feature versions are now `mediapipe_tasks_gait_proxies_v3` and `mediapipe_tasks_proxies_v2`; the demo cache includes this version. Older results remain distinguishable for comparisons.

## Run it yourself

Open `http://127.0.0.1:8501/public-demo` → choose **Public example** →
**Analyze this recording**. For hand/body recordings use **Play**, rotate the
model, or change playback speed. Voice displays acoustic measurements and
statistics. **Download demo report** produces an attributed HTML report;
browser Print → Save as PDF is available.

Roman Urdu: **Example chunein → recording dekhein/sunein → Analyze this recording
dabayein → neeche result, graphs aur report dekhein.** Apni recording ke liye
Welcome → login → Start or resume an assessment → section → task → Upload ya
Live Camera/Microphone chunein. Daily activities mein apne asal jawab dein.

Reproduce the installed public-recording run without patient/database writes:

```sh
.venv/bin/python scripts/check_public_recordings.py
```

This uses the fixed local catalogue, verifies file hashes, and writes a new
timestamped evidence folder. A fresh checkout needs the documented public
media/catalogue installed first; missing files produce an explicit message.

## Verification

- Final targeted regression command: 284 passed, one opt-in official-model test skipped; one upstream Starlette/httpx deprecation warning. It covered section login/navigation, all movement tasks, all voice modes, ADL/text resume, reports, quality guidance, 3D geometry/playback and public media isolation.
- The skipped opt-in test was then run separately with `PARKINSENSE_RUN_MODEL_TESTS=1`: one passed. It checks that blank/noise inputs do not create a person with the real official models. Total: 285 distinct checks passed across the two runs.
- Targeted Ruff checks and `git diff --check` passed.
- Real left-hand demo rendered 177/177 tracked frames; playback progressed from 0.0 through 11.7 seconds and exposed Replay at the end. Fullscreen rendered correctly. Screenshot: `artifacts/all-modules-check-2026-10-16/hand-demo-2026-10-18.png`.
- Real narration played in the browser, passed analysis, and displayed 14.84 seconds, 70% rounded signal activity, four pauses, acoustic limitations, a 3D statistical graph and report control.
- Browser report download verification was blocked by declined browser download permission. No retry or download workaround was used. The separate pipeline run had already generated and verified local attributed reports.

Regression command:

```sh
.venv/bin/python -m pytest tests/test_assessment_sections.py tests/test_movement_task_features.py tests/test_voice_adl_resume.py tests/test_public_demo.py tests/test_vision.py tests/test_gait_feature_visibility.py tests/test_intelligence.py tests/test_3d_studio.py tests/test_live_camera_ui.py tests/test_motion_studio_ui.py tests/test_live_3d.py tests/test_statistical_3d.py tests/test_auto_reports.py tests/test_analysis_feedback_ui.py tests/test_feature_tables.py tests/test_guidance.py tests/test_patient_usability.py -q
```
