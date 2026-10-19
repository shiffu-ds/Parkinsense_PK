# Android APK verification — 4 October 2026

Built the standalone native patient preview with JDK 21, Android SDK 36,
build-tools 36.0.0, AGP 8.10.1 and checksum-pinned Gradle 8.13. The actual
reproducible command `bash scripts/build_android_apk.sh` completed successfully.

## Delivered artifact

- Project artifact: `artifacts/ParkinSense-PK-preview.apk`
- Easy-transfer copy: `/home/shaiby/Downloads/ParkinSense-PK.apk`
- Package: `org.parkinsense.pk.preview`
- Version: `0.3.0-preview-local`, code 3
- Minimum Android: API 26 / Android 8.0; target API 36
- Size: 5,273,949 bytes (5.03 MiB)
- ABIs: arm64-v8a, armeabi-v7a, x86, x86_64
- SHA-256: `7e5b707f7acbba55fe540ac853d290915cde52cf7dcf47d8778eda29b9793684`

`apksigner verify` confirms an APK Signature Scheme v2 signature with one
signer. This is the signed development preview, not a production store release.
`aapt dump badging` confirms the package, SDK requirements, launcher and camera,
microphone and internet permissions. The APK includes its Java Dex program and
native camera libraries. No private project environment, signing key, session
registry or database files were bundled. The Downloads copy matches the
project artifact's SHA-256. All current Java sources were compiled before the
artifact was copied.

## Automated checks

- Android `assembleDebug`, `testDebugUnitTest` and `lintDebug`: passed.
- 12 native unit tests: passed (seven measured-signal checks and five server
  origin/security checks).
- Android lint: zero errors; 33 non-blocking warnings, including dynamic UI
  text/localisation, deliberate synchronous token persistence and preview
  network policy. The pinned build tool emits an SDK XML/deprecation warning;
  packaging and verification still succeed.
- Full Python suite: 356 passed, four environment-dependent tests skipped.
- Final patient API suite: 11 passed, including streamed oversized-upload
  cleanup added during review.
- Vision tests with `PARKINSENSE_RUN_MODEL_TESTS=1`: 14 passed. They exercise
  real model loading and blank-clip rejection; they do not establish clinical
  accuracy or acceptance of a patient's recording.
- Repository Ruff and `git diff --check`: passed.

API tests use isolated temporary SQLite databases, synthetic signals and test
accounts. They do not read or change the existing patient database or records.
A test-client dependency deprecation warning remains; the checks pass.

The new patient gateway starts independently of the existing web services.
`/health` returns 200 on both loopback and the laptop's Wi-Fi address,
`192.168.1.11:8767`; anonymous `/profile` access returns 401. Responses use
`Cache-Control: no-store`. Existing web/media services on 8501/8503 remain
running. No default patient password is embedded or created.

## Checks on the intended phone

No physical phone or emulator UI run was performed. Install the APK on the
intended Android phone and keep it on the same Wi-Fi as the laptop. Register
or sign in with a patient email, try microphone recording, then camera
recording, review/discard/upload, and verify accepted analysis appears in
History. Also check denied permissions and backgrounding during capture.
CameraX supports depend on the phone's hardware; an unsupported combination
shows an error and permits selecting an existing recording.

The app's live camera and microphone values are recording-quality signals.
Detailed saved analysis uses the laptop's existing measurement pipelines.
These values do not diagnose Parkinson's disease or measure clinical severity.
The laptop gateway/database must stay running for account access, uploads and
saved analysis. See [installation instructions](mobile-android.md).
