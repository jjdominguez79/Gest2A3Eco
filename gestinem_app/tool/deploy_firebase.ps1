param(
    [string]$ApiBaseUrl = "https://gest2a3eco-production.up.railway.app",
    [string]$Environment = "production",
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"
$appDirectory = Split-Path -Parent $PSScriptRoot

Push-Location -LiteralPath $appDirectory
try {
    flutter build web --release `
        --dart-define="API_BASE_URL=$ApiBaseUrl" `
        --dart-define="ENVIRONMENT=$Environment"
    if ($LASTEXITCODE -ne 0) {
        throw "Flutter Web devolvio el codigo $LASTEXITCODE."
    }

    if (-not (Test-Path -LiteralPath "build/web/index.html")) {
        throw "Flutter no genero build/web/index.html."
    }

    if ($BuildOnly) {
        Write-Host "Build web preparado en gestinem_app/build/web."
        return
    }

    if (-not (Get-Command firebase -ErrorAction SilentlyContinue)) {
        throw "Firebase CLI no esta instalado. Ejecuta: npm install -g firebase-tools"
    }

    firebase deploy --only hosting --project gest2a3eco
    if ($LASTEXITCODE -ne 0) {
        throw "Firebase Hosting devolvio el codigo $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
