# Start a real local conversation. Pass --save, --session UUID, or attachment flags as needed.
$ErrorActionPreference = 'Stop'
& "$PSScriptRoot\uv.ps1" run elara --config "$PSScriptRoot\..\config\elara.ollama.example.toml" chat @args
exit $LASTEXITCODE
