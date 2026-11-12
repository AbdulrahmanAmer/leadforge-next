# Smoke run of the built window with a picture of the real window, no person needed. Windows PowerShell 5.1.
# Starts the app with --smoke, waits for the core's log line "engine_version ok", lets the page paint, captures the
# app's own window with PrintWindow (PW_RENDERFULLCONTENT, so other windows on top do not matter), waits for the
# app's own smoke exit (or stops it), prints this run's core.log lines. Exit 0 only when all of that held.
# Usage: smoke-window.ps1 -Exe <app.exe> -Png <screenshot.png>
param([Parameter(Mandatory = $true)][string]$Exe, [Parameter(Mandatory = $true)][string]$Png)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class Win {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
'@
$log = Join-Path $env:LOCALAPPDATA 'app.leadforge.window\logs\core.log'
$start = 0
if (Test-Path $log) { $start = (Get-Item $log).Length }
$p = Start-Process -FilePath $Exe -ArgumentList '--smoke' -PassThru
$ok = $false; $shot = $false
for ($i = 0; $i -lt 120 -and -not $p.HasExited; $i++) {
    Start-Sleep -Milliseconds 250
    if (-not (Test-Path $log)) { continue }
    $fs = [IO.File]::Open($log, 'Open', 'Read', 'ReadWrite'); $fs.Seek($start, 'Begin') | Out-Null
    $new = (New-Object IO.StreamReader($fs)).ReadToEnd(); $fs.Close()
    if ($new -match 'engine_version (ok|error)') { $ok = $new -match 'engine_version ok'; break }
}
Start-Sleep -Milliseconds 900
$p.Refresh()
$h = $p.MainWindowHandle
if ($h -ne [IntPtr]::Zero) {
    $r = New-Object Win+RECT
    [Win]::GetWindowRect($h, [ref]$r) | Out-Null
    $bmp = New-Object Drawing.Bitmap ($r.Right - $r.Left), ($r.Bottom - $r.Top)
    $g = [Drawing.Graphics]::FromImage($bmp); $hdc = $g.GetHdc()
    $shot = [Win]::PrintWindow($h, $hdc, 2)
    $g.ReleaseHdc($hdc); $g.Dispose(); $bmp.Save($Png, [Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    "window '{0}' {1}x{2}, screenshot {3}: {4}" -f $p.MainWindowTitle, ($r.Right - $r.Left), ($r.Bottom - $r.Top), $shot, $Png
} else { 'no main window handle' }
if (-not $p.WaitForExit(15000)) { 'app did not exit by itself: stopping it'; Stop-Process -Id $p.Id -Force; $ok = $false }
"app exit code: $($p.ExitCode)"
$fs = [IO.File]::Open($log, 'Open', 'Read', 'ReadWrite'); $fs.Seek($start, 'Begin') | Out-Null
'core.log lines of this run:'; (New-Object IO.StreamReader($fs)).ReadToEnd().TrimEnd(); $fs.Close()
if ($ok -and $shot -and $p.ExitCode -eq 0) { exit 0 } else { exit 1 }
