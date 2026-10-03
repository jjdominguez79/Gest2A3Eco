[CmdletBinding()]
param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet('android','apk','web','windows','ios','macos')]
    [string]$Platform,
    [string]$ApiBaseUrl = 'https://gest2a3eco-production.up.railway.app',
    [string]$Environment = 'production',
    [string]$VapidKey = $env:FIREBASE_WEB_VAPID_KEY,
    [string]$SharedInstallerDirectory = '',
    [switch]$UploadPlay,
    [ValidateSet('internal','alpha','beta','production')]
    [string]$PlayTrack = 'internal',
    [switch]$SubmitPlayReview,
    [string]$PlayCredentialsPath = $env:GOOGLE_PLAY_CREDENTIALS_PATH,
    [switch]$SkipChecks,
    [switch]$AllowNonMain
)

$ErrorActionPreference = 'Stop'
$appDirectory = Split-Path -Parent $PSScriptRoot

function Assert-Command([string]$Name, [string]$InstallHint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name no está disponible. $InstallHint"
    }
}

function Assert-File([string]$Path, [string]$Description) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "No se generó $Description. Ruta esperada: $Path"
    }
}

function Assert-NotEmpty([string]$Value, [string]$Description) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Falta $Description."
    }
}

function Resolve-ExternalFile([string]$Path, [string]$Description) {
    Assert-NotEmpty $Path $Description
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "No existe $Description`: $Path"
    }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $repositoryDirectory = Split-Path -Parent $appDirectory
    $repositoryPrefix = $repositoryDirectory.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if ($resolved.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Description debe estar fuera del repositorio: $resolved"
    }
    return $resolved
}

Push-Location -LiteralPath $appDirectory
try {
    Assert-Command 'git' 'Instala Git y vuelve a abrir el terminal.'
    Assert-Command 'flutter' 'Instala Flutter y añádelo a PATH.'

    if ($SubmitPlayReview -and -not $UploadPlay) {
        throw '-SubmitPlayReview requiere -UploadPlay.'
    }
    if ($UploadPlay -and $Platform -ne 'android') {
        throw '-UploadPlay solo se puede usar con la plataforma android.'
    }

    # Compatible con Windows PowerShell 5.1 y PowerShell 7+.
    $runningOnWindows = ($env:OS -eq 'Windows_NT')
    $runningOnMacOS = $false
    if ($PSVersionTable.PSVersion.Major -ge 6) {
        if (Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) {
            $runningOnWindows = [bool]$IsWindows
        }
        if (Get-Variable -Name IsMacOS -ErrorAction SilentlyContinue) {
            $runningOnMacOS = [bool]$IsMacOS
        }
    }
    if (-not $runningOnWindows) {
        try { $runningOnMacOS = ((uname -s) -eq 'Darwin') } catch { $runningOnMacOS = $false }
    }

    $branch = (git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar la rama Git.' }
    if ($branch -ne 'main' -and -not $AllowNonMain) {
        throw "Estás en la rama '$branch'. Para producción usa main. Usa -AllowNonMain solo para diagnóstico."
    }
    if (git status --porcelain) {
        throw 'Hay cambios sin guardar. Haz commit o stash antes de generar una versión de producción.'
    }

    $versionMatch = Select-String -LiteralPath 'pubspec.yaml' -Pattern '^version:\s*(\S+)' | Select-Object -First 1
    if (-not $versionMatch) { throw 'No se encontró version en pubspec.yaml.' }
    $appVersion = $versionMatch.Matches[0].Groups[1].Value
    Write-Host "Preparando Gestinem $appVersion para $Platform..."

    flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'flutter pub get ha fallado.' }
    if (-not $SkipChecks) {
        flutter analyze
        if ($LASTEXITCODE -ne 0) { throw 'flutter analyze ha fallado.' }
        flutter test
        if ($LASTEXITCODE -ne 0) { throw 'flutter test ha fallado.' }
    } else {
        Write-Warning 'Se han omitido flutter analyze y flutter test.'
    }

    $defines = @(
        "--dart-define=API_BASE_URL=$ApiBaseUrl",
        "--dart-define=ENVIRONMENT=$Environment"
    )

    function Assert-AndroidSigning {
        Assert-File 'android/key.properties' 'android/key.properties para firmar Android'
    }

    function Publish-AndroidBundle([string]$BundlePath) {
        Assert-Command 'fastlane' 'Instala Fastlane: https://docs.fastlane.tools/getting-started/android/setup/'
        $credentialsPath = Resolve-ExternalFile `
            $PlayCredentialsPath `
            'la credencial de servicio de Google Play'
        $resolvedBundlePath = (Resolve-Path -LiteralPath $BundlePath).Path

        $arguments = @(
            'supply',
            '--aab', $resolvedBundlePath,
            '--package_name', 'es.gestinem.app',
            '--track', $PlayTrack,
            '--release_status', 'completed',
            '--json_key', $credentialsPath,
            '--skip_upload_metadata', 'true',
            '--skip_upload_changelogs', 'true',
            '--skip_upload_images', 'true',
            '--skip_upload_screenshots', 'true',
            '--timeout', '600'
        )
        if (-not $SubmitPlayReview) {
            $arguments += @('--changes_not_sent_for_review', 'true')
        }

        Write-Host "Subiendo AAB a Google Play (pista: $PlayTrack)..."
        & fastlane @arguments
        if ($LASTEXITCODE -ne 0) {
            throw 'Google Play no aceptó la entrega del AAB.'
        }
        if ($SubmitPlayReview) {
            Write-Host "OK: entrega de Google Play enviada a revisión en la pista $PlayTrack."
        } else {
            Write-Host "OK: AAB subido a la pista $PlayTrack y pendiente de enviar a revisión."
        }
    }

    function Get-FirebaseWebOption([string]$Name) {
        $optionsFile = Join-Path $appDirectory 'lib\firebase_options.dart'
        Assert-File $optionsFile 'lib/firebase_options.dart'
        $content = Get-Content -LiteralPath $optionsFile -Raw
        $webBlock = ($content -split 'static const FirebaseOptions android')[0]
        $match = [regex]::Match(
            $webBlock,
            ("(?m)^\s*" + [regex]::Escape($Name) + "\s*:\s*'([^']+)'\s*,")
        )
        return $(if ($match.Success) { $match.Groups[1].Value } else { '' })
    }

    function Resolve-WebVapidKey {
        if (-not [string]::IsNullOrWhiteSpace($VapidKey)) {
            return $VapidKey.Trim()
        }
        if (-not [string]::IsNullOrWhiteSpace($env:MESSAGING_VAPID_PUBLIC_KEY)) {
            return $env:MESSAGING_VAPID_PUBLIC_KEY.Trim()
        }

        Assert-Command 'railway' 'Instala Railway CLI, inicia sesión y vincula este repositorio al servicio Gest2A3Eco.'
        $rawVariables = railway variable list --json 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $rawVariables) {
            throw 'No se pudieron consultar las variables de Railway. Comprueba railway login, link y status.'
        }
        try {
            $variables = $rawVariables | ConvertFrom-Json
        } catch {
            throw 'Railway no devolvió un JSON válido al consultar sus variables.'
        }
        foreach ($name in @('FIREBASE_WEB_VAPID_KEY', 'MESSAGING_VAPID_PUBLIC_KEY')) {
            $property = $variables.PSObject.Properties[$name]
            if ($null -ne $property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
                return ([string]$property.Value).Trim()
            }
        }
        throw 'Railway no contiene FIREBASE_WEB_VAPID_KEY ni MESSAGING_VAPID_PUBLIC_KEY con valor.'
    }

    function Set-BuiltFirebaseServiceWorker(
        [string]$FirebaseApiKey,
        [string]$FirebaseAuthDomain,
        [string]$FirebaseProjectId,
        [string]$FirebaseStorageBucket,
        [string]$FirebaseMessagingSenderId,
        [string]$FirebaseAppId
    ) {
        $serviceWorkerPath = Join-Path $appDirectory 'build\web\firebase-messaging-sw.js'
        Assert-File $serviceWorkerPath 'el service worker web de Firebase'
        $content = Get-Content -LiteralPath $serviceWorkerPath -Raw
        $replacements = [ordered]@{
            'PENDIENTE_FIREBASE_WEB_API_KEY'         = $FirebaseApiKey
            'PENDIENTE_FIREBASE_AUTH_DOMAIN'         = $FirebaseAuthDomain
            'PENDIENTE_FIREBASE_PROJECT_ID'          = $FirebaseProjectId
            'PENDIENTE_FIREBASE_STORAGE_BUCKET'      = $FirebaseStorageBucket
            'PENDIENTE_FIREBASE_MESSAGING_SENDER_ID' = $FirebaseMessagingSenderId
            'PENDIENTE_FIREBASE_APP_ID'              = $FirebaseAppId
        }
        foreach ($entry in $replacements.GetEnumerator()) {
            $content = $content.Replace($entry.Key, [string]$entry.Value)
        }
        if ($content -match 'PENDIENTE_FIREBASE_') {
            throw 'El service worker compilado conserva valores Firebase pendientes.'
        }
        $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($serviceWorkerPath, $content, $utf8WithoutBom)
    }

    function Publish-Web {
        Assert-Command 'firebase' 'Instala Firebase CLI con: npm install -g firebase-tools'
        $resolvedVapidKey = Resolve-WebVapidKey

        $firebaseApiKey = Get-FirebaseWebOption 'apiKey'
        $firebaseAuthDomain = Get-FirebaseWebOption 'authDomain'
        $firebaseProjectId = Get-FirebaseWebOption 'projectId'
        $firebaseStorageBucket = Get-FirebaseWebOption 'storageBucket'
        $firebaseMessagingSenderId = Get-FirebaseWebOption 'messagingSenderId'
        $firebaseAppId = Get-FirebaseWebOption 'appId'
        Assert-NotEmpty $firebaseApiKey 'apiKey en firebase_options.dart'
        Assert-NotEmpty $firebaseAuthDomain 'authDomain en firebase_options.dart'
        Assert-NotEmpty $firebaseProjectId 'projectId en firebase_options.dart'
        Assert-NotEmpty $firebaseStorageBucket 'storageBucket en firebase_options.dart'
        Assert-NotEmpty $firebaseMessagingSenderId 'messagingSenderId en firebase_options.dart'
        Assert-NotEmpty $firebaseAppId 'appId en firebase_options.dart'

        & flutter build web --release @defines "--dart-define=FIREBASE_WEB_VAPID_KEY=$resolvedVapidKey"
        if ($LASTEXITCODE -ne 0) { throw 'Falló Flutter Web.' }
        Assert-File 'build/web/index.html' 'build/web/index.html'
        Assert-File 'build/web/main.dart.js' 'build/web/main.dart.js'

        Set-BuiltFirebaseServiceWorker `
            $firebaseApiKey `
            $firebaseAuthDomain `
            $firebaseProjectId `
            $firebaseStorageBucket `
            $firebaseMessagingSenderId `
            $firebaseAppId

        $compiledJavascript = [System.IO.File]::ReadAllText((Join-Path $appDirectory 'build\web\main.dart.js'))
        if (-not $compiledJavascript.Contains($resolvedVapidKey)) {
            throw 'La aplicación web compilada no contiene la clave pública VAPID.'
        }

        firebase deploy --only hosting --project gest2a3eco
        if ($LASTEXITCODE -ne 0) { throw 'Falló el despliegue de Firebase Hosting.' }
        Write-Host 'OK: web publicada en https://app.gestinem.es'
    }

    function Get-WindowsInstallerPath {
        $executablePath = Join-Path $appDirectory 'build\windows\x64\runner\Release\gestinem.exe'
        Assert-File $executablePath 'el ejecutable Windows'
        $versionInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($executablePath)
        $version = '{0}.{1}.{2}.{3}' -f `
            $versionInfo.FileMajorPart,
            $versionInfo.FileMinorPart,
            $versionInfo.FileBuildPart,
            $versionInfo.FilePrivatePart
        return Join-Path (Split-Path -Parent $appDirectory) "dist_installer\Gestinem-Windows-$version.exe"
    }

    function Publish-WindowsInstaller([string]$InstallerPath) {
        $sharedDirectory = $SharedInstallerDirectory
        if ([string]::IsNullOrWhiteSpace($sharedDirectory)) {
            $sharedDirectory = $env:GEST2A3ECO_DOCUMENT_REPOSITORY_DIR
        }
        if ([string]::IsNullOrWhiteSpace($sharedDirectory)) {
            $sharedDirectory = '\\GestinemMain\Doc_Compartidos\Gest2A3Eco'
        }
        if (-not (Test-Path -LiteralPath $sharedDirectory -PathType Container)) {
            throw "La carpeta compartida de instaladores no está disponible: $sharedDirectory"
        }

        $fileName = Split-Path -Leaf $InstallerPath
        $destinationPath = Join-Path $sharedDirectory $fileName
        $temporaryPath = Join-Path $sharedDirectory ".$fileName.$PID.tmp"
        try {
            Copy-Item -LiteralPath $InstallerPath -Destination $temporaryPath -Force
            $sourceHash = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash
            $temporaryHash = (Get-FileHash -LiteralPath $temporaryPath -Algorithm SHA256).Hash
            if ($sourceHash -ne $temporaryHash) {
                throw 'La copia temporal del instalador no coincide con el original.'
            }
            Move-Item -LiteralPath $temporaryPath -Destination $destinationPath -Force
            $destinationHash = (Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash
            if ($sourceHash -ne $destinationHash) {
                throw 'El instalador compartido no coincide con el original.'
            }
        } finally {
            if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
                Remove-Item -LiteralPath $temporaryPath -Force
            }
        }
        Write-Host "OK: instalador copiado en $destinationPath"
    }

    switch ($Platform) {
        'android' {
            Assert-AndroidSigning
            & flutter build appbundle --release @defines
            if ($LASTEXITCODE -ne 0) { throw 'Falló el AAB Android.' }
            $bundlePath = 'build/app/outputs/bundle/release/app-release.aab'
            Assert-File $bundlePath 'el AAB Android'
            if ($UploadPlay) {
                Publish-AndroidBundle $bundlePath
            } else {
                Write-Host "OK: AAB disponible en $bundlePath"
                Write-Host 'Para subirlo: añade -UploadPlay -PlayTrack <pista> y, opcionalmente, -SubmitPlayReview.'
            }
        }
        'apk' {
            Assert-AndroidSigning
            & flutter build apk --release @defines
            if ($LASTEXITCODE -ne 0) { throw 'Falló el APK Android.' }
            Assert-File 'build/app/outputs/flutter-apk/app-release.apk' 'el APK Android'
            Write-Host 'OK: APK disponible en build/app/outputs/flutter-apk/app-release.apk'
        }
        'web' {
            Publish-Web
        }
        'windows' {
            if (-not $runningOnWindows) { throw 'Windows solo puede compilarse desde Windows.' }
            & flutter build windows --release @defines
            if ($LASTEXITCODE -ne 0) { throw 'Falló Flutter Windows.' }

            $iscc = @(
                'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
                'C:\Program Files\Inno Setup 6\ISCC.exe'
            ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
            if (-not $iscc) {
                throw 'Inno Setup 6 no está instalado. No se puede generar el instalador Windows.'
            }
            & $iscc 'windows\installer\gestinem.iss'
            if ($LASTEXITCODE -ne 0) { throw 'Falló Inno Setup.' }
            $installerPath = Get-WindowsInstallerPath
            Assert-File $installerPath 'el instalador Windows'
            Write-Host "OK: instalador generado en $installerPath"
            Publish-WindowsInstaller $installerPath
        }
        'ios' {
            if (-not $runningOnMacOS) { throw 'iOS solo puede compilarse desde macOS.' }
            & flutter build ipa --release @defines
            if ($LASTEXITCODE -ne 0) { throw 'Falló el IPA iOS.' }
            $ipa = Get-ChildItem -LiteralPath 'build/ios/ipa' -Filter '*.ipa' -File | Select-Object -First 1
            if (-not $ipa) { throw 'Flutter terminó sin generar ningún IPA en build/ios/ipa/.' }
            Write-Host "OK: sube $($ipa.FullName) a App Store Connect."
        }
        'macos' {
            if (-not $runningOnMacOS) { throw 'macOS solo puede compilarse desde macOS.' }
            & flutter build macos --release @defines
            if ($LASTEXITCODE -ne 0) { throw 'Falló Flutter macOS.' }
            $macApp = Get-ChildItem -LiteralPath 'build/macos/Build/Products/Release' -Filter '*.app' -Directory | Select-Object -First 1
            if (-not $macApp) { throw 'Flutter terminó sin generar ninguna aplicación macOS.' }
            Write-Host "OK: aplicación macOS generada en $($macApp.FullName)"
        }
    }
}
finally {
    Pop-Location
}
