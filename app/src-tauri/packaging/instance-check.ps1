# Item 6 proof: a second copy of the app does not open a window or start an engine; it asks the first copy to come to
# the front and exits. Windows PowerShell 5.1. Shows the first copy's window for a few seconds, then closes it.
# Usage: instance-check.ps1 -Exe <app.exe>
param([Parameter(Mandatory = $true)][string]$Exe)
$ErrorActionPreference = 'Stop'
$log = Join-Path $env:LOCALAPPDATA 'app.leadforge.window\logs\core.log'
$start = 0
if (Test-Path $log) { $start = (Get-Item $log).Length }
$first = Start-Process -FilePath $Exe -PassThru
Start-Sleep -Seconds 4
$sw = [Diagnostics.Stopwatch]::StartNew()
$second = Start-Process -FilePath $Exe -PassThru
$ended = $second.WaitForExit(10000)
"second copy ended by itself: $ended after $([math]::Round($sw.Elapsed.TotalSeconds, 2)) s, exit code $($second.ExitCode)"
Start-Sleep -Seconds 1
$copies = @(Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($Exe)) -ErrorAction SilentlyContinue)
"copies running now: $($copies.Count)"
$first.CloseMainWindow() | Out-Null
if (-not $first.WaitForExit(10000)) { Stop-Process -Id $first.Id -Force; 'first copy had to be stopped' }
$fs = [IO.File]::Open($log, 'Open', 'Read', 'ReadWrite'); $fs.Seek($start, 'Begin') | Out-Null
'core.log lines of this run:'; (New-Object IO.StreamReader($fs)).ReadToEnd().TrimEnd(); $fs.Close()
$left = @(Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($Exe)) -ErrorAction SilentlyContinue)
"copies left after closing: $($left.Count)"
