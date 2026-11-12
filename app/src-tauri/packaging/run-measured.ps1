# Runs one build command and records its duration and the peak memory of its whole process tree (sum of working sets,
# sampled every second). Windows PowerShell 5.1. Run it through the heavy lock.
# Usage: run-measured.ps1 -Log <file> -Exe <program> -ArgLine "<arguments>" [-Cwd <folder>]
param(
    [Parameter(Mandatory = $true)][string]$Log,
    [Parameter(Mandatory = $true)][string]$Exe,
    [string]$ArgLine = '',
    [string]$Cwd = (Get-Location).Path
)
$ErrorActionPreference = 'Stop'
. D:\rust\env.ps1
$env:CARGO_TARGET_DIR = 'D:\LeadForge\wt\target'
$env:CARGO_BUILD_JOBS = '2'
$env:CARGO_TERM_COLOR = 'never'
$freeBefore = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024)
$psi = New-Object Diagnostics.ProcessStartInfo
$psi.FileName = $env:ComSpec
$psi.Arguments = "/d /s /c `"`"$Exe`" $ArgLine > `"$Log`" 2>&1`""
$psi.WorkingDirectory = $Cwd
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = [Diagnostics.Process]::Start($psi)
$peak = 0
while (-not $p.HasExited) {
    $all = Get-CimInstance Win32_Process -Property ProcessId, ParentProcessId, WorkingSetSize
    $kids = @{}
    foreach ($x in $all) { if (-not $kids.ContainsKey($x.ParentProcessId)) { $kids[$x.ParentProcessId] = @() }; $kids[$x.ParentProcessId] += $x }
    $sum = 0; $stack = New-Object Collections.Stack; $stack.Push([uint32]$p.Id); $seen = @{}
    while ($stack.Count -gt 0) {
        $id = $stack.Pop()
        if ($seen.ContainsKey($id)) { continue }; $seen[$id] = $true
        foreach ($c in @($kids[$id])) { if ($c) { $sum += $c.WorkingSetSize; $stack.Push([uint32]$c.ProcessId) } }
    }
    if ($sum -gt $peak) { $peak = $sum }
    Start-Sleep -Milliseconds 1000
}
$p.WaitForExit()
$sw.Stop()
"exit {0}; duration {1:N0} s; peak working set of the build's process tree {2:N0} MB; free RAM before {3} MB" -f `
    $p.ExitCode, $sw.Elapsed.TotalSeconds, ($peak / 1MB), $freeBefore
exit $p.ExitCode
