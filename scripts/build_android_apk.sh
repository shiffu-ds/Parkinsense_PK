#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANDROID_HOME="${ANDROID_HOME:-$TASK_ROOT/.tooling/android-sdk}"
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
export ANDROID_HOME JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-$TASK_ROOT/.tooling/gradle-cache}"
if [[ ! -f "$ANDROID_HOME/platforms/android-36/android.jar" ]]; then
  echo "Install Android SDK Platform 36 and Build Tools 36.0.0; set ANDROID_HOME to your SDK." >&2
  exit 1
fi
cd "$TASK_ROOT/mobile/android"
./gradlew assembleDebug testDebugUnitTest lintDebug --no-daemon --max-workers=2
mkdir -p "$TASK_ROOT/artifacts"
cp app/build/outputs/apk/debug/app-debug.apk "$TASK_ROOT/artifacts/ParkinSense-PK-preview.apk"
"$ANDROID_HOME/build-tools/36.0.0/apksigner" verify --verbose "$TASK_ROOT/artifacts/ParkinSense-PK-preview.apk"
sha256sum "$TASK_ROOT/artifacts/ParkinSense-PK-preview.apk"
echo "APK: $TASK_ROOT/artifacts/ParkinSense-PK-preview.apk"
