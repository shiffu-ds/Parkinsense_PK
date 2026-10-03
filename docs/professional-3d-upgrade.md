# Professional movement and care upgrade — 3 October 2026

This upgrade follows the request for a more professional, human-centered app with a genuine 3D movement review. The research below informed the product choices; it is not clinical validation or an endorsement by those organizations.

## Implemented

| Area | Result | Basis and practical limits |
|---|---|---|
| 3D movement studio | Solid articulated body/hand meshes, joint skeleton option, orbit/zoom, front/side/top/isometric camera views, time scrubber, play/pause and speed controls | Uses model `world_landmarks` XYZ only. Image-normalized coordinates are never substituted for missing world geometry. |
| Joint trails | Select a wrist, fingertip, knee, hip or ankle, or use task-specific trails | Trails break at visibility/tracking gaps. Body coordinates are hip-local and hands are hand-local; a room-scale walking/wrist path is not available. |
| First-recording comparison | Optional muted baseline overlay at the same estimated-meter scale | Requires compatible task/method/hand side and usable 3D data. Initial origins align; recording progress matches relative time. This is a visual aid, not a validated change score. |
| Offline replay | Explicitly prepare and download a self-contained HTML viewer | Plotly JavaScript is bundled locally, with no CDN dependency. Exports omit identity, raw videos and private prose but contain sensitive movement geometry. Changing the result/options requires preparing again. |
| Live preview | Separate 3D observation panel beside the camera workflow | Camera output defaults to no 2D landmark overlay. Final measurements still pass through the recording quality checks; live display is not a clinical result. |
| My Care | Dated energy/sleep/movement/mood check-ins, optional falls and a free note | All four ratings require explicit answers. Unknown falls remain unknown. One entry per patient/day is updated rather than duplicated. No combined severity score is calculated. |
| Personal goals | Patient-written priorities with in-progress/completed/paused status | Goals express the patient's own priorities. They are not automatically prescribed activities. |
| Patient follow-up | Clinician-written notes and optional planned review date | Actual author and date are shown. Assigned clinicians write; patients read. A review date is not a booked appointment or an external reminder. |
| Interface | Original code-drawn movement mark, restrained navy/teal/ivory palette, visible field boundaries, clear workflow states and conversational copy | Native controls retain their semantics. Dynamic custom HTML is escaped. No generated stock imagery, fictional care team or AI-written care plan is used. |

## Research and decisions

[Parkinson's Foundation: Tech Tools for Daily Living](https://www.parkinson.org/living-with-parkinsons/management/tech-tools) describes daily symptom tracking, goals and care-team coordination as digital-tool categories. That informed the daily context, personal goal and clinician follow-up pages. We chose explicit self-report and human authorship; the questions are custom wellbeing prompts rather than a validated Parkinson instrument.

[Google's pose landmark documentation](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python) distinguishes image-normalized XYZ from world landmarks around the hip midpoint. [Its hand landmark documentation](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python) gives a hand-center origin for world XYZ. The renderer now requires those world landmarks, preserves their estimated-meter scale, and maps the vertical axis upward. Single-camera depth remains estimated, and the upstream local origins prevent a calibrated global trajectory.

[Plotly's camera documentation](https://plotly.com/python/3d-camera-controls/) and [Mesh3d reference](https://plotly.com/python-api-reference/generated/plotly.graph_objects.Mesh3d.html) informed the camera presets and solid WebGL geometry. Tubes, joint spheres and torso/palm shells are stylized geometry around observed joints; they do not reconstruct skin, body shape or object contact.

## Data and verification

Three additive tables (`daily_checkins`, `personal_goals`, `care_plans`) preserve the existing assessment schema and records. Every care service repeats active-actor, ownership/assignment and consent checks. Administrators receive no access to private care context. Revoking a clinician link removes their read/write access. Audit metadata excludes patient notes and goal prose.

Replay limits are fixed across animation, and at most 90 display frames enter a replay. Display smoothing is optional and gap-aware; it does not modify stored observations or feature extraction. Finite/visibility filtering masks unusable joints instead of inventing coordinates.

See [verification.md](verification.md) for actual test and browser evidence. Developer preview geometry exists only in an isolated test database and ignored artifacts; it does not enter real patient records. Clinical validation and calibrated room-scale motion capture remain separate acceptance requirements.
