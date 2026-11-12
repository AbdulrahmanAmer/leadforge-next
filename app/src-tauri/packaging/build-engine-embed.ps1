# Packaging (b): python.org's embeddable Python with the engine's packages beside it. Windows PowerShell 5.1.
# Output: <repo>\build\engine-embed\python\ (python.exe, the stdlib zip, Lib\site-packages with the hashed lock and the engine).
# The zip must already be downloaded and checked against python.org's published SHA-256 (the script checks it again).
# Run through the heavy lock:  node heavy.mjs run -- powershell -NoProfile -ExecutionPolicy Bypass -File build-engine-embed.ps1 <zip>
param([Parameter(Mandatory = $true)][string]$Zip)
$ErrorActionPreference = 'Stop'
# python.org, Python 3.12.10, python-3.12.10-embed-amd64.zip: SHA-256 from its SBOM (.spdx.json), MD5 from its download API.
$Sha256 = '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$Out = Join-Path $Repo 'build\engine-embed'
$Py = Join-Path $Out 'python'
$Site = Join-Path $Py 'Lib\site-packages'

$got = (Get-FileHash -Algorithm SHA256 $Zip).Hash.ToLower()
if ($got -ne $Sha256) { Write-Error "embeddable zip hash $got differs from python.org's $Sha256"; exit 2 }
if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force $Py | Out-Null
Expand-Archive -Path $Zip -DestinationPath $Py

# The ._pth file is the embeddable interpreter's whole import path (isolated: no PYTHONPATH, no user site).
$pth = "python312.zip`r`n.`r`nLib\site-packages`r`n"
[IO.File]::WriteAllText((Join-Path $Py 'python312._pth'), $pth, (New-Object Text.UTF8Encoding $false))

# The engine's packages: the hashed lock, wheels only, for this exact interpreter; then the engine itself, no deps.
$build = Join-Path $Repo '.venv\Scripts\python.exe'
& $build -m pip install --disable-pip-version-check --no-compile --require-hashes --only-binary :all: `
    --python-version 3.12 --platform win_amd64 --implementation cp --target $Site -r (Join-Path $Repo 'requirements.lock')
if ($LASTEXITCODE -ne 0) { exit 3 }
$wheelDir = Join-Path $Repo 'build\engine-wheel'
if (Test-Path $wheelDir) { Remove-Item -Recurse -Force $wheelDir }
& $build -m pip wheel --disable-pip-version-check --no-deps --no-build-isolation -w $wheelDir $Repo
if ($LASTEXITCODE -ne 0) { exit 4 }
$whl = Get-ChildItem $wheelDir -Filter 'leadforge-*.whl' | Select-Object -First 1
& $build -m pip install --disable-pip-version-check --no-compile --no-deps --only-binary :all: `
    --python-version 3.12 --platform win_amd64 --implementation cp --target $Site $whl.FullName
if ($LASTEXITCODE -ne 0) { exit 5 }
# Bytecode once, at build time, so the first start does not write into the install folder.
& (Join-Path $Py 'python.exe') -I -m compileall -q -j 2 $Site | Out-Null
& (Join-Path $Py 'python.exe') -X utf8 -I -m leadforge --json version
exit $LASTEXITCODE
