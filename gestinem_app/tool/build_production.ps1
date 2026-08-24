param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('android','apk','web','web-deploy','windows','ios','macos','all')]
    [string]$Platform,
    [string]$ApiBaseUrl = 'https://gest2a3eco-production.up.railway.app',
    [string]$Environment = 'production',
    [switch]$SkipChecks,
    [switch]$AllowNonMain
)

$ErrorActionPreference = 'Stop'
$appDirectory = Split-Path -Parent $PSScriptRoot
Push-Location $appDirectory
try {
    if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) { throw 'Flutter no está instalado o no está en PATH.' }

    $branch = (git branch --show-current).Trim()
    if ($branch -ne 'main' -and -not $AllowNonMain) {
        throw "Estás en la rama '$branch'. Para producción usa main. Usa -AllowNonMain solo si sabes lo que haces."
    }
    if (git status --porcelain) { throw 'Hay cambios sin guardar. Haz commit/stash antes de un build de producción.' }

    flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'flutter pub get ha fallado.' }
    if (-not $SkipChecks) {
        flutter analyze
        if ($LASTEXITCODE -ne 0) { throw 'flutter analyze ha fallado.' }
        flutter test
        if ($LASTEXITCODE -ne 0) { throw 'flutter test ha fallado.' }
    }

    $defines = @("--dart-define=API_BASE_URL=$ApiBaseUrl", "--dart-define=ENVIRONMENT=$Environment")

    function Assert-AndroidSigning {
        if (-not (Test-Path 'android/key.properties')) { throw 'Falta android/key.properties. No se puede generar Android release firmado.' }
    }

    function Build-One([string]$Target) {
        switch ($Target) {
            'android' {
                Assert-AndroidSigning
                & flutter build appbundle --release @defines
                if ($LASTEXITCODE -ne 0) { throw 'Falló el AAB Android.' }
                Write-Host 'OK: build/app/outputs/bundle/release/app-release.aab'
            }
            'apk' {
                Assert-AndroidSigning
                & flutter build apk --release @defines
                if ($LASTEXITCODE -ne 0) { throw 'Falló el APK Android.' }
                Write-Host 'OK: build/app/outputs/flutter-apk/app-release.apk'
            }
            'web' {
                & flutter build web --release @defines
                if ($LASTEXITCODE -ne 0) { throw 'Falló Flutter Web.' }
                Write-Host 'OK: build/web'
            }
            'web-deploy' {
                if (-not (Get-Command firebase -ErrorAction SilentlyContinue)) { throw 'Firebase CLI no está instalado. Ejecuta: npm install -g firebase-tools' }
                & flutter build web --release @defines
                if ($LASTEXITCODE -ne 0) { throw 'Falló Flutter Web.' }
                firebase deploy --only hosting --project gest2a3eco
                if ($LASTEXITCODE -ne 0) { throw 'Falló Firebase Hosting.' }
            }
            'windows' {
                if (-not $IsWindows) { throw 'Windows solo puede compilarse desde Windows.' }
                & flutter build windows --release @defines
                if ($LASTEXITCODE -ne 0) { throw 'Falló Flutter Windows.' }
                $iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
                if (Test-Path $iscc) {
                    & $iscc 'windows\installer\gestinem.iss'
                    if ($LASTEXITCODE -ne 0) { throw 'Falló Inno Setup.' }
                    Write-Host 'OK: instalador generado en ../dist_installer/'
                } else {
                    Write-Warning 'Build Windows creado, pero Inno Setup 6 no está instalado. No se generó el instalador.'
                }
            }
            'ios' {
                if (-not $IsMacOS) { throw 'iOS solo puede compilarse desde macOS.' }
                & flutter build ipa --release @defines
                if ($LASTEXITCODE -ne 0) { throw 'Falló el IPA iOS.' }
            }
            'macos' {
                if (-not $IsMacOS) { throw 'macOS solo puede compilarse desde macOS.' }
                & flutter build macos --release @defines
                if ($LASTEXITCODE -ne 0) { throw 'Falló Flutter macOS.' }
            }
        }
    }

    if ($Platform -eq 'all') {
        Build-One 'android'; Build-One 'web'
        if ($IsWindows) { Build-One 'windows' }
        if ($IsMacOS) { Build-One 'ios'; Build-One 'macos' }
    } else { Build-One $Platform }
}
finally { Pop-Location }
