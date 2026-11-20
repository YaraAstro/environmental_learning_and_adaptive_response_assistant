# Launch the local browser UI with the existing Ollama profile.
$ErrorActionPreference = 'Stop'
& "$PSScriptRoot\uv.ps1" run --extra api elara --config "$PSScriptRoot\..\config\elara.ollama.example.toml" ui @args
exit $LASTEXITCODE
