# The real window (WebView2), walked by the core's own --selftest, pictured without a person. Windows PowerShell 5.1.
# Starts the app with --selftest, follows the core's log, takes a picture of the app's own window (PrintWindow with
# PW_RENDERFULLCONTENT, so windows on top do not matter) at every "selftest: shot <name>" line, waits for the app to
# exit by itself (bounded), prints this run's log lines, searches them for the self-test's key marker, and checks
# the log for the commands the walk must have caused (the run itself, not only the pictures).
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
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
    // the app's own window, never the console a debug build also owns (MainWindowHandle may name either)
    public static IntPtr AppWindow(uint pid) {
        IntPtr found = IntPtr.Zero;
        EnumWindows(delegate (IntPtr h, IntPtr l) {
            uint p; GetWindowThreadProcessId(h, out p);
            if (p != pid || !IsWindowVisible(h)) return true;
            var cls = new System.Text.StringBuilder(256); GetClassName(h, cls, 256);
            if (cls.ToString() == "ConsoleWindowClass" || cls.ToString().StartsWith("CASCADIA")) return true;
            found = h; return false;
        }, IntPtr.Zero);
        return found;
    }
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
    $h = [LfWin]::AppWindow([uint32]$p.Id)
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
# Bounds (a failing walk once kept the window on the owner's screen for three minutes): the whole walk 120 s, and
# 20 s for each step: when no new "selftest:" line reaches the log for 20 s, the walk is stuck and the app is stopped.
$walkBound = [TimeSpan]::FromSeconds(120)
$stepBound = [TimeSpan]::FromSeconds(20)
$clock = [Diagnostics.Stopwatch]::StartNew()
$lastStep = $clock.Elapsed
$steps = 0
$bounded = ''
while (-not $p.HasExited) {
    Start-Sleep -Milliseconds 200
    $text = Read-New
    $now = ([regex]::Matches($text, 'selftest: ')).Count
    if ($now -ne $steps) { $steps = $now; $lastStep = $clock.Elapsed }
    foreach ($m in [regex]::Matches($text, 'selftest: shot (\S+)')) {
        $name = $m.Groups[1].Value
        if (-not $taken.ContainsKey($name)) {
            $file = Join-Path $Shots ($name + '.png')
            $taken[$name] = Shot $p $file
            "shot {0}: {1}" -f $name, $taken[$name]
        }
    }
    if ($clock.Elapsed -gt $walkBound) { $bounded = 'the whole walk passed its 120 s bound'; break }
    if (($clock.Elapsed - $lastStep) -gt $stepBound) { $bounded = 'no step of the walk for 20 s'; break }
}
if ($bounded) { "SELFTEST BOUND: $bounded; stopping the app"; Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
if (-not $p.WaitForExit(10000)) { 'app did not exit by itself: stopping it'; Stop-Process -Id $p.Id -Force }
"walk took {0:N0} s" -f $clock.Elapsed.TotalSeconds
"app exit code: $($p.ExitCode)"
$new = Read-New
'core.log lines of this run:'; $new.TrimEnd()
$leak = $new.Contains('LF-SELFTEST-KEY-7f3a9c51')
"key marker in this run's log: $leak"
$clean = $new -match 'selftest: probe "\{\\"violations\\":\[\],\\"errors\\":\[\]\}"'
$shots = @($taken.Values | Where-Object { $_ }).Count
"shots taken: $shots of 11; probe clean: $clean"
# What the core's own log of THIS run must show, in this order. A walk that took its pictures but never started a run
# proves nothing about the run: every missed expectation prints a line saying which one.
$rows = @($new -split "`r?`n" | Where-Object { $_ -ne '' })
$missed = @()
function Find-Row([string]$pattern, [int]$after) {
    for ($k = $after + 1; $k -lt $rows.Count; $k++) { if ($rows[$k] -match $pattern) { return $k } }
    return -1
}
function Expect([string]$what, [string]$pattern, [int]$after) {
    $k = Find-Row $pattern $after
    if ($k -lt 0) { $script:missed += "SELFTEST EXPECTATION MISSED: $what (log pattern: $pattern)"; return $after }
    return $k
}
# the error path, once on purpose: the incomplete form is refused with kind input and the refusal is on the screen
$e = Expect 'the incomplete campaign is refused with kind input (campaign_create error kind=input)' 'cmd=campaign_create .* error kind=input' -1
$null = Expect 'the refusal is on screen (02-campaign-error shows the field problem)' 'selftest: shows 02-campaign-error: .*at least one' $e
# the run, in order
$c = Expect 'campaign_create answered ok' 'cmd=campaign_create .* ok out=' $e
$s = Expect 'run_start relayed its handle' 'cmd=run_start handle relayed' $c
$t = Expect 'run_stop answered ok' 'cmd=run_stop .* ok out=' $s
$r = Expect 'run_start ended ok with at least one stream line after the handle (lines=2 or more)' 'cmd=run_start .* ok out=\d+B lines=([2-9]|\d\d+) ' $s
# a start the engine refuses (stand-in case standin-refuse): the core rejects run_start with the engine's own
# document (kind input), and the Run screen shows the start refused (the engine's message and "Try again")
$f = Expect 'the refused start: the core rejected run_start (line 1 was not a run handle)' 'cmd=run_start rejected: line 1 was not a run handle' $r
$null = Expect "the refused start: run_start logged with the engine's kind (error kind=input lines=0)" 'cmd=run_start .* error kind=input lines=0 ' $r
$null = Expect 'the refused start is on screen (05b-run-refused: Try again, then the message)' 'selftest: shows 05b-run-refused: "run \| .*Try again.*could not start the run' $f
# every screen's own data command answered ok after the run was stopped
foreach ($cmd in 'campaigns_list', 'people_list', 'purge_report', 'retention_get', 'keys_list', 'key_save', 'settings_get', 'about') {
    $null = Expect "$cmd answered ok" "cmd=$cmd .* ok out=" $t
}
if ($bounded) { $missed += "SELFTEST EXPECTATION MISSED: the walk ended within its bounds ($bounded)" }
foreach ($m in $missed) { $m }
$ran = ($missed.Count -eq 0)
"expectations missed: $($missed.Count)"
if ($p.ExitCode -eq 0 -and $shots -eq 11 -and $clean -and -not $leak -and $ran) { 'SELFTEST PASS'; exit 0 } else { 'SELFTEST FAIL'; exit 1 }
