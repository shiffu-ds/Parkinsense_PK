# Focused live 3D movement tracking

The live capture page now enables focused camera lines by default and displays a separate current-frame 3D view. Camera startup is asynchronous: a polling fragment is registered even when the video processor is initially absent, and each tick reads the current processor rather than a captured previous instance.

## Patient controls

1. Select the matching movement task and **Live Camera**.
2. Press the camera's **START** button and allow camera access in your browser. Audio is disabled for movement capture.
3. Keep the required joints visible in even lighting. Reach requires the torso and hips as well as shoulders, elbows and wrists; hand tasks require the full selected hand. Left/right tasks refer to the patient's anatomical side.
4. **Show focused joint lines on camera** and **Show short movement trails** start enabled. Choose Front, Side, Top or Isometric for the adjacent 3D view, or drag it to rotate.
5. Choose **Start recording**, then **Finish & analyze**. A clip that reaches the 45-second cap remains available for analysis. A camera interruption retains the current clip for review within the same visit/session, without displaying its old geometry. If the camera reconnects before review, finish the pending clip before starting another recording.
6. Review recording-quality guidance and accepted measurements before saving. Existing report generation and statistics run after accepted analysis/save.

## Task focus

| Task | Bright joints and lines | Short trails |
|---|---|---|
| Finger tapping, left/right | Selected thumb, index finger and wrist | Thumb/index fingertips |
| Hand opening/closing | Palm and all five fingers | Five fingertips |
| Grasp / object transfer | Selected hand and fingers | Thumb/index/middle fingertips |
| Reach | Shoulders, elbows and wrists | Wrists |
| Walking/gait | Hips, knees, ankles and feet | Ankles |
| Sit-to-stand | Shoulders, hips, knees and ankles | Hips/knees |
| Turning | Shoulders, hips, knees and ankles | Shoulders/hips |

Other observed joints use restrained context lines. Focused lines use teal/blue depth colors, a soft glow and visible joint centers.

## Geometry, freshness and recording

Camera lines are projected onto the detected image X/Y coordinates; their depth colors come from world Z. The adjacent viewer uses genuine MediaPipe world XYZ estimates, in meters, with the existing Y-axis reflection for an upright display. It has stable metric axes and shows the latest observation immediately, with no saved-replay timeline. Body geometry is relative to the hips; hand geometry is relative to the hand center. Trails therefore show recent local articulation, not calibrated travel through a room.

World coordinates must be finite and confident. Offscreen joints, low-confidence detections, the wrong selected hand and missing world landmarks suppress geometry; no substitute skeleton is created. Trail history is limited to 45 observations over at most three seconds. Tracking loss, a camera gap or a hand switch clears the continuous sequence. Polling expires observations after a 0.35-second pause even when no further video frame arrives. Individual occlusions remain breaks in their trails.

Detection is scheduled at most every 0.1 seconds; the UI polls at 0.25 seconds. These are refresh settings, not a guaranteed device frame rate. Media callbacks never call Streamlit and state exchanges use a lock and detached snapshots. Overlay rendering blends at most three fading trail layers, plus context and focus glow. Raw frames are recorded before overlays, so neither lines nor labels enter final video analysis or alter saved measurements.

The live chart uses a persistent Streamlit V2 component and `Plotly.react`. Its WebGL canvas survives changing landmark payloads; slow renders discard intermediate display updates and keep the latest frame. Updates pause during a drag, camera state uses a stable revision, and unmount releases listeners/observers/WebGL resources. The installed offline Plotly library loads outside the polling fragment and no external script/CDN receives coordinates.

## Sources and validation

The lifecycle follows the official [streamlit-webrtc threading/state guidance](https://github.com/whitphx/streamlit-webrtc), [Streamlit fragment API](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment) and [Streamlit V2 component API](https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v2.component). Persistent figure updates use the documented [Plotly function API](https://plotly.com/javascript/plotlyjs-function-reference/). World/image coordinates and handedness follow the [MediaPipe hand landmarker documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python) and [pose landmarker documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python).

Regression tests cover live startup/reconnection, task focus, world-coordinate requirements, freshness/gaps/occlusion, display controls, recording readiness and raw-frame preservation. Browser QA uses the production movement page with explicitly synthetic camera pixels and coordinates in a separate database. It does not access the user's camera or establish detector accuracy on patients. See `verification.md` for observed test results.
