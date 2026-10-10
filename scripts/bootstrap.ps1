$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python scripts/manage.py up @args
exit $LASTEXITCODE
