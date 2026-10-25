param([string]$TqecSource = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'conda_common.ps1')
if (-not $TqecSource) { $TqecSource = Join-Path $DemoWorkspace '.runtime/tqec-source' }
$CondaHistory = Join-Path $DemoEnvironmentPath 'conda-meta/history'
if (-not (Test-Path -LiteralPath $CondaHistory)) {
    if (Test-Path -LiteralPath $DemoEnvironmentPath) {
        throw 'The target directory exists but is not a Conda environment; it will not be overwritten.'
    }
    & $DemoCondaExecutable env create --prefix $DemoEnvironmentPath --file (Join-Path $PSScriptRoot 'environment.yml') --yes
    if ($LASTEXITCODE -ne 0) { throw 'Conda environment creation failed.' }
}
Enter-DemoEnvironment
Invoke-DemoPython -c 'import sys; assert sys.version_info[:2] == (3,12)'
Invoke-DemoPython (Join-Path $PSScriptRoot 'prepare_sources.py') --tqec-source $TqecSource
# Conda owns the interpreter; its pip installs the exact research package pins.
Invoke-DemoPython (Join-Path $PSScriptRoot 'notebook_tools/install_dependencies.py') -r (Join-Path $PSScriptRoot 'requirements-notebook-lock.txt') $TqecSource
Invoke-DemoPython -m pip check
Invoke-DemoPython -m ipykernel install --prefix $DemoEnvironmentPath --name defective-cnot-d3 --display-name 'Conda defective-cnot-d3 (Python 3.12)'
Invoke-DemoPython (Join-Path $PSScriptRoot 'notebook_tools/verify_conda_environment.py')
Write-Output "Ready: $DemoEnvironmentPath"
Write-Output 'Activate this shell with: . ./activate_env.ps1'
