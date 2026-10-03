# Patient recording and language usability

The patient interface follows the language saved in **Profile**. English, Urdu
script and Roman Urdu have local, fixed product copy. Changing the profile
language applies on the next rerun; recording task IDs, file associations and
the 0–4 daily-activity response values remain unchanged.

## Implemented

- The home page, assessment hub, profile, movement capture, voice capture and
  daily-activity form use the patient's saved language. Staff workflows retain
  English. Other existing preferences, including Pashto and Mixed, receive an
  explicit English instruction fallback rather than an implied translation.
- All nine movement tasks have three numbered steps covering preparation,
  the actual task and stopping. Instructions retain the task's existing local
  minimum duration and 45-second video limit. Usual assistance and stopping
  when a task is uncomfortable or unsafe remain explicit.
- All three voice tasks have a prompt. The fixed sentence follows the selected
  **speech language**, independently of the interface language, and instructs
  patients to use the same sentence and language across visits. Vowel copy asks
  for a comfortable three-second recording; the existing decoder minimum is
  unchanged. Automatic transcription remains clearly labelled unavailable.
- Daily activities include translated wording for every item and all five
  answer choices. Unanswered items remain unanswered, never silently zero.
  The custom questionnaire is still identified as clinically unvalidated.
- All 33 existing fault-guidance codes have fixed native Urdu titles, reasons
  and three steps. English/Roman Urdu text and fault classification are retained.
  Follow-up about a reported fall or freezing still requires explicit accepted
  self-report evidence; camera measurements do not create those findings.
- Native Urdu prose has explicit `lang="ur"`, RTL direction and escaped HTML.
  Product buttons, labels and form controls use readable local font fallbacks.
  The app downloads no fonts and sends no content to a translation service.
  Scientific graphs keep their own left-to-right coordinate layout.
- Native action buttons, radio/checkbox labels and key entry/select controls
  have 48-pixel minimum touch targets. Long labels wrap. Main columns stack
  below 720 pixels so recording and tracking panels fit narrow viewports.

## Mobile camera path

Patients can choose an automatic, front or rear lens preference. It requests
`user` or `environment` facing mode using an **ideal** constraint, allowing the
browser to use another available lens. The instructions explain the camera
device selector and recommend keeping the same lens across repeat visits.
The camera requests ideal 1280×720 resolution and 30 fps, caps capture at 30 fps,
uses inline playback and does not request microphone access for movement tasks.
These browser preferences do not prove that a physical camera supplies the
requested resolution, frame rate or measurement accuracy.

WebRTC start/stop, device choice and camera-permission errors have Urdu and
Roman Urdu translations. **Camera START** connects the preview. **Start
recording** creates the current clip. **Finish & analyze** stops that clip and
opens its analysis. Camera **STOP** ends the connection; it is not the analysis
action. Existing retained-clip handling keeps a completed recording available
after a disconnect.

A phone opening the app over the network needs a secure HTTPS origin and
browser permission for live camera access. Localhost is a browser secure-context
exception on the machine running it; opening a laptop's plain HTTP LAN address
on a phone does not inherit that exception. When live capture is unavailable,
the instructions direct patients to record with their normal camera app and
upload the complete, upright, normal-speed clip. These requirements follow
[MDN's getUserMedia documentation](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
and the [streamlit-webrtc HTTPS guidance](https://github.com/whitphx/streamlit-webrtc#https).

## What verification establishes

`tests/test_patient_usability.py` checks complete task/item/choice catalogs,
all three interface languages, stable numeric ADL storage, unanswered answers,
profile persistence, selected speech-language prompts, escaped RTL prose,
all Urdu fault codes and evidence gates, and front/rear browser constraints.
Camera tests replace WebRTC with an inert context; they never access a camera
or microphone. CSS tests check the intended touch, wrapping and stacking rules.
These automated checks are not physical-phone recording or clinical validation.

## Clinic-pilot release checks

Before treating the Urdu copy as suitable for a clinic, ask a bilingual clinician
and intended patient users to review the instructions, left/right wording,
stop directions and daily-activity answer meanings. Record misunderstandings,
changes, reviewer names and the approved copy version. This is a product
translation review; it does not validate the custom ADL scale or turn the
current measurements into a medical diagnosis.

Test the actual deployment on representative Android Chrome and iPhone Safari
devices over HTTPS. Record device/browser versions, front/rear lens selection,
portrait/landscape layout, permission denial, camera interruption, repeat
attempts, keyboard/input readability, long Urdu labels, task completion and
report access. Observe whether patients can complete the flow without staff
help, where they pause, and whether clinician review is understandable. Measure
real capture frame gaps and recording quality rather than reporting requested
browser settings as achieved device performance. A real phone/device pilot and
independent accuracy study remain separate work requiring representative
recordings and real participants.
