# The real window (WebView2) on the REAL engine, walked by the core's own self-test, pictured without a person.
# Windows PowerShell 5.1.
#   selftest-window.ps1 -Exe <app.exe> -Shots <folder>              the short walk (--selftest): no run; the installed app's
#   selftest-window.ps1 -Exe <app.exe> -Shots <folder> -Campaign    the fake campaign (--selftest-campaign): debug build only
# Both: ONE throwaway folder, D:\Temp\lf-selftest (refused if its full path is anything else or it is a link), is the app's
# home for this run (USERPROFILE, APPDATA and LOCALAPPDATA of the app process point into it), so the app's workspace, log and
# WebView2 profile are fresh and the owner's own workspace is never touched. Its leadforge.yaml is the fake campaign's
# (scripts/e2e_fake_campaign.py CONFIG_YAML: registers on 127.0.0.1). -Campaign also starts the loopback fakes and puts the
# fakes' harness loader into the dev venv (packaging/fake_world.py), and after the walk compares the window's result with the
# same campaign through the command line (packaging/compare_campaign.py). Everything started is stopped, the loader and the
# folder are removed, and the verdict comes from the core's own log of THIS run.
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$Shots,
    [switch]$Campaign
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
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
$here = $PSScriptRoot
$repo = Split-Path (Split-Path (Split-Path $here -Parent) -Parent) -Parent
$venv = Join-Path $repo '.venv'
$py = Join-Path $venv 'Scripts\python.exe'
$root = 'D:\Temp\lf-selftest'
function Assert-Throwaway {
    $full = [IO.Path]::GetFullPath($root)
    if ($full -ne 'D:\Temp\lf-selftest') { throw "refused: $root resolves to $full" }
    if (Test-Path -LiteralPath $full) {
        if ((Get-Item -LiteralPath $full -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "refused: $full is a link" }
    }
    return $full
}
function Remove-Throwaway {
    $full = Assert-Throwaway
    if (Test-Path -LiteralPath $full) {
        # a link inside is removed as an entry, never followed
        Get-ChildItem -LiteralPath $full -Recurse -Force -Attributes ReparsePoint -ErrorAction SilentlyContinue | ForEach-Object { [IO.Directory]::Delete($_.FullName) }
        Remove-Item -LiteralPath $full -Recurse -Force
    }
}
Remove-Throwaway
$home2 = Join-Path $root 'home'
$saved = @{ USERPROFILE = $env:USERPROFILE; APPDATA = $env:APPDATA; LOCALAPPDATA = $env:LOCALAPPDATA }
$local = Join-Path $home2 'AppData\Local'
New-Item -ItemType Directory -Force $local, (Join-Path $home2 'AppData\Roaming'), $Shots | Out-Null
$ws = Join-Path $local 'app.leadforge.window\workspace'
$fakes = Join-Path $root 'fakes'
$stopFlag = Join-Path $root 'fakes.stop'
$snap = Join-Path $root 'exports-at-06'
$log = Join-Path $local 'app.leadforge.window\logs\core.log'
$serve = $null; $p = $null
$ErrorActionPreference = 'Continue'
if ($Campaign) {
    & $py -X utf8 (Join-Path $here 'fake_world.py') prepare --ws $ws --out $fakes
} else {
    & $py -X utf8 (Join-Path $here 'fake_world.py') prepare --ws $ws --out $fakes --registers-only
}
if ($Campaign) {
    & $py -X utf8 (Join-Path $here 'fake_world.py') loader on --venv $venv
    $serve = Start-Process -FilePath $py -ArgumentList @('-X', 'utf8', (Join-Path $here 'fake_world.py'), 'serve', '--out', $fakes, '--stop', $stopFlag, '--bound', '900') -PassThru -WindowStyle Hidden
}
function Read-New {
    if (-not (Test-Path $log)) { return '' }
    $fs = [IO.File]::Open($log, 'Open', 'Read', 'ReadWrite')
    $t = (New-Object IO.StreamReader($fs)).ReadToEnd(); $fs.Close(); return $t
}
function Shot([Diagnostics.Process]$proc, [string]$file) {
    $h = [LfWin]::AppWindow([uint32]$proc.Id)
    if ($h -eq [IntPtr]::Zero) { return $false }
    $r = New-Object LfWin+RECT; [LfWin]::GetWindowRect($h, [ref]$r) | Out-Null
    $bmp = New-Object Drawing.Bitmap ($r.Right - $r.Left), ($r.Bottom - $r.Top)
    $g = [Drawing.Graphics]::FromImage($bmp); $hdc = $g.GetHdc()
    $ok = [LfWin]::PrintWindow($h, $hdc, 2)
    $g.ReleaseHdc($hdc); $g.Dispose(); $bmp.Save($file, [Drawing.Imaging.ImageFormat]::Png)
    $w = $bmp.Width; $bmp.Dispose()
    # a picture of a minimised window is a title bar: it does not count
    return ($ok -and $w -ge 800)
}
function Engine([string]$name, [string]$json) {
    Push-Location $ws
    $o = ($json | & $py -X utf8 -I -m leadforge window $name 2>$null) -join "`n"
    Pop-Location
    return $o
}
$taken = @{}
$bounded = ''
$walkSeconds = 120; if ($Campaign) { $walkSeconds = 420 }
$expectShots = 8; if ($Campaign) { $expectShots = 14 }
try {
    $env:USERPROFILE = $home2; $env:APPDATA = (Join-Path $home2 'AppData\Roaming'); $env:LOCALAPPDATA = $local
    $arg = '--selftest'; if ($Campaign) { $arg = '--selftest-campaign' }
    # Normal, said explicitly: started from a hidden parent (a lock wrapper, a scheduled job) the window would inherit a
    # minimised show state, and every picture was the 160 x 28 title bar (walks 1 and 2 of 2026-11-12)
    $p = Start-Process -FilePath $Exe -ArgumentList $arg -PassThru -WindowStyle Normal
    # Bounds: the whole walk ($walkSeconds s; the core ends itself at the same bound), and 20 s for each step: when no new
    # "selftest:" line reaches the log for 20 s, the walk is stuck and the app is stopped.
    $walkBound = [TimeSpan]::FromSeconds($walkSeconds)
    $stepBound = [TimeSpan]::FromSeconds(20)
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $lastStep = $clock.Elapsed
    $steps = 0
    while (-not $p.HasExited) {
        Start-Sleep -Milliseconds 200
        $text = Read-New
        $now = ([regex]::Matches($text, 'selftest: ')).Count
        if ($now -ne $steps) { $steps = $now; $lastStep = $clock.Elapsed }
        foreach ($m in [regex]::Matches($text, 'selftest: shot (\S+)')) {
            $name = $m.Groups[1].Value
            if (-not $taken.ContainsKey($name)) {
                $taken[$name] = Shot $p (Join-Path $Shots ($name + '.png'))
                "shot {0}: {1}" -f $name, $taken[$name]
                # the window's sheet as written by sheet_export, before the delete side changes it
                if ($name -eq '06-results-exported') {
                    Copy-Item -Recurse -Force (Join-Path $ws 'leadforge_data\exports') $snap
                    # the run's status as the window had it, before the delete side changes the counts (walk 2 compared after)
                    $status = Engine 'run_status' '{"runId":null}'
                    [IO.File]::WriteAllText((Join-Path $root 'window-status.json'), $status, (New-Object Text.UTF8Encoding $false))
                    "window run's status at 06, before the delete side (run_status): $status"
                }
                # the report first: the engine's own dry run of the forget the walk does next (the window has no report-first)
                if ($Campaign -and $name -eq '07-people') { "forget, report first (window person_forget dry_run): $(Engine 'person_forget' '{"value":"millbrook-autos.example","dry_run":true}')" }
                if ($Campaign -and $name -eq '08-data') { "purge report before the retention change: $(Engine 'purge_report' '{}')" }
            }
        }
        if ($clock.Elapsed -gt $walkBound) { $bounded = "the whole walk passed its $walkSeconds s bound"; break }
        if (($clock.Elapsed - $lastStep) -gt $stepBound) { $bounded = 'no step of the walk for 20 s'; break }
    }
    if ($bounded) { "SELFTEST BOUND: $bounded; stopping the app"; Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    if (-not $p.WaitForExit(10000)) { 'app did not exit by itself: stopping it'; Stop-Process -Id $p.Id -Force }
    "walk took {0:N0} s" -f $clock.Elapsed.TotalSeconds
    "app exit code: $($p.ExitCode)"
    $new = Read-New
    'core.log lines of this run:'; $new.TrimEnd()
    $clean = $new -match 'selftest: probe "\{\\"violations\\":\[\],\\"errors\\":\[\]\}"'
    $shots = @($taken.Values | Where-Object { $_ }).Count
    "shots taken: $shots of $expectShots; probe clean: $clean"
    "the app's workspace was the throwaway one: $($new.Length -gt 0 -and (Test-Path (Join-Path $ws 'leadforge.yaml')))"
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
    $null = Expect 'the real engine was started (origin dev-venv or bundled, never a stand-in)' 'started \(selftest=.*engine=(dev-venv|bundled)\)' -1
    if ($new -match 'dev-standin|standin') { $missed += 'SELFTEST EXPECTATION MISSED: no stand-in in this run (the log names one)' }
    # the incomplete form, refused by the real engine with kind input, and its words on screen
    # (the real engine's detail: "target.categories: at least one kind of business"; the form shows it on the field)
    $e = Expect 'the incomplete campaign is refused with kind input' 'cmd=campaign_create .* error kind=input' -1
    $null = Expect "the refusal is on screen in the engine's words (02: 'at least one kind of business')" 'selftest: shows 02-campaign-error: .*at least one kind of business' $e
    $c = Expect 'campaign_create answered ok' 'cmd=campaign_create .* ok out=' $e
    if ($Campaign) {
        $s = Expect 'run_start relayed its handle' 'cmd=run_start handle relayed' $c
        $null = Expect 'the run finished on screen (05: Open the results)' 'selftest: the run finishes: yes' $s
        $r = Expect 'run_start ended ok with its stream (lines=2 or more)' 'cmd=run_start .* ok out=\d+B lines=([2-9]|\d\d+) ' $s
        $x = Expect 'sheet_export answered ok (Write it again)' 'cmd=sheet_export .* ok out=' $r
        $f = Expect 'person_forget answered ok' 'cmd=person_forget .* ok out=' $x
        $u = Expect 'address_suppress answered ok' 'cmd=address_suppress .* ok out=' $f
        $t = Expect 'retention_set answered ok (1 month)' 'cmd=retention_set .* ok out=' $u
        $null = Expect 'purge_report asked again after the retention change' 'cmd=purge_report .* ok out=' $t
        foreach ($cmd in 'campaigns_list', 'people_list', 'settings_get', 'about') { $null = Expect "$cmd answered ok" "cmd=$cmd .* ok out=" $c }
    } else {
        foreach ($cmd in 'campaigns_list', 'people_list', 'purge_report', 'retention_get', 'settings_get', 'about') { $null = Expect "$cmd answered ok" "cmd=$cmd .* ok out=" $c }
    }
    # keys: the screen asked; ok, or the engine's own environment answer when it has no keyring package
    $null = Expect 'keys_list answered (ok, or kind environment: no keyring package)' 'cmd=keys_list .* (ok out=|error kind=environment)' $c
    if ($bounded) { $missed += "SELFTEST EXPECTATION MISSED: the walk ended within its bounds ($bounded)" }
    if ($Campaign) {
        # after the walk, from the engine's own command line in the same workspace
        $statusFile = Join-Path $root 'window-status.json'
        "window run's status after the delete side (run_status): $(Engine 'run_status' '{"runId":null}')"
        $people = Engine 'people_list' '{"query":{"search":"","limit":500}}'
        $forgotIn = ($people -match 'millbrook-autos\.example|Ysolde Fenwick')
        "forget: millbrook-autos.example or Ysolde Fenwick in people_list after the forget: $forgotIn"
        $inFiles = @(Get-ChildItem -Recurse -File (Join-Path $ws 'leadforge_data\exports') -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.csv', '.json' } | Select-String -SimpleMatch 'millbrook-autos.example' -List).Count
        $inSnap = @(Get-ChildItem -Recurse -File $snap -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.csv', '.json' } | Select-String -SimpleMatch 'millbrook-autos.example' -List).Count
        "forget: export files (csv, json) holding the domain: before the forget $inSnap, after $inFiles"
        if ($forgotIn -or $inFiles -gt 0 -or $inSnap -eq 0) { $missed += 'SELFTEST EXPECTATION MISSED: the forgotten domain is gone from People and from the exported files (and was in them before)' }
        $sup = ([regex]::Matches($people, '"domain":\s*"kestrel-garage\.example"[^}]*"suppressed":\s*true')).Count
        "suppress: people of kestrel-garage.example listed as suppressed: $sup"
        if ($sup -lt 1) { $missed += 'SELFTEST EXPECTATION MISSED: the suppressed domain is listed as suppressed in People' }
        "purge report now: $(Engine 'purge_report' '{}')"
        "keys_list from the command line: $(Engine 'keys_list' '{}')"
        $cli = Join-Path $root 'cli'
        & $py -X utf8 (Join-Path $here 'compare_campaign.py') --window-ws $ws --window-exports $snap --window-status $statusFile --cli $cli --python $py
        if ($LASTEXITCODE -ne 0) { $missed += 'SELFTEST EXPECTATION MISSED: the window campaign equals the command line campaign (compare_campaign.py)' }
    }
    foreach ($m in $missed) { $m }
    "expectations missed: $($missed.Count)"
    $ran = ($missed.Count -eq 0)
    $verdict = ($p.ExitCode -eq 0 -and $shots -eq $expectShots -and $clean -and $ran)
} finally {
    $env:USERPROFILE = $saved.USERPROFILE; $env:APPDATA = $saved.APPDATA; $env:LOCALAPPDATA = $saved.LOCALAPPDATA
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    if ($serve) { New-Item -ItemType File -Force $stopFlag | Out-Null; if (-not $serve.WaitForExit(15000)) { Stop-Process -Id $serve.Id -Force } }
    if ($Campaign) { & $py -X utf8 (Join-Path $here 'fake_world.py') loader off --venv $venv }
    Start-Sleep -Seconds 2
    $left = @(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and (($_.CommandLine -like '*D:\Temp\lf-selftest*') -or ($_.Name -eq 'leadforge-window.exe')) })
    "processes left: $($left.Count)"
    foreach ($l in $left) { Stop-Process -Id $l.ProcessId -Force -ErrorAction SilentlyContinue }
    try { Remove-Throwaway } catch { "could not remove ${root}: $_" }
    "throwaway folder left: $(Test-Path $root)"
}
if ($verdict) { 'SELFTEST PASS'; exit 0 } else { 'SELFTEST FAIL'; exit 1 }
