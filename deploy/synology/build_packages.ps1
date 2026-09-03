[CmdletBinding()]
param(
    [string]$OutputRoot
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $scriptRoot '..\..')).Path
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $repoRoot 'dist_synology'
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$outputPath = (Resolve-Path -LiteralPath $OutputRoot).Path

$packages = @(
    @{
        Name = 'gest2a3eco-mail-sync'
        Modules = @('__init__.py', '__main__.py', 'config.py', 'graph.py', 'repository.py', 'worker.py')
    },
    @{
        Name = 'gest2a3eco-messaging-sync'
        Modules = @('__init__.py', 'config.py', 'messaging_worker.py')
    },
    @{
        Name = 'gest2a3eco-master-data-sync'
        Modules = @('__init__.py', 'config.py', 'master_data_worker.py')
    }
)

foreach ($package in $packages) {
    $templateRoot = Join-Path $scriptRoot $package.Name
    $packageRoot = Join-Path $outputPath $package.Name
    $workerRoot = Join-Path $packageRoot 'sync_worker'
    $secretRoot = Join-Path $packageRoot 'secrets'

    New-Item -ItemType Directory -Path $packageRoot, $workerRoot, $secretRoot -Force | Out-Null

    foreach ($file in @('compose.yaml', 'Dockerfile', 'requirements.txt', 'README.md')) {
        Copy-Item -LiteralPath (Join-Path $templateRoot $file) -Destination (Join-Path $packageRoot $file) -Force
    }
    Copy-Item -LiteralPath (Join-Path $templateRoot 'secrets\.gitignore') -Destination (Join-Path $secretRoot '.gitignore') -Force

    foreach ($module in $package.Modules) {
        Copy-Item -LiteralPath (Join-Path $repoRoot "sync_worker\$module") -Destination (Join-Path $workerRoot $module) -Force
    }
}

Write-Host "Paquetes Synology generados en: $outputPath"
Write-Host 'Los ficheros de secrets no se copian ni se modifican.'
