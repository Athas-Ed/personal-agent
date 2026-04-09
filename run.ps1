$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

Write-Host "[INFO] Using launcher run.bat (venv enforced)."

if ($args.Count -gt 0) {
  & "$PSScriptRoot\\run.bat" @args
} else {
  & "$PSScriptRoot\\run.bat"
}

exit $LASTEXITCODE

