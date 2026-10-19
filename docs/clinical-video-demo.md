# Public recording demonstration

Open `http://127.0.0.1:8501/` and choose **Try a public demo — bina login**.

1. Select a gait clip, left/right finger-tapping example, or voice narration. Play the original recording.
2. Press **Analyze this recording** once. Wait for the recording-quality result.
3. Under **3D movement replay**, press **Play**. Drag to rotate, use the time bar to inspect a frame, or choose **0.5×** for slow motion. **Pause** and **Play** continue from the current observation; **Replay** starts again at the end.
4. Choose **Download demo report**. Open the HTML file in a browser and use Print → Save as PDF if needed. The optional **Download the public 3D replay** section prepares a standalone, attributed replay.

Roman Urdu: **Recording chunein → Analyze this recording dabayein → neeche Play se 3D dekhein → Download demo report se report lein.** Apni private recording ke liye Welcome par wapas jaa kar login karein, phir Start Assessment mein task aur Upload/Live Camera chunein.

To start the local application from the repository root:

```sh
bash scripts/run_local.sh
```

The existing database and model setup are required. The demo itself does not create a patient, visit or saved assessment. It accepts only the operator's fixed, hash-verified public catalogue; there is no arbitrary-path or personal-video input on this page. Videos and the catalogue are local artifacts in `artifacts/clinical-video-check-2026-10-16/`, excluded from Git. A checkout without these artifacts displays an installation message instead of an empty or misleading example.

The follow-up coverage of all six sections, hand and voice demos is documented in [assessment-coverage-2026-10-18.md](assessment-coverage-2026-10-18.md).

## Source and actual results — 16 October 2026

Both clips come from Video S1 of Schaeffer, Linke and Berg (2016), [“Cueing” for Levodopa-Induced Dyskinesias in Parkinson’s Disease](https://www.frontiersin.org/journals/neurology/articles/10.3389/fneur.2016.00237/full). The publication describes the participant's Parkinson’s diagnosis and reports consent for video publication. The video is CC BY 4.0. Source credit, licence, excerpt range and transformations accompany the demo and its exports.

| Excerpt | Decoded frames | Valid / sampled frames | Current quality gate |
| --- | ---: | ---: | --- |
| Outdoor, source 7.5–13.5 seconds | 180 | 49 / 60 (81.7%) | ACCEPT |
| Indoor visual cues, source 31.5–37.5 seconds | 180 | 60 / 60 (100%) | ACCEPT |

These are two excerpts of the **same** published case. Each is 6.006 seconds after frame quantization. Both were selected visually before analysis, then processed through `analyze_video(path, "gait")` without lowering gates. Both also ran through the visible Streamlit demo.

The indoor result correctly omits arm swing because wrist tracking is insufficient. The body-quality result alone does not qualify every individual measurement. The screen and report now display this limitation. A preceding public-video test exposed the underlying arm-swing visibility defect; the corrected method is `mediapipe_tasks_gait_proxies_v2`.

No independent reference measurements are available for these excerpts. Cropping, camera movement, short duration and medication/cueing conditions limit interpretation. Tracking coverage is not diagnostic accuracy; differences between these clips do not establish treatment benefit.

## 3D and verification — 16 October 2026

The viewer uses observed MediaPipe world XYZ, with a stylized solid mesh, tapered closed limbs, rounded head, lighting, left/right colours, joint trails and an estimated scale reference. It preserves missing joints and tracking gaps. Hip-centred coordinates do not recover a room-space walking route or calibrated anatomy.

Playback now uses each recorded interval, including irregular samples, and aligns continuation timing after scrubbing or pausing. A tracking interruption is labelled explicitly. Geometry is bounded to 90 replay frames. The legend has room above the scene at the app's narrow browser width.

- 123 targeted tests passed across application flow, gait visibility, reports, statistics, feature tables, 3D geometry, studio controls and the public demo.
- Targeted Ruff and `git diff --check` passed.
- The original outdoor video played to its 6.006-second end without a browser media error.
- Outdoor 3D replay advanced from 1.1 to 5.9 seconds. Indoor 0.5× playback paused at 3.0 seconds, remained there, resumed at 3.1 seconds and reached 5.9 seconds.
- The actual demo report downloaded successfully. Its source credit, excerpt range, licence and unavailable-arm-swing explanation were checked.

Detailed provenance, hashes, original media, the reproducible analysis runner, raw JSON results and attributed reports are in `artifacts/clinical-video-check-2026-10-16/PROVENANCE.md`, `RESULTS.md` and the two per-clip directories. The separate earlier check in `docs/public-video-check-2026-10-15.md` includes an occluded walking video and a dark negative control; those are not Parkinson’s-labelled cases.
