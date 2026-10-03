#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-https://gest2a3eco-production.up.railway.app}"
ENVIRONMENT="${ENVIRONMENT:-production}"
FIREBASE_WEB_VAPID_KEY="${FIREBASE_WEB_VAPID_KEY:-}"
PLATFORM="${1:-}"
SKIP_CHECKS="${SKIP_CHECKS:-0}"
ALLOW_NON_MAIN="${ALLOW_NON_MAIN:-0}"
SHARED_INSTALLER_DIRECTORY="${SHARED_INSTALLER_DIRECTORY:-${GEST2A3ECO_DOCUMENT_REPOSITORY_DIR:-//GestinemMain/Doc_Compartidos/Gest2A3Eco}}"
PLAY_UPLOAD="${PLAY_UPLOAD:-0}"
PLAY_TRACK="${PLAY_TRACK:-internal}"
PLAY_SUBMIT_REVIEW="${PLAY_SUBMIT_REVIEW:-0}"
GOOGLE_PLAY_CREDENTIALS_PATH="${GOOGLE_PLAY_CREDENTIALS_PATH:-}"

usage() {
  cat <<'EOF'
Uso: bash tool/build_production.sh <android|apk|web|windows|ios|macos>

Comandos:
  android   genera el AAB firmado para Google Play
  apk       genera un APK firmado para instalación manual
  web       compila, valida y publica https://app.gestinem.es
  windows   genera el instalador y lo copia a Documentos compartidos
  ios       genera el IPA para App Store Connect (solo macOS)
  macos     genera la aplicación macOS (solo macOS)

Variables opcionales:
  API_BASE_URL=https://api.gestinem.es
  FIREBASE_WEB_VAPID_KEY=<clave-publica>  evita consultar Railway
  SHARED_INSTALLER_DIRECTORY=//servidor/carpeta
  PLAY_UPLOAD=1                           sube el AAB generado a Google Play
  PLAY_TRACK=production                   pista: internal, alpha, beta o production
  PLAY_SUBMIT_REVIEW=1                    envía los cambios a revisión
  GOOGLE_PLAY_CREDENTIALS_PATH=/ruta/credencial.json (fuera del repositorio)
  SKIP_CHECKS=1                            omite analyze/test (diagnóstico)
  ALLOW_NON_MAIN=1                         permite otra rama (diagnóstico)
EOF
}

[[ -n "$PLATFORM" ]] || { usage; exit 2; }
case "$PLATFORM" in
  android|apk|web|windows|ios|macos) ;;
  *) usage; exit 2 ;;
esac

case "$PLAY_TRACK" in
  internal|alpha|beta|production) ;;
  *) echo "ERROR: PLAY_TRACK no válido: $PLAY_TRACK"; exit 2 ;;
esac
if [[ "$PLAY_SUBMIT_REVIEW" == '1' && "$PLAY_UPLOAD" != '1' ]]; then
  echo 'ERROR: PLAY_SUBMIT_REVIEW=1 requiere PLAY_UPLOAD=1.'
  exit 2
fi
if [[ "$PLAY_UPLOAD" == '1' && "$PLATFORM" != 'android' ]]; then
  echo 'ERROR: PLAY_UPLOAD=1 solo se puede usar con android.'
  exit 2
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

command -v git >/dev/null || { echo 'ERROR: Git no está disponible.'; exit 1; }
command -v flutter >/dev/null || { echo 'ERROR: Flutter no está instalado o no está en PATH.'; exit 1; }

branch="$(git branch --show-current)"
if [[ "$branch" != "main" && "$ALLOW_NON_MAIN" != "1" ]]; then
  echo "ERROR: estás en la rama '$branch'. Para producción usa main."
  echo "Solo para diagnóstico: ALLOW_NON_MAIN=1 bash tool/build_production.sh $PLATFORM"
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo 'ERROR: hay cambios sin guardar. Haz commit o stash antes de generar una versión de producción.'
  exit 1
fi

APP_VERSION="$(sed -n 's/^[[:space:]]*version:[[:space:]]*\([^[:space:]]*\).*/\1/p' pubspec.yaml | head -n 1)"
[[ -n "$APP_VERSION" ]] || { echo 'ERROR: no se encontró version en pubspec.yaml.'; exit 1; }
echo "Preparando Gestinem $APP_VERSION para $PLATFORM..."

flutter pub get
if [[ "$SKIP_CHECKS" != '1' ]]; then
  flutter analyze
  flutter test
else
  echo 'AVISO: se han omitido flutter analyze y flutter test.'
fi

DEFINES=(--dart-define="API_BASE_URL=$API_BASE_URL" --dart-define="ENVIRONMENT=$ENVIRONMENT")
UNAME="$(uname -s)"
IS_WINDOWS=0
case "$UNAME" in MINGW*|MSYS*|CYGWIN*) IS_WINDOWS=1 ;; esac

assert_file() {
  local path="$1"
  local description="$2"
  [[ -f "$path" ]] || { echo "ERROR: no se generó $description. Ruta esperada: $path"; return 1; }
}

assert_android_signing() {
  assert_file 'android/key.properties' 'android/key.properties para firmar Android'
}

publish_android_bundle() {
  local bundle_path="$1"
  command -v fastlane >/dev/null || {
    echo 'ERROR: instala Fastlane: https://docs.fastlane.tools/getting-started/android/setup/'
    return 1
  }
  [[ -n "$GOOGLE_PLAY_CREDENTIALS_PATH" ]] || {
    echo 'ERROR: falta GOOGLE_PLAY_CREDENTIALS_PATH.'
    return 1
  }
  [[ -f "$GOOGLE_PLAY_CREDENTIALS_PATH" ]] || {
    echo "ERROR: no existe la credencial de Google Play: $GOOGLE_PLAY_CREDENTIALS_PATH"
    return 1
  }

  local credentials_path repository_prefix
  credentials_path="$(cd "$(dirname "$GOOGLE_PLAY_CREDENTIALS_PATH")" && pwd)/$(basename "$GOOGLE_PLAY_CREDENTIALS_PATH")"
  repository_prefix="$(cd "$APP_DIR/.." && pwd)/"
  case "$credentials_path" in
    "$repository_prefix"*)
      echo "ERROR: la credencial de Google Play debe estar fuera del repositorio: $credentials_path"
      return 1
      ;;
  esac

  local arguments=(
    supply
    --aab "$bundle_path"
    --package_name es.gestinem.app
    --track "$PLAY_TRACK"
    --release_status completed
    --json_key "$credentials_path"
    --skip_upload_metadata true
    --skip_upload_changelogs true
    --skip_upload_images true
    --skip_upload_screenshots true
    --timeout 600
  )
  if [[ "$PLAY_SUBMIT_REVIEW" != '1' ]]; then
    arguments+=(--changes_not_sent_for_review true)
  fi

  echo "Subiendo AAB a Google Play (pista: $PLAY_TRACK)..."
  fastlane "${arguments[@]}"
  if [[ "$PLAY_SUBMIT_REVIEW" == '1' ]]; then
    echo "OK: entrega de Google Play enviada a revisión en la pista $PLAY_TRACK."
  else
    echo "OK: AAB subido a la pista $PLAY_TRACK y pendiente de enviar a revisión."
  fi
}

get_firebase_web_option() {
  local option="$1"
  sed -n "/static const FirebaseOptions android/q; s/^[[:space:]]*${option}:[[:space:]]*'\([^']*\)'.*/\1/p" \
    lib/firebase_options.dart | head -n 1
}

resolve_web_vapid_key() {
  if [[ -n "$FIREBASE_WEB_VAPID_KEY" ]]; then
    printf '%s' "$FIREBASE_WEB_VAPID_KEY"
    return
  fi
  if [[ -n "${MESSAGING_VAPID_PUBLIC_KEY:-}" ]]; then
    printf '%s' "$MESSAGING_VAPID_PUBLIC_KEY"
    return
  fi

  command -v railway >/dev/null || {
    echo 'ERROR: instala Railway CLI, inicia sesión y vincula el repositorio.' >&2
    return 1
  }
  command -v node >/dev/null || {
    echo 'ERROR: Node.js es necesario para leer de forma segura la configuración de Railway.' >&2
    return 1
  }

  local resolved
  if ! resolved="$(railway variable list --json 2>/dev/null | node -e '
    let input = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", chunk => input += chunk);
    process.stdin.on("end", () => {
      const values = JSON.parse(input);
      process.stdout.write(values.FIREBASE_WEB_VAPID_KEY || values.MESSAGING_VAPID_PUBLIC_KEY || "");
    });
  ')"; then
    echo 'ERROR: no se pudieron consultar las variables de Railway. Comprueba railway login, link y status.' >&2
    return 1
  fi
  [[ -n "$resolved" ]] || {
    echo 'ERROR: Railway no contiene FIREBASE_WEB_VAPID_KEY ni MESSAGING_VAPID_PUBLIC_KEY con valor.' >&2
    return 1
  }
  printf '%s' "$resolved"
}

patch_built_firebase_service_worker() {
  local service_worker='build/web/firebase-messaging-sw.js'
  assert_file "$service_worker" 'el service worker web de Firebase'

  FIREBASE_API_KEY="$1" \
  FIREBASE_AUTH_DOMAIN="$2" \
  FIREBASE_PROJECT_ID="$3" \
  FIREBASE_STORAGE_BUCKET="$4" \
  FIREBASE_MESSAGING_SENDER_ID="$5" \
  FIREBASE_APP_ID="$6" \
  SERVICE_WORKER_PATH="$service_worker" \
  node -e '
    const fs = require("fs");
    const path = process.env.SERVICE_WORKER_PATH;
    let content = fs.readFileSync(path, "utf8");
    const replacements = {
      PENDIENTE_FIREBASE_WEB_API_KEY: process.env.FIREBASE_API_KEY,
      PENDIENTE_FIREBASE_AUTH_DOMAIN: process.env.FIREBASE_AUTH_DOMAIN,
      PENDIENTE_FIREBASE_PROJECT_ID: process.env.FIREBASE_PROJECT_ID,
      PENDIENTE_FIREBASE_STORAGE_BUCKET: process.env.FIREBASE_STORAGE_BUCKET,
      PENDIENTE_FIREBASE_MESSAGING_SENDER_ID: process.env.FIREBASE_MESSAGING_SENDER_ID,
      PENDIENTE_FIREBASE_APP_ID: process.env.FIREBASE_APP_ID,
    };
    for (const [token, value] of Object.entries(replacements)) {
      if (!value) throw new Error(`Falta el valor para ${token}`);
      content = content.split(token).join(value);
    }
    if (content.includes("PENDIENTE_FIREBASE_")) {
      throw new Error("El service worker conserva valores Firebase pendientes.");
    }
    fs.writeFileSync(path, content, "utf8");
  '
}

publish_web() {
  command -v firebase >/dev/null || {
    echo 'ERROR: Firebase CLI no está instalado. Ejecuta: npm install -g firebase-tools'
    return 1
  }
  command -v node >/dev/null || { echo 'ERROR: Node.js no está disponible.'; return 1; }

  local vapid_key firebase_api_key firebase_auth_domain firebase_project_id
  local firebase_storage_bucket firebase_messaging_sender_id firebase_app_id
  vapid_key="$(resolve_web_vapid_key)"
  firebase_api_key="$(get_firebase_web_option apiKey)"
  firebase_auth_domain="$(get_firebase_web_option authDomain)"
  firebase_project_id="$(get_firebase_web_option projectId)"
  firebase_storage_bucket="$(get_firebase_web_option storageBucket)"
  firebase_messaging_sender_id="$(get_firebase_web_option messagingSenderId)"
  firebase_app_id="$(get_firebase_web_option appId)"

  [[ -n "$firebase_api_key" ]] || { echo 'ERROR: falta apiKey en firebase_options.dart.'; return 1; }
  [[ -n "$firebase_auth_domain" ]] || { echo 'ERROR: falta authDomain en firebase_options.dart.'; return 1; }
  [[ -n "$firebase_project_id" ]] || { echo 'ERROR: falta projectId en firebase_options.dart.'; return 1; }
  [[ -n "$firebase_storage_bucket" ]] || { echo 'ERROR: falta storageBucket en firebase_options.dart.'; return 1; }
  [[ -n "$firebase_messaging_sender_id" ]] || { echo 'ERROR: falta messagingSenderId en firebase_options.dart.'; return 1; }
  [[ -n "$firebase_app_id" ]] || { echo 'ERROR: falta appId en firebase_options.dart.'; return 1; }

  flutter build web --release "${DEFINES[@]}" --dart-define="FIREBASE_WEB_VAPID_KEY=$vapid_key"
  assert_file 'build/web/index.html' 'build/web/index.html'
  assert_file 'build/web/main.dart.js' 'build/web/main.dart.js'
  patch_built_firebase_service_worker \
    "$firebase_api_key" \
    "$firebase_auth_domain" \
    "$firebase_project_id" \
    "$firebase_storage_bucket" \
    "$firebase_messaging_sender_id" \
    "$firebase_app_id"
  grep -Fq -- "$vapid_key" build/web/main.dart.js || {
    echo 'ERROR: la aplicación web compilada no contiene la clave pública VAPID.'
    return 1
  }

  firebase deploy --only hosting --project gest2a3eco
  echo 'OK: web publicada en https://app.gestinem.es'
}

publish_windows_installer() {
  local installer_path="$1"
  local installer_name destination_path temporary_path source_hash copied_hash

  [[ -d "$SHARED_INSTALLER_DIRECTORY" ]] || {
    echo "ERROR: la carpeta compartida de instaladores no está disponible: $SHARED_INSTALLER_DIRECTORY"
    return 1
  }

  installer_name="$(basename "$installer_path")"
  destination_path="$SHARED_INSTALLER_DIRECTORY/$installer_name"
  temporary_path="$SHARED_INSTALLER_DIRECTORY/.$installer_name.$$.tmp"
  if ! cp -f -- "$installer_path" "$temporary_path"; then
    rm -f -- "$temporary_path"
    echo "ERROR: no se pudo copiar el instalador a $SHARED_INSTALLER_DIRECTORY"
    return 1
  fi
  source_hash="$(sha256sum "$installer_path" | awk '{print $1}')"
  copied_hash="$(sha256sum "$temporary_path" | awk '{print $1}')"
  if [[ "$source_hash" != "$copied_hash" ]]; then
    rm -f -- "$temporary_path"
    echo 'ERROR: la copia temporal del instalador no coincide con el original.'
    return 1
  fi
  mv -f -- "$temporary_path" "$destination_path"
  copied_hash="$(sha256sum "$destination_path" | awk '{print $1}')"
  [[ "$source_hash" == "$copied_hash" ]] || {
    echo 'ERROR: el instalador compartido no coincide con el original.'
    return 1
  }
  echo "OK: instalador copiado en $destination_path"
}

case "$PLATFORM" in
  android)
    assert_android_signing
    flutter build appbundle --release "${DEFINES[@]}"
    assert_file 'build/app/outputs/bundle/release/app-release.aab' 'el AAB Android'
    if [[ "$PLAY_UPLOAD" == '1' ]]; then
      publish_android_bundle 'build/app/outputs/bundle/release/app-release.aab'
    else
      echo 'OK: AAB disponible en build/app/outputs/bundle/release/app-release.aab'
      echo 'Para subirlo: usa PLAY_UPLOAD=1, PLAY_TRACK=<pista> y, opcionalmente, PLAY_SUBMIT_REVIEW=1.'
    fi
    ;;
  apk)
    assert_android_signing
    flutter build apk --release "${DEFINES[@]}"
    assert_file 'build/app/outputs/flutter-apk/app-release.apk' 'el APK Android'
    echo 'OK: APK disponible en build/app/outputs/flutter-apk/app-release.apk'
    ;;
  web)
    publish_web
    ;;
  windows)
    [[ "$IS_WINDOWS" == '1' ]] || { echo 'ERROR: Windows solo puede compilarse desde Windows.'; exit 1; }
    flutter build windows --release "${DEFINES[@]}"

    iscc=''
    for candidate in \
      '/c/Program Files (x86)/Inno Setup 6/ISCC.exe' \
      '/c/Program Files/Inno Setup 6/ISCC.exe'; do
      if [[ -f "$candidate" ]]; then iscc="$candidate"; break; fi
    done
    [[ -n "$iscc" ]] || { echo 'ERROR: Inno Setup 6 no está instalado.'; exit 1; }
    "$iscc" 'windows\installer\gestinem.iss'

    installer_version="${APP_VERSION/+/.}"
    installer_path="../dist_installer/Gestinem-Windows-$installer_version.exe"
    assert_file "$installer_path" 'el instalador Windows'
    echo "OK: instalador generado en $installer_path"
    publish_windows_installer "$installer_path"
    ;;
  ios)
    [[ "$UNAME" == 'Darwin' ]] || { echo 'ERROR: iOS solo puede compilarse desde macOS.'; exit 1; }
    flutter build ipa --release "${DEFINES[@]}"
    compgen -G 'build/ios/ipa/*.ipa' >/dev/null || { echo 'ERROR: no se generó ningún IPA.'; exit 1; }
    echo 'OK: sube el IPA de build/ios/ipa/ a App Store Connect.'
    ;;
  macos)
    [[ "$UNAME" == 'Darwin' ]] || { echo 'ERROR: macOS solo puede compilarse desde macOS.'; exit 1; }
    flutter build macos --release "${DEFINES[@]}"
    compgen -G 'build/macos/Build/Products/Release/*.app' >/dev/null || {
      echo 'ERROR: no se generó ninguna aplicación macOS.'
      exit 1
    }
    echo 'OK: aplicación macOS generada en build/macos/Build/Products/Release/.'
    ;;
esac
