# Dot-source this script to activate the project environment in the current shell.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'conda_common.ps1')
Enter-DemoEnvironment
Write-Output "Activated: $DemoEnvironmentPath"
