# Packaging (a): the engine as one PyInstaller file. Windows PowerShell 5.1.
# A throwaway build venv (outside the repo) gets the engine's hashed lock plus PyInstaller's hashed pins, wheels only,
# then the engine as a wheel without deps; PyInstaller freezes `python -m leadforge`.
# Output: <repo>\build\engine-pyinstaller\leadforge.exe
# Run through the heavy lock:  node heavy.mjs run -- powershell -NoProfile -ExecutionPolicy Bypass -File build-engine-pyinstaller.ps1 <venv dir>
param([Parameter(Mandatory = $true)][string]$Venv)
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$Out = Join-Path $Repo 'build\engine-pyinstaller'
$Work = Join-Path $Repo 'build\pyinstaller-work'
$Py = Join-Path $Venv 'Scripts\python.exe'

if (-not (Test-Path $Py)) {
    & python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { exit 2 }
    & $Py -m pip install --disable-pip-version-check --require-hashes --only-binary :all: `
        -r (Join-Path $Repo 'requirements.lock') -r (Join-Path $PSScriptRoot 'requirements-pyinstaller.txt')
    if ($LASTEXITCODE -ne 0) { exit 3 }
    & $Py -m pip install --disable-pip-version-check --no-deps --no-build-isolation $Repo
    if ($LASTEXITCODE -ne 0) { exit 4 }
}
foreach ($d in @($Out, $Work)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
$entry = Join-Path $Work 'lf_entry.py'
New-Item -ItemType Directory -Force $Work | Out-Null
[IO.File]::WriteAllText($entry, "from leadforge.cli import main`r`nmain()`r`n", (New-Object Text.UTF8Encoding $false))
# --collect-data leadforge: the packaged yaml files (rubric, skeletons) the engine reads at run time.
& $Py -m PyInstaller --noconfirm --onefile --console --name leadforge --distpath $Out --workpath $Work `
    --specpath $Work --collect-data leadforge --collect-submodules leadforge $entry
if ($LASTEXITCODE -ne 0) { exit 5 }
& (Join-Path $Out 'leadforge.exe') --json version
exit $LASTEXITCODE
