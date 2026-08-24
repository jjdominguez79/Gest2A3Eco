#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-https://gest2a3eco-production.up.railway.app}"
ENVIRONMENT="${ENVIRONMENT:-production}"
PLATFORM="${1:-}"
SKIP_CHECKS="${SKIP_CHECKS:-0}"
ALLOW_NON_MAIN="${ALLOW_NON_MAIN:-0}"

usage() {
  cat <<'EOF'
Uso: ./tool/build_production.sh <android|apk|web|web-deploy|ios|macos|all>

Ejemplos:
  ./tool/build_production.sh android      # AAB para Google Play
  ./tool/build_production.sh apk          # APK release para instalación manual
  ./tool/build_production.sh web          # compila web sin publicar
  ./tool/build_production.sh web-deploy   # compila y publica Firebase Hosting
  ./tool/build_production.sh ios          # IPA para App Store/TestFlight (solo macOS)
  ./tool/build_production.sh macos        # app macOS (solo macOS)

Variables opcionales:
  API_BASE_URL=https://api.gestinem.es
  SKIP_CHECKS=1        omite analyze/test
  ALLOW_NON_MAIN=1     permite ejecutar fuera de main
EOF
}

[[ -n "$PLATFORM" ]] || { usage; exit 2; }
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

command -v flutter >/dev/null || { echo "ERROR: Flutter no está instalado o no está en PATH."; exit 1; }

branch="$(git branch --show-current 2>/dev/null || true)"
if [[ "$branch" != "main" && "$ALLOW_NON_MAIN" != "1" ]]; then
  echo "ERROR: Estás en la rama '$branch'. Para producción usa main."
  echo "Si sabes lo que haces: ALLOW_NON_MAIN=1 ./tool/build_production.sh $PLATFORM"
  exit 1
fi
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
  echo "ERROR: Hay cambios sin guardar. Haz commit/stash antes de un build de producción."
  exit 1
fi

flutter pub get
if [[ "$SKIP_CHECKS" != "1" ]]; then
  flutter analyze
  flutter test
fi

DEFINES=(--dart-define="API_BASE_URL=$API_BASE_URL" --dart-define="ENVIRONMENT=$ENVIRONMENT")

check_android_signing() {
  [[ -f android/key.properties ]] || { echo "ERROR: falta android/key.properties."; exit 1; }
}

build_one() {
  case "$1" in
    android)
      check_android_signing
      flutter build appbundle --release "${DEFINES[@]}"
      echo "OK: build/app/outputs/bundle/release/app-release.aab"
      ;;
    apk)
      check_android_signing
      flutter build apk --release "${DEFINES[@]}"
      echo "OK: build/app/outputs/flutter-apk/app-release.apk"
      ;;
    web)
      flutter build web --release "${DEFINES[@]}"
      echo "OK: build/web"
      ;;
    web-deploy)
      command -v firebase >/dev/null || { echo "ERROR: Firebase CLI no está instalado. Ejecuta: npm install -g firebase-tools"; exit 1; }
      flutter build web --release "${DEFINES[@]}"
      firebase deploy --only hosting --project gest2a3eco
      echo "OK: web publicada en Firebase Hosting."
      ;;
    ios)
      [[ "$(uname -s)" == "Darwin" ]] || { echo "ERROR: iOS solo puede compilarse en macOS."; exit 1; }
      flutter build ipa --release "${DEFINES[@]}"
      echo "OK: revisa build/ios/ipa/"
      ;;
    macos)
      [[ "$(uname -s)" == "Darwin" ]] || { echo "ERROR: macOS solo puede compilarse en macOS."; exit 1; }
      flutter build macos --release "${DEFINES[@]}"
      echo "OK: revisa build/macos/Build/Products/Release/"
      ;;
    *) usage; exit 2 ;;
  esac
}

if [[ "$PLATFORM" == "all" ]]; then
  build_one android
  build_one web
  if [[ "$(uname -s)" == "Darwin" ]]; then
    build_one ios
    build_one macos
  fi
else
  build_one "$PLATFORM"
fi
