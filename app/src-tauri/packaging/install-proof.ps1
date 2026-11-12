# Item 5 proof: the per-user installer installs with the user's own rights into a scratch folder, the installed app shows
# the bundled engine's version, and the uninstaller leaves no process and no file there. Windows PowerShell 5.1.
# Run from an ordinary (NOT elevated) PowerShell; it refuses to run elevated, because an elevated run proves nothing.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File install-proof.ps1 -Setup <LeadForge_x.y.z_x64-setup.exe>
param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [string]$Dir = 'D:\Temp\lf-install\LeadForge'
)
$ErrorActionPreference = 'Stop'
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if ((New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    'REFUSED: this PowerShell is elevated; open an ordinary one'; exit 2
}
if (Test-Path $Dir) { "REFUSED: $Dir already exists"; exit 2 }
$exe = Join-Path $Dir 'leadforge-window.exe'

# /S silent, /NS no shortcuts (no Start menu, no desktop), /D= the scratch folder (must be last, unquoted).
$p = Start-Process -FilePath $Setup -ArgumentList '/S', '/NS', "/D=$Dir" -PassThru -Wait
"install exit code: $($p.ExitCode); app present: $(Test-Path $exe); engine present: $(Test-Path (Join-Path $Dir 'engine\python\python.exe'))"
$files = @(Get-ChildItem -Recurse -File $Dir -ErrorAction SilentlyContinue)
"installed: {0} files, {1:N1} MB" -f $files.Count, (($files | Measure-Object -Sum Length).Sum / 1MB)

& (Join-Path $PSScriptRoot 'smoke-window.ps1') -Exe $exe -Png (Join-Path $env:TEMP 'lf-install-smoke.png')
"installed app smoke exit: $LASTEXITCODE"

$un = Join-Path $Dir 'uninstall.exe'
Start-Process -FilePath $un -ArgumentList '/S' -Wait | Out-Null
for ($i = 0; $i -lt 120; $i++) {   # the uninstaller copies itself to %TEMP% and runs from there: wait for it
    $left = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Dir*" -or $_.ProcessName -like 'Au_*' })
    if ((-not (Test-Path $Dir)) -and $left.Count -eq 0) { break }
    Start-Sleep -Milliseconds 500
}
$procs = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -like 'D:\Temp\lf-install*' })
$rest = @(Get-ChildItem -Recurse -Force 'D:\Temp\lf-install' -ErrorAction SilentlyContinue)
"after uninstall: processes from D:\Temp\lf-install: $($procs.Count); files or folders left there: $($rest.Count) $(($rest | ForEach-Object FullName) -join '; ')"
"uninstall registry key left: $(Test-Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadForge')"
if ($procs.Count -eq 0 -and $rest.Count -eq 0) { 'PASS'; exit 0 } else { 'FAIL'; exit 1 }
