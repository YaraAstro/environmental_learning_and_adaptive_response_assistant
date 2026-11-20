# Run from a normal PowerShell session to verify the complete local application.
[CmdletBinding()]
param(
    [switch]$CheckOllama,
    [switch]$RebuildUI
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$failedChecks = [System.Collections.Generic.List[string]]::new()

function Invoke-Check {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "`nChecking: $Name"
    try {
        & $Command
        if ($LASTEXITCODE -ne 0) { throw "Command exited with code $LASTEXITCODE" }
        Write-Host "PASS: $Name" -ForegroundColor Green
    } catch {
        $failedChecks.Add($Name)
        Write-Host "FAIL: $Name - $($_.Exception.Message)" -ForegroundColor Red
    }
}

Push-Location $projectRoot
try {
    if ($RebuildUI) {
        Push-Location (Join-Path $projectRoot 'frontend')
        try {
            Invoke-Check 'Install locked frontend dependencies' { & npm ci }
            Invoke-Check 'Type-check and build frontend' { & npm run build }
        } finally { Pop-Location }
    }
    Invoke-Check 'Install locked Python dependencies' {
        & "$PSScriptRoot\uv.ps1" sync --locked --all-extras
    }
    Invoke-Check 'Python lint' { & "$PSScriptRoot\uv.ps1" run --no-sync ruff check src tests }
    Invoke-Check 'Python types' { & "$PSScriptRoot\uv.ps1" run --no-sync mypy }
    Invoke-Check 'Full test suite, including async SDK and HTTP tests' {
        & "$PSScriptRoot\uv.ps1" run --no-sync pytest -q
    }
    Invoke-Check 'Local application diagnostics' {
        & "$PSScriptRoot\uv.ps1" run --no-sync elara --config config/elara.example.toml doctor
    }
    Invoke-Check 'Python distributions' { & "$PSScriptRoot\uv.ps1" build }
    if ($CheckOllama) {
        Invoke-Check 'Installed Ollama model metadata (no generation)' {
            & "$PSScriptRoot\uv.ps1" run --no-sync elara --config config/elara.ollama.example.toml provider check
        }
    }
} finally { Pop-Location }

if ($failedChecks.Count) {
    Write-Host "`nVerification failed: $($failedChecks -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "`nAll requested automated checks passed." -ForegroundColor Green
Write-Host 'Browser media decoding and live attachment replies still require the manual smoke check in docs/next-steps.md.'
exit 0
