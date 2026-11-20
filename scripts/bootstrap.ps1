# Requires internet access. Does not alter system Python or the global PATH.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'uv.ps1'
$localUvRoot = Join-Path $projectRoot '.tools\uv-package'
$localUv = Get-ChildItem -LiteralPath $localUvRoot -Recurse -Filter uv.exe `
    -ErrorAction SilentlyContinue | Select-Object -First 1
Push-Location $projectRoot
try {
    if (-not $localUv -and
        -not (Get-Command uv -CommandType Application -ErrorAction SilentlyContinue)) {
        & python -m pip install --disable-pip-version-check --no-cache-dir --retries 0 `
            --timeout 30 --index-url https://pypi.org/simple `
            --target (Join-Path $projectRoot '.tools\uv-package') uv
        if ($LASTEXITCODE -ne 0) { throw 'uv installation failed. Check access to PyPI.' }
    }
    & $runner python install 3.12
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 installation failed.' }
    if (Test-Path -LiteralPath 'uv.lock') {
        & $runner sync --locked --all-extras
    } else {
        & $runner sync --all-extras
    }
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & $runner run ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Lint checks failed.' }
    & $runner run mypy
    if ($LASTEXITCODE -ne 0) { throw 'Type checks failed.' }
    & $runner run pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    & $runner run elara doctor
    if ($LASTEXITCODE -ne 0) { throw 'ELARA doctor failed.' }
    & $runner build
    if ($LASTEXITCODE -ne 0) { throw 'Package build failed.' }
    Write-Host 'ELARA setup verified. Try: .\scripts\uv.ps1 run elara chat'
} finally {
    Pop-Location
}
