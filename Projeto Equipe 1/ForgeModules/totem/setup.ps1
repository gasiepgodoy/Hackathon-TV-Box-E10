# PowerShell wrapper for Mina Virtual Assistant setup
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}

if (-not $PythonCmd) {
    Write-Error "Python executable not found in PATH! Please install Python 3.9+."
    exit 1
}

Write-Host "=== Starting Mina Assistant Cross-Platform Installation ===" -ForegroundColor Cyan
& $PythonCmd.Source install.py $args
