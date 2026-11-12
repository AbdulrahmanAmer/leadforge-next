# The real window (WebView2), walked by the core's own --selftest, pictured without a person. Windows PowerShell 5.1.
# Starts the app with --selftest, follows the core's log, takes a picture of the app's own window (PrintWindow with
# PW_RENDERFULLCONTENT, so windows on top do not matter) at every "selftest: shot <name>" line, waits for the app to
# exit by itself (bounded), prints this run's log lines, and searches them for the self-test's key marker.
# Usage: selftest-window.ps1 -Exe <app.exe> -Shots <folder>
param([Parameter(Mandatory = $true)][string]$Exe, [Parameter(Mandatory = $true)][string]$Shots)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class LfWin {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
}
'@
New-Item -ItemType Directory -Force $Shots | Out-Null
$log = Join-Path $env:LOCALAPPDATA 'app.leadforge.window\logs\core.log'
$start = 0
if (Test-Path $log) { $start = (Get-Item $log).Length }
function Read-New {
    if (-not (Test-Path $log)) { return '' }
    $fs = [IO.File]::Open($log, 'Open', 'Read', 'ReadWrite'); $fs.Seek($start, 'Begin') | Out-Null
    $t = (New-Object IO.StreamReader($fs)).ReadToEnd(); $fs.Close(); return $t
}
function Shot([Diagnostics.Process]$p, [string]$file) {
    $p.Refresh(); $h = $p.MainWindowHandle
    if ($h -eq [IntPtr]::Zero) { return $false }
    $r = New-Object LfWin+RECT; [LfWin]::GetWindowRect($h, [ref]$r) | Out-Null
    $bmp = New-Object Drawing.Bitmap ($r.Right - $r.Left), ($r.Bottom - $r.Top)
    $g = [Drawing.Graphics]::FromImage($bmp); $hdc = $g.GetHdc()
    $ok = [LfWin]::PrintWindow($h, $hdc, 2)
    $g.ReleaseHdc($hdc); $g.Dispose(); $bmp.Save($file, [Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    return $ok
}
$p = Start-Process -FilePath $Exe -ArgumentList '--selftest' -PassThru
$taken = @{}
for ($i = 0; $i -lt 900 -and -not $p.HasExited; $i++) {   # 900 x 200 ms = 3 minutes at most
    Start-Sleep -Milliseconds 200
    foreach ($m in [regex]::Matches((Read-New), 'selftest: shot (\S+)')) {
        $name = $m.Groups[1].Value
        if (-not $taken.ContainsKey($name)) {
            $file = Join-Path $Shots ($name + '.png')
            $taken[$name] = Shot $p $file
            "shot {0}: {1}" -f $name, $taken[$name]
        }
    }
}
if (-not $p.WaitForExit(10000)) { 'app did not exit by itself: stopping it'; Stop-Process -Id $p.Id -Force }
"app exit code: $($p.ExitCode)"
$new = Read-New
'core.log lines of this run:'; $new.TrimEnd()
$leak = $new.Contains('LF-SELFTEST-KEY-7f3a9c51')
"key marker in this run's log: $leak"
$clean = $new -match 'selftest: probe "\{\\"violations\\":\[\],\\"errors\\":\[\]\}"'
$shots = @($taken.Values | Where-Object { $_ }).Count
"shots taken: $shots of 10; probe clean: $clean"
if ($p.ExitCode -eq 0 -and $shots -eq 10 -and $clean -and -not $leak) { 'SELFTEST PASS'; exit 0 } else { 'SELFTEST FAIL'; exit 1 }
