# Measures one engine packaging: size on disk, `version` start-up time three runs (the first is the first start after
# the build, cold for the engine's own files), Defender's verdict (a custom scan of the folder, then the threat
# detections since the start, then whether the program file still exists). Windows PowerShell 5.1.
# Usage: measure-engine.ps1 -Label <name> -Dir <folder> -Program <exe> [-Prefix <args before the command>]
param(
    [Parameter(Mandatory = $true)][string]$Label,
    [Parameter(Mandatory = $true)][string]$Dir,
    [Parameter(Mandatory = $true)][string]$Program,
    [string[]]$Prefix = @()
)
$ErrorActionPreference = 'Stop'
$since = Get-Date
$files = Get-ChildItem -Recurse -File $Dir
$bytes = ($files | Measure-Object -Sum Length).Sum
$work = Join-Path $env:TEMP ('lf-measure-' + $Label)
New-Item -ItemType Directory -Force $work | Out-Null
$times = @()
for ($i = 1; $i -le 3; $i++) {
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $Program
    $psi.Arguments = (($Prefix + @('--json', 'version')) -join ' ')
    $psi.WorkingDirectory = $work
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.CreateNoWindow = $true
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = [Diagnostics.Process]::Start($psi)
    $stdout = $p.StandardOutput.ReadToEnd()
    if (-not $p.WaitForExit(120000)) { $p.Kill(); $times += 'timeout'; continue }
    $sw.Stop()
    $first = ($stdout -split "`n")[0].Trim()
    $times += ('{0:N2}s' -f $sw.Elapsed.TotalSeconds) + "(exit $($p.ExitCode), '$first')"
}
$scan = & "$env:ProgramFiles\Windows Defender\MpCmdRun.exe" -Scan -ScanType 3 -File $Dir -DisableRemediation 2>&1 | Out-String
$found = @(Get-MpThreatDetection -ErrorAction SilentlyContinue | Where-Object { $_.InitialDetectionTime -ge $since })
$verdict = if ($found.Count -eq 0) { 'no detection' } else { "DETECTIONS: $($found.Count) " + (($found | ForEach-Object { $_.Resources }) -join ';') }
$scanLine = (($scan -split "`r?`n") | Where-Object { $_ -match 'threat|found' } | Select-Object -First 1)
"{0}: {1:N1} MB in {2} files; starts: {3}; Defender scan: {4}; detections since start: {5}; program file present after: {6}" -f `
    $Label, ($bytes / 1MB), $files.Count, ($times -join ', '), $scanLine, $verdict, (Test-Path $Program)
Remove-Item -Recurse -Force $work
