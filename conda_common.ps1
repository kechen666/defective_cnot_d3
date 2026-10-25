# Shared project-local Conda paths. Dot-source from setup/launch scripts.
$DemoWorkspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$DemoEnvironmentPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '.conda/envs/defective-cnot-d3'))
$DemoCondaCommand = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue
if (-not $DemoCondaCommand) { throw 'Conda is unavailable. Run from Anaconda PowerShell Prompt or add its Scripts directory to PATH.' }
$DemoCondaExecutable = $DemoCondaCommand.Source
$env:CONDA_ENVS_PATH = Join-Path $PSScriptRoot '.conda/envs'
$env:CONDA_PKGS_DIRS = Join-Path $DemoWorkspace '.runtime/conda-pkgs'
$env:PIP_CACHE_DIR = Join-Path $DemoWorkspace '.runtime/pip-cache'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONIOENCODING = 'utf-8'
# Decode Conda's generated activation script correctly for Chinese paths in PS 5.1.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Enter-DemoEnvironment {
    if (-not (Test-Path -LiteralPath (Join-Path $DemoEnvironmentPath 'conda-meta/history'))) {
        throw 'Create the project Conda environment with setup_env.ps1 first.'
    }
    # Native activation also sets DLL search paths and runs activate.d scripts.
    # Unlike conda run on this installation, it does not force PYTHONUTF8=1.
    $DemoActivation = & $DemoCondaExecutable shell.powershell activate $DemoEnvironmentPath
    if ($LASTEXITCODE -ne 0) { throw 'Conda PowerShell activation failed.' }
    Invoke-Expression ($DemoActivation -join "`n")
    if ($env:CONDA_PREFIX -ne $DemoEnvironmentPath) { throw 'Incorrect activated Conda prefix.' }
}

function Invoke-DemoPython {
    if ($env:CONDA_PREFIX -ne $DemoEnvironmentPath) { Enter-DemoEnvironment }
    & (Join-Path $DemoEnvironmentPath 'python.exe') @args
    if ($LASTEXITCODE -ne 0) { throw "Conda environment command failed (exit $LASTEXITCODE)." }
}
