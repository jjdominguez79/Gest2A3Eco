[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Cyan
}

function Stop-WithError {
    param(
        [string]$Step,
        [string]$Message,
        [string]$Command = "",
        [string]$Details = ""
    )

    Write-Host ""
    Write-Host "ERROR [$Step] $Message" -ForegroundColor Red
    if ($Command) {
        Write-Host "Comando: $Command" -ForegroundColor DarkRed
    }
    if ($Details) {
        Write-Host $Details -ForegroundColor Yellow
    }
    throw "${Step}: $Message"
}

function Test-CommandInstalled {
    param(
        [string]$Name,
        [string]$Step
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Stop-WithError -Step $Step -Message "No se encontro el ejecutable '$Name' en PATH." -Details "Instala $Name y vuelve a intentarlo."
    }
}

function Invoke-Tool {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Step,
        [int[]]$AllowedExitCodes = @(0),
        [switch]$ShowOutput
    )

    $commandText = ($FilePath + " " + ($Arguments -join " ")).Trim()
    $previousErrorActionPreference = $ErrorActionPreference
    $hasNativePreference = [bool](Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)
    if ($hasNativePreference) {
        $previousNativePreference = $PSNativeCommandUseErrorActionPreference
    }

    try {
        $ErrorActionPreference = "Continue"
        if ($hasNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $false
        }
        $rawOutput = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        if ($hasNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $previousNativePreference
        }
    }

    $output = ($rawOutput | ForEach-Object { $_.ToString() }) -join "`n"

    if ($AllowedExitCodes -notcontains $exitCode) {
        Stop-WithError -Step $Step -Message "El comando termino con codigo $exitCode." -Command $commandText -Details $output
    }

    if ($ShowOutput -and $output) {
        Write-Host $output
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output   = $output.Trim()
        Command  = $commandText
    }
}

function Invoke-Git {
    param(
        [string]$Step,
        [string[]]$Arguments,
        [int[]]$AllowedExitCodes = @(0),
        [switch]$ShowOutput
    )

    return Invoke-Tool -FilePath "git" -Arguments $Arguments -Step $Step -AllowedExitCodes $AllowedExitCodes -ShowOutput:$ShowOutput
}

function Invoke-Python {
    param(
        [string]$Step,
        [string[]]$Arguments,
        [int[]]$AllowedExitCodes = @(0),
        [switch]$ShowOutput
    )

    return Invoke-Tool -FilePath "python" -Arguments $Arguments -Step $Step -AllowedExitCodes $AllowedExitCodes -ShowOutput:$ShowOutput
}

function Read-MultilineChangelog {
    Write-Host ""
    Write-Host "Introduce el changelog. Escribe FIN en una linea nueva para terminar:" -ForegroundColor Cyan
    $lines = New-Object System.Collections.Generic.List[string]
    while ($true) {
        $line = Read-Host
        if ($line -eq "FIN") {
            break
        }
        $lines.Add($line)
    }
    return ($lines -join [Environment]::NewLine).Trim()
}

function Test-IncompleteGitOperation {
    param([string]$GitDirPath)

    $markers = @(
        "MERGE_HEAD",
        "REBASE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG"
    )

    foreach ($marker in $markers) {
        $markerPath = Join-Path $GitDirPath $marker
        if (Test-Path $markerPath) {
            Stop-WithError -Step "validacion git" -Message "Hay una operacion Git incompleta: $markerPath" -Details "Resuelve o aborta esa operacion antes de publicar una version."
        }
    }
}

Test-CommandInstalled -Name "git" -Step "validacion git"
Test-CommandInstalled -Name "python" -Step "validacion python"

$repoCheck = Invoke-Git -Step "validacion repositorio" -Arguments @("rev-parse", "--show-toplevel")
$resolvedRepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
$resolvedTopLevel = [System.IO.Path]::GetFullPath($repoCheck.Output)
if ($resolvedRepoRoot -ne $resolvedTopLevel) {
    Stop-WithError -Step "validacion repositorio" -Message "El script debe ejecutarse desde la raiz real del repositorio." -Details "Esperado: $resolvedTopLevel`nActual:   $resolvedRepoRoot"
}

$gitDirRaw = Invoke-Git -Step "validacion git" -Arguments @("rev-parse", "--git-dir")
$gitDirPath = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $gitDirRaw.Output))
Test-IncompleteGitOperation -GitDirPath $gitDirPath

$originUrl = (Invoke-Git -Step "validacion remoto" -Arguments @("remote", "get-url", "origin")).Output
if ($originUrl -notmatch '(^|[/:])jjdominguez79/Gest2A3Eco(\.git)?$') {
    Stop-WithError -Step "validacion remoto" -Message "El remoto origin no apunta a jjdominguez79/Gest2A3Eco." -Details "URL detectada: $originUrl"
}

$currentBranch = (Invoke-Git -Step "validacion rama" -Arguments @("branch", "--show-current")).Output
if ($currentBranch -ne "main") {
    Stop-WithError -Step "validacion rama" -Message "La rama actual debe ser main." -Details "Rama detectada: $currentBranch"
}

$localChangesBefore = (Invoke-Git -Step "estado git" -Arguments @("status", "--short", "--untracked-files=all") -AllowedExitCodes @(0, 1)).Output
$includeLocalChanges = $false
if ($localChangesBefore) {
    Write-Step "Cambios locales detectados"
    Write-Host $localChangesBefore -ForegroundColor Yellow
    $includeAnswer = Read-Host "Hay cambios locales sin confirmar. Quieres incluirlos en la nueva version? S/N"
    $includeLocalChanges = $includeAnswer -match "^[sS]$"
}

Write-Step "Sincronizando con origin/main"
Invoke-Git -Step "git fetch" -Arguments @("fetch", "origin") -ShowOutput | Out-Null
Invoke-Git -Step "git pull" -Arguments @("pull", "--ff-only", "origin", "main") -ShowOutput | Out-Null

$conflicts = (Invoke-Git -Step "estado git" -Arguments @("ls-files", "--unmerged")).Output
if ($conflicts) {
    Stop-WithError -Step "validacion git" -Message "Existen conflictos Git sin resolver." -Details $conflicts
}

$currentVersion = (Invoke-Python -Step "leer version actual" -Arguments @("-m", "release_utils", "read-app-version")).Output
Write-Host ""
Write-Host "Version actual: $currentVersion" -ForegroundColor Green
$newVersion = Read-Host "Nueva version"

if ($newVersion -notmatch "^\d+\.\d+\.\d+$") {
    Stop-WithError -Step "validacion version" -Message "La nueva version debe tener formato X.Y.Z exacto." -Details "Ejemplos validos: 1.2.2, 1.3.0, 2.0.0"
}

$comparison = (Invoke-Python -Step "comparar versiones" -Arguments @("-m", "release_utils", "compare", $currentVersion, $newVersion)).Output
if ([int]$comparison -ge 0) {
    Stop-WithError -Step "validacion version" -Message "La nueva version debe ser mayor que la version actual." -Details "Actual: $currentVersion`nNueva:  $newVersion"
}

$newTag = "v$newVersion"
$installerName = "Setup_Gest2A3Eco_$newVersion.exe"

$localTagCheck = Invoke-Git -Step "validacion tag local" -Arguments @("rev-parse", "--verify", "--quiet", "refs/tags/$newTag") -AllowedExitCodes @(0, 1)
if ($localTagCheck.ExitCode -eq 0) {
    Stop-WithError -Step "validacion tag local" -Message "El tag $newTag ya existe localmente."
}

$remoteTagCheck = Invoke-Git -Step "validacion tag remoto" -Arguments @("ls-remote", "--exit-code", "--tags", "origin", "refs/tags/$newTag") -AllowedExitCodes @(0, 2)
if ($remoteTagCheck.ExitCode -eq 0) {
    Stop-WithError -Step "validacion tag remoto" -Message "El tag $newTag ya existe en origin."
}

$changelog = Read-MultilineChangelog
if ([string]::IsNullOrWhiteSpace($changelog)) {
    Stop-WithError -Step "validacion changelog" -Message "El changelog no puede estar vacio."
}

$forceAnswer = Read-Host "La actualizacion sera obligatoria? S/N"
$forceUpdate = $forceAnswer -match "^[sS]$"
$forceText = if ($forceUpdate) { "Si" } else { "No" }

Write-Step "Resumen de publicacion"
Write-Host "Version actual:           $currentVersion"
Write-Host "Nueva version:            $newVersion"
Write-Host "Tag:                      $newTag"
Write-Host "Instalador esperado:      $installerName"
Write-Host "Actualizacion obligatoria $forceText"
Write-Host "Cambios locales extra:    $(if ($includeLocalChanges) { 'Se incluiran' } else { 'No se incluiran' })"
Write-Host ""
Write-Host "Changelog:"
Write-Host $changelog
Write-Host ""

$confirmation = Read-Host "Escribe PUBLICAR para continuar"
if ($confirmation -ne "PUBLICAR") {
    Stop-WithError -Step "confirmacion final" -Message "La publicacion ha sido cancelada. No se realizaron cambios."
}

$tempChangelogPath = [System.IO.Path]::GetTempFileName()
try {
    Set-Content -LiteralPath $tempChangelogPath -Value $changelog -Encoding UTF8

    Write-Step "Actualizando archivos de version"
    Invoke-Python -Step "actualizar version" -Arguments @("-m", "release_utils", "update-files", "--version", $newVersion) | Out-Null

    $metadataArgs = @(
        "-m", "release_utils", "write-release-metadata",
        "--version", $newVersion,
        "--output", "updates/release_metadata.json",
        "--changelog-file", $tempChangelogPath
    )
    if ($forceUpdate) {
        $metadataArgs += "--force-update"
    }
    Invoke-Python -Step "generar release metadata" -Arguments $metadataArgs | Out-Null

    $releaseState = Invoke-Python -Step "validar coherencia de version" -Arguments @(
        "-m", "release_utils", "validate-release-state",
        "--tag", $newTag,
        "--repo", "jjdominguez79/Gest2A3Eco",
        "--app-version-file", "app_version.py",
        "--setup-file", "setup.iss",
        "--metadata-file", "updates/release_metadata.json"
    )
    Write-Host $releaseState.Output

    Write-Step "Preparando commit"
    if ($includeLocalChanges) {
        Invoke-Git -Step "git add" -Arguments @("add", "-A")
    }
    else {
        Invoke-Git -Step "git add" -Arguments @("add", "--", "app_version.py", "setup.iss", "updates/release_metadata.json")
    }

    Invoke-Git -Step "git commit" -Arguments @("commit", "-m", "Preparar versión $newVersion") -ShowOutput
    Invoke-Git -Step "git push main" -Arguments @("push", "origin", "main") -ShowOutput
    Invoke-Git -Step "git tag" -Arguments @("tag", "-a", $newTag, "-m", "Gest2A3Eco $newVersion")
    Invoke-Git -Step "git push tag" -Arguments @("push", "origin", $newTag) -ShowOutput

    Write-Host ""
    Write-Host "La versión $newVersion ha sido enviada a GitHub." -ForegroundColor Green
    Write-Host "GitHub Actions está compilando y publicando la Release." -ForegroundColor Green
}
finally {
    if (Test-Path $tempChangelogPath) {
        Remove-Item -LiteralPath $tempChangelogPath -Force
    }
}
