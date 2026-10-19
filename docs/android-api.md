# Android patient API

The native Android app connects to this gateway. The gateway uses the existing
patient accounts, monitoring consent, private storage, measurement pipelines and
saved reports. The web server runs independently and does not need to restart.

## Start on the laptop

From this project directory, run:

```bash
PARKINSENSE_MOBILE_HOST=0.0.0.0 uv run python scripts/run_mobile_api.py
```

The default port is `8767`. Set `PARKINSENSE_MOBILE_PORT` to change it. The normal
default host is `127.0.0.1`; the command above explicitly makes the gateway
available to a phone on the same private Wi-Fi network. Set the Android app's
server address to `http://<laptop-Wi-Fi-address>:8767`. The laptop must stay on and
the gateway must keep running. A public deployment needs an HTTPS origin.

No password is embedded in the APK. Existing patients sign in with their web
email and password. New patients use Register in the app. Registration requires
the patient's explicit monitoring consent. The server accepts passwords from
10 to 128 characters; the Android registration screen requires at least 12.

## Session security

Authentication returns an HMAC-signed bearer session with a random 256-bit nonce
and a 12-hour expiry. The server generates its private signing key at
`<private-storage>/mobile-api.key` with mode `0600`. It can instead use a
`PARKINSENSE_MOBILE_SECRET` environment value of at least 32 bytes. The key is
never sent to the phone or included in source, logs or reports.

`<private-storage>/mobile-api-sessions.sqlite3` stores only issued nonce hashes
and expiry times. Sign-out deletes the current nonce durably, including across
server restarts. Other mobile devices and current web sessions stay signed in.
Every protected request also checks the existing active patient account and
password-reset session revision. Tokens must appear in the `Authorization`
header, never in a URL. Responses carry `Cache-Control: no-store`.

## Contract

All endpoints except `/health`, `/auth/register` and `/auth/login` require:

```text
Authorization: Bearer <access_token>
```

| Method | Path | Request or result |
| --- | --- | --- |
| GET | `/health` | `{status:"ok",application:"ParkinSense PK"}` |
| POST | `/auth/register` | `{full_name,email,password,language,consent:true}` |
| POST | `/auth/login` | `{email,password}` |
| POST | `/auth/logout` | Sign out the current mobile session |
| GET | `/profile` | Own identity and `monitoring_consent:{active,versions}` |
| POST | `/profile/consent` | `{acknowledged:true}` to resume monitoring, or `false` to withdraw |
| GET | `/sessions` | Own sessions, newest first |
| POST | `/sessions` | Create own draft; send `{}` |
| GET | `/sessions/{id}` | Own session, modules and safe media identifiers |
| POST | `/sessions/{id}/notes` | `{text}`; 3–5,000 characters |
| POST | `/sessions/{id}/activities` | `{responses,other_difficulty?}`; complete nine activities |
| POST | `/sessions/{id}/video` | Multipart `file` and movement `task` |
| POST | `/sessions/{id}/audio` | Multipart WAV `file` and voice `task` |
| POST | `/sessions/{id}/complete` | Complete own draft with an accepted saved module |
| GET | `/sessions/{id}/report` | Own patient summary, sections, measurements and limitations |
| GET | `/sessions/{id}/media/{file_id}` | Own recording; current monitoring consent required |

Registration and login return:

```json
{
  "access_token": "<private bearer session>",
  "token_type": "bearer",
  "expires_in": 43200,
  "user": {
    "id": "<user UUID>",
    "full_name": "Patient name",
    "email": "patient@example.test",
    "role": "patient",
    "language": "English",
    "patient_id": "<patient UUID>"
  }
}
```

Supported languages are `English`, `Urdu`, `Pashto`, `Mixed` and `Roman Urdu`.
Activity response keys are `dressing`, `feeding`, `grooming`, `bathing`,
`writing`, `phone_use`, `walking`, `transfers` and `household_activities`.
Each answer must be an integer from 0 to 4. These are personal self-reports.

Movement tasks are `gait`, `turning`, `finger_left`, `finger_right`,
`hand_open_close`, `sit_to_stand`, `reach`, `grasp` and `object_transfer`.
MP4, MOV, AVI and MKV are supported, subject to the existing decoder and
landmark quality checks. Video is limited to 45 seconds, 100 MB and 4K. The
configured `PARKINSENSE_MAX_UPLOAD_MB` can impose a smaller size limit. Voice
tasks are `vowel`, `sentence` and `natural`; WAV clips are limited to 180
seconds and 72 MB. The vowel minimum is 2 seconds; other voice tasks require
3 seconds. The app records bounded clips and sends them after the patient
chooses Upload and analyse.

During recording, the native Live Checker measures camera lighting/frame
change or microphone signal level on the phone. These immediate recording
checks are shown separately from saved server measurements. Saved videos use
the same MediaPipe task pipeline as the web application; saved voice clips use
the same local acoustic pipeline. No diagnosis, Parkinson severity or
automatic transcription is inferred.

Upload results have `{accepted,result,session}`. An accepted result is saved
with its recording and generates a patient report. A failed quality attempt
returns its result for the patient to review, deletes the temporary recording,
and adds no saved module or media. Sessions return only media IDs, types,
modules, sizes and dates; private storage paths are never exposed.

Error responses contain `{detail:"message"}`. `401` means sign-in is needed,
`403` means ownership or consent prevented the action, `404` means the record
is unavailable, `413` means a size limit was exceeded, `422` means invalid
input and `429` means wait before retrying. Auth attempts are limited per IP
address and operation. Decoder and measurement work is bounded; only one
mobile recording is analyzed at a time.

## Verification

The isolated test suite uses temporary SQLite databases and generated WAV
signals. It checks patient registration and ownership, existing password-reset
revision enforcement, durable per-device sign-out, consent withdrawal, real
acoustic analysis, authenticated media, input limits, failed attempt cleanup,
error privacy and signing-key permissions.

```bash
uv run pytest tests/test_mobile_api.py -q
```

No real patient database, recording or credential is used by these tests.
