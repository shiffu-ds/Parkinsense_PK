# 3D statistics, patient reports and fault guidance

Implemented on 3 October 2026. These features use the existing authorized patient and linked-clinician workflow.

## Statistical review

| Analysis | 3D graph | Source |
|---|---|---|
| Walking, turning, left/right tapping, hand opening/closing, sit-to-stand, reach, grasp, transfer | Time × measurement series × observed value; scalar summary where available | Accepted movement features and extracted curves |
| Sustained vowel, fixed sentence, natural speech | Measurement × analysis × value | Accepted acoustic features, grouped into seconds, dBFS, Hz, fractions, counts or MFCC coefficient units |
| Daily-life description | Activity × analysis × rule result, or matched-domain count | User-entered transcript and dictionary rules |
| Daily activities | Activity × analysis × reported difficulty | Explicit answers on the custom, unvalidated 0–4 scale |
| Progress and compatible visit history | Visit × measurement × value | Accepted results with the same task, method and language |

Graphs are Plotly `Scatter3d` and explicitly triangulated `Mesh3d` boxes. The studio's body/hand replay continues to use observed world XYZ. Unit, statistical-view and camera controls are available where the corresponding data exist. Progress opens with visit history when available.

Only finite numeric, non-boolean data with explicit acceptance contribute. A contradictory rejection overrides a positive acceptance field. Unknown-unit features have separate labelled groups. Legitimate zero and negative values remain visible. Blank, rejected, abandoned or incompatible visits do not become zero values or connected trends. Movement gaps remain gaps, including when display curves are reduced to at most 300 actual samples per series. Descriptive tables use all finite extracted samples and population standard deviation; the display sampling does not create new observations.

## Patient report

Saving a module and updating its current automatic report share one database transaction. Reanalysis updates the same report row. Separate manual summaries retain their historical revision provenance. Ordinary reads do not regenerate reports.

The report contains the task's accepted measurements and units, an earlier compatible reference when one exists, explicit questionnaire answers, transcript-rule readings, recording checks, missing modalities, limitations, and actual clinician review/context. The report records module revisions and references; changes require a current report before sharing. No disease score, normal range, diagnosis, inferred improvement, or medicine change is generated from these measurements.

Reports can be read in **Reports**, downloaded as standalone printable HTML, or exported as structured JSON. The HTML escapes patient prose, uses no JavaScript/CDN, and supports browser Print → Save as PDF. Detailed tables are in English; supported summary/guidance templates include Roman Urdu, and unsupported guidance languages disclose the fallback. Translations still require clinical language review for deployment.

A movement draft or failed form/recording attempt can download an **unsaved analysis attempt preview**. Rejected attempts contain canonical quality reasons and numbered retry instructions, with no measurement values. An accepted auto-saved voice/form result downloads the saved report. Failed replacements preserve earlier saved evidence and appear separately as the latest attempt.

## Numbered guidance

The fixed local catalogue handles short/long clips, poor light, blur, crop/visibility, wrong hand, camera gaps, missing recordings, silent/clipped audio, unsupported formats, missing model/runtime dependencies, unconfigured ASR, empty transcripts and unanswered ADL items. It gives the specific next steps instead of exposing decoder messages, private paths or stack traces.

Fall/freezing follow-up is shown only for explicitly reported concerns in accepted reviewed text. Negation and mentioned-only entities prevent a follow-up flag from being treated as a new report. Recording geometry and acoustic values do not diagnose a clinical fault. No patient data or transcript is sent to an internet search or external AI service.

## Primary sources consulted

- [Plotly 3D line plots](https://plotly.com/python/3d-line-plots/) and [3D mesh documentation](https://plotly.com/python/3d-mesh/) support the graph primitives and camera handling.
- [Google MediaPipe pose guide](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python) and [hand guide](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python) support world-landmark/model setup wording.
- [Parkinson's Foundation: preparing for care visits](https://www.parkinson.org/living-with-parkinsons/finding-care/making-the-most) informed the emphasis on patient concerns and clinician discussion.
- [Parkinson's Foundation: freezing](https://www.parkinson.org/library/fact-sheets/freezing) and [fall prevention](https://www.parkinson.org/sites/default/files/documents/Fall-Prevention-2024.pdf) support the linked patient-reported-concern guidance.

Software verification is recorded in `verification.md`. Synthetic browser fixtures are clearly labelled and isolated from the normal PostgreSQL database. Software tests do not demonstrate clinical prediction accuracy.
