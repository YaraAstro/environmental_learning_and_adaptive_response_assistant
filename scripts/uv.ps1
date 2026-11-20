# Run uv with all downloaded tool/cache data kept inside this workspace.
# Usage: .\scripts\uv.ps1 sync --locked
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localUvRoot = Join-Path $projectRoot '.tools\uv-package'
$localUv = Get-ChildItem -LiteralPath $localUvRoot -Recurse -Filter uv.exe `
    -ErrorAction SilentlyContinue | Select-Object -First 1
$uvCommand = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue
if ($localUv) {
    $uvExecutable = $localUv.FullName
} elseif ($uvCommand) {
    $uvExecutable = $uvCommand.Source
} else {
    throw 'uv is unavailable. Run .\scripts\bootstrap.ps1 first.'
}

$previousCache = $env:UV_CACHE_DIR
$previousPythonDir = $env:UV_PYTHON_INSTALL_DIR
$previousManaged = $env:UV_MANAGED_PYTHON
$previousNoBin = $env:UV_PYTHON_INSTALL_BIN
$previousRegistry = $env:UV_PYTHON_INSTALL_REGISTRY
Push-Location $projectRoot
try {
    $env:UV_CACHE_DIR = Join-Path $projectRoot '.uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.tools\python'
    $env:UV_MANAGED_PYTHON = '1'
    $env:UV_PYTHON_INSTALL_BIN = '0'
    $env:UV_PYTHON_INSTALL_REGISTRY = '0'
    & $uvExecutable @args
    $result = $LASTEXITCODE
} finally {
    $env:UV_CACHE_DIR = $previousCache
    $env:UV_PYTHON_INSTALL_DIR = $previousPythonDir
    $env:UV_MANAGED_PYTHON = $previousManaged
    $env:UV_PYTHON_INSTALL_BIN = $previousNoBin
    $env:UV_PYTHON_INSTALL_REGISTRY = $previousRegistry
    Pop-Location
}
exit $result
