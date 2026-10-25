param([switch]$InstallDependencies)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'conda_common.ps1')
$env:JUPYTER_PATH = Join-Path $DemoEnvironmentPath 'share/jupyter'
if (-not (Test-Path -LiteralPath (Join-Path $DemoEnvironmentPath 'conda-meta/history'))) {
    throw 'Create the project Conda environment with setup_env.ps1 first.'
}
foreach ($Setting in @{
    JUPYTER_RUNTIME_DIR = 'jupyter-runtime'
    JUPYTER_CONFIG_DIR = 'jupyter-config'
    JUPYTER_DATA_DIR = 'jupyter-data'
    IPYTHONDIR = 'ipython'
}.GetEnumerator()) {
    $CachePath = Join-Path $PSScriptRoot ('.cache/' + $Setting.Value)
    New-Item -ItemType Directory -Force -Path $CachePath | Out-Null
    [Environment]::SetEnvironmentVariable($Setting.Key, $CachePath, 'Process')
}
if ($InstallDependencies) {
    Invoke-DemoPython (Join-Path $PSScriptRoot 'notebook_tools/install_dependencies.py') -r (Join-Path $PSScriptRoot 'requirements-notebook-lock.txt')
}
Invoke-DemoPython -c 'import ipykernel, nbformat, nbclient, jupyterlab'
Invoke-DemoPython -m ipykernel install --prefix $DemoEnvironmentPath --name defective-cnot-d3 --display-name 'Conda defective-cnot-d3 (Python 3.12)'
Push-Location -LiteralPath $PSScriptRoot
try {
    # Keep a foreground server; user can open its local URL and stop with Ctrl+C.
    Invoke-DemoPython -m jupyter lab --no-browser defective_cnot_d3_walkthrough.ipynb
} finally {
    Pop-Location
}
