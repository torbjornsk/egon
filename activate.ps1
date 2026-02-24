# Quick activation script for PowerShell
# Usage: . .\activate.ps1

$venvPath = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"

if (Test-Path $venvPath) {
    & $venvPath
    Write-Host "✓ Virtual environment activated" -ForegroundColor Green
    Write-Host "Python: $(python --version)" -ForegroundColor Cyan
    Write-Host "Location: $PWD" -ForegroundColor Cyan
} else {
    Write-Host "✗ Virtual environment not found at $venvPath" -ForegroundColor Red
    Write-Host "Run: uv venv" -ForegroundColor Yellow
}
