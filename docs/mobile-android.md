# ParkinSense PK Android preview

The APK is a standalone native Java Android patient app. It uses the phone camera and microphone directly; it does not open a web page or require Expo, Metro or a development client. Android 8.0 or later is required.

The complete app follows a dark theme. It provides registration and login with the same patient accounts as the web application, a patient dashboard, personal history and reports, daily activity ratings, personal notes, consent controls and logout. There are no staff or Research screens in the Android app.

## Install and connect

1. Transfer `artifacts/ParkinSense-PK-preview.apk` to your Android phone, open it and allow installation from the file app when Android asks.
2. Keep the laptop and phone on the same trusted Wi-Fi. Start the existing database if needed, then the patient API:

   ```bash
   cd "/home/shaiby/Parkinsense PK"
   docker compose --env-file .env -f infra/compose.yaml -p parkinsense_pk up -d --wait db
   PARKINSENSE_MOBILE_HOST=0.0.0.0 uv run python scripts/run_mobile_api.py
   ```

3. Open **ParkinSense PK**, then **Server connection**. The preview defaults to `http://192.168.1.11:8767`. If the laptop's Wi-Fi IP changes, enter its current address and port `8767`.
4. Register a personal account or log in using your existing patient email and password. No shared password or server signing key is bundled in the APK.

The laptop API and database need to stay running for login, uploads, analysis and history. A deployed server can be used by entering its HTTPS origin. Public HTTP addresses, embedded credentials, query strings and URL paths are rejected. Changing the server signs out this phone before the new connection is used. The APK is a local development preview, not a Play Store release.

## Live Checker and saved analysis

Choose **Start Live Checker** and a movement or voice task. The recorder gives task instructions and requests the relevant device permission after **Start live recording**.

- **Movement:** a real CameraX preview and MP4 recording run together with live image analysis. Brightness, contrast, edge detail and pixel change update approximately twice per second. Pixel change includes camera motion; it is not a body landmark measurement or symptom score.
- **Voice:** Android AudioRecord creates a mono 16 kHz WAV recording. Real microphone RMS level, clipping and silence are displayed during recording.
- Recording stops at 45 seconds; movement recordings are additionally bounded to 30 MB. Clips remain in private temporary storage. **Stop**, **Use recording**, review/playback, **Upload and analyse**, retry and **Discard** are separate controls. Leaving the recorder or backgrounding it releases the hardware and discards unused capture.
- Existing MP4 or WAV recordings can be selected with the Android file picker. They are copied into temporary app storage with a 100 MB cap and require the same explicit upload step.

Live recording signals are calculated on the phone without a server connection. After the patient chooses **Upload and analyse**, the server runs the existing movement or voice analysis. Only recordings accepted by its quality checks enter the personal session. Daily check-ins and notes can join the same session. **Finish and view report** produces a personal report with measured values, compatible earlier reference differences and the patient's own activity responses.

These are technical measurements for personal monitoring. They do not diagnose Parkinson's disease, quantify clinical severity or recommend treatment. Setup and recording conditions can affect comparisons.

## Privacy and preview boundaries

Tokens are encrypted with AES-GCM using an Android Keystore key. App backups are disabled. Bearer tokens are bound to the configured origin and requests do not follow redirects. Server changes and logout clear local authentication and invalidate pending callbacks. Screens prevent system screenshots to reduce accidental exposure of personal data. Forgotten temporary captures older than 24 hours are purged without deleting a fresh pending camera result.

The debug preview permits private Wi-Fi HTTP through its Android network configuration; the API client rejects public HTTP. Use trusted Wi-Fi for the local preview and HTTPS with a system-trusted certificate for remote use. Release build network configuration requires HTTPS. Personal data is stored by the configured server, not inside the APK. Withdrawing monitoring consent prevents new saved monitoring; it does not automatically remove existing saved records.

Physical phone installation, camera compatibility, microphone permission behaviour and recording quality must still be checked on the intended device. No physical device or emulator UI verification has been claimed. Linux does not produce an iPhone installation package; this artifact is for Android.

## Build locally

JDK 21, Android SDK platform 36 and build-tools 36.0.0 are used. The project pins AGP 8.10.1, Gradle 8.13, CameraX 1.5.3 and the required AndroidX dependencies. The checked-in Gradle wrapper verifies the Gradle distribution SHA-256.

```bash
cd "/home/shaiby/Parkinsense PK/mobile/android"
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
ANDROID_HOME="/home/shaiby/Parkinsense PK/.tooling/android-sdk" \
./gradlew --no-daemon :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

`app/build/outputs/apk/debug/app-debug.apk` is a signed development preview with application ID `org.parkinsense.pk.preview`. It embeds the complete Java app and needs no additional mobile development server. Production signing, Play Store publishing and public server deployment are separate actions.

Build, signature, test results and remaining hardware checks are recorded in [APK verification](android-verification.md).
