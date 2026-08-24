param(
    [string]$ApiBaseUrl = "https://gest2a3eco-production.up.railway.app",
    [string]$Environment = "production",
    # Clave publica VAPID (Firebase Console > Cloud Messaging > Certificados web push).
    # Tambien puede pasarse mediante la variable de entorno FIREBASE_WEB_VAPID_KEY.
    [string]$VapidKey = $env:FIREBASE_WEB_VAPID_KEY,
    # Configuracion Firebase Web (se usan para inyectar en el service worker).
    # Si no se pasan, se leen de las variables de entorno FIREBASE_WEB_*.
    [string]$FirebaseApiKey            = $env:FIREBASE_WEB_API_KEY,
    [string]$FirebaseAuthDomain        = $env:FIREBASE_WEB_AUTH_DOMAIN,
    [string]$FirebaseProjectId         = $env:FIREBASE_WEB_PROJECT_ID,
    [string]$FirebaseStorageBucket     = $env:FIREBASE_WEB_STORAGE_BUCKET,
    [string]$FirebaseMessagingSenderId = $env:FIREBASE_WEB_MESSAGING_SENDER_ID,
    [string]$FirebaseAppId             = $env:FIREBASE_WEB_APP_ID,
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"
$appDirectory = Split-Path -Parent $PSScriptRoot

# ---------------------------------------------------------------------------
# Validaciones previas al build
# ---------------------------------------------------------------------------

function Assert-NotEmpty([string]$value, [string]$name) {
    if (-not $value -or $value.Trim() -eq '') {
        throw "Falta el parametro requerido: $name. Pasalo como argumento o variable de entorno."
    }
}

Assert-NotEmpty $VapidKey            "VapidKey / FIREBASE_WEB_VAPID_KEY"
Assert-NotEmpty $FirebaseApiKey            "FirebaseApiKey / FIREBASE_WEB_API_KEY"
Assert-NotEmpty $FirebaseAuthDomain        "FirebaseAuthDomain / FIREBASE_WEB_AUTH_DOMAIN"
Assert-NotEmpty $FirebaseProjectId         "FirebaseProjectId / FIREBASE_WEB_PROJECT_ID"
Assert-NotEmpty $FirebaseStorageBucket     "FirebaseStorageBucket / FIREBASE_WEB_STORAGE_BUCKET"
Assert-NotEmpty $FirebaseMessagingSenderId "FirebaseMessagingSenderId / FIREBASE_WEB_MESSAGING_SENDER_ID"
Assert-NotEmpty $FirebaseAppId             "FirebaseAppId / FIREBASE_WEB_APP_ID"

# Comprobar que firebase_options.dart no tiene valores PENDIENTE en la seccion web.
$optionsFile = Join-Path $appDirectory "lib/firebase_options.dart"
if (Test-Path -LiteralPath $optionsFile) {
    $optionsContent = Get-Content $optionsFile -Raw
    # Buscamos PENDIENTE en las lineas que pertenecen al bloque web (antes de android).
    $webBlock = ($optionsContent -split 'static const FirebaseOptions android')[0]
    if ($webBlock -match 'PENDIENTE') {
        throw (
            "firebase_options.dart contiene valores PENDIENTE en la configuracion web. " +
            "Ejecuta 'flutterfire configure --project=<proyecto>' y vuelve a intentarlo."
        )
    }
} else {
    throw "No se encontro $optionsFile"
}

# Comprobar que el service worker no tiene valores PENDIENTE (antes de sustituir).
$swFile = Join-Path $appDirectory "web/firebase-messaging-sw.js"
if (-not (Test-Path -LiteralPath $swFile)) {
    throw "No se encontro el service worker: $swFile"
}

Push-Location -LiteralPath $appDirectory
try {
    # ---------------------------------------------------------------------------
    # Inyectar valores reales en el service worker (sustitucion temporal).
    # ---------------------------------------------------------------------------
    $swOriginal = Get-Content $swFile -Raw -Encoding UTF8

    $swPatched = $swOriginal `
        -replace 'PENDIENTE_FIREBASE_WEB_API_KEY',         $FirebaseApiKey `
        -replace 'PENDIENTE_FIREBASE_AUTH_DOMAIN',          $FirebaseAuthDomain `
        -replace 'PENDIENTE_FIREBASE_PROJECT_ID',           $FirebaseProjectId `
        -replace 'PENDIENTE_FIREBASE_STORAGE_BUCKET',       $FirebaseStorageBucket `
        -replace 'PENDIENTE_FIREBASE_MESSAGING_SENDER_ID',  $FirebaseMessagingSenderId `
        -replace 'PENDIENTE_FIREBASE_APP_ID',               $FirebaseAppId

    if ($swPatched -match 'PENDIENTE') {
        throw "El service worker sigue teniendo valores PENDIENTE tras la sustitucion. Revisa el script."
    }

    [System.IO.File]::WriteAllText($swFile, $swPatched, [System.Text.Encoding]::UTF8)

    # ---------------------------------------------------------------------------
    # Build
    # ---------------------------------------------------------------------------
    flutter build web --release `
        --dart-define="API_BASE_URL=$ApiBaseUrl" `
        --dart-define="ENVIRONMENT=$Environment" `
        --dart-define="FIREBASE_WEB_VAPID_KEY=$VapidKey"

    if ($LASTEXITCODE -ne 0) {
        throw "Flutter Web devolvio el codigo $LASTEXITCODE."
    }

    if (-not (Test-Path -LiteralPath "build/web/index.html")) {
        throw "Flutter no genero build/web/index.html."
    }

    if (-not (Test-Path -LiteralPath "build/web/firebase-messaging-sw.js")) {
        throw (
            "El service worker no aparece en build/web/. " +
            "Comprueba que web/firebase-messaging-sw.js existe y que Flutter lo copia."
        )
    }

    # Verificar que el build no contiene PENDIENTE en el service worker.
    $builtSw = Get-Content "build/web/firebase-messaging-sw.js" -Raw
    if ($builtSw -match 'PENDIENTE') {
        throw "El service worker compilado sigue conteniendo valores PENDIENTE."
    }

    if ($BuildOnly) {
        Write-Host "Build web preparado en gestinem_app/build/web."
        return
    }

    # ---------------------------------------------------------------------------
    # Deploy
    # ---------------------------------------------------------------------------
    if (-not (Get-Command firebase -ErrorAction SilentlyContinue)) {
        throw "Firebase CLI no esta instalado. Ejecuta: npm install -g firebase-tools"
    }

    firebase deploy --only hosting --project gest2a3eco
    if ($LASTEXITCODE -ne 0) {
        throw "Firebase Hosting devolvio el codigo $LASTEXITCODE."
    }
}
finally {
    # Restaurar el service worker con los placeholders originales.
    if ($null -ne $swOriginal) {
        [System.IO.File]::WriteAllText($swFile, $swOriginal, [System.Text.Encoding]::UTF8)
    }
    Pop-Location
}
