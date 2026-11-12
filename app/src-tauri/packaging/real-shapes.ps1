# The REAL engine's 21 window commands through the core's own code path, against the repository's loopback fakes, and their
# answers held to the screens' types. Windows PowerShell 5.1. Run it under the heavy-job lock (it builds and runs a cargo test).
#   real-shapes.ps1 -Report <file for answers.json>
# Makes and deletes ONE throwaway folder, D:\Temp\lf-real-shapes (refused if it resolves elsewhere or is a link); starts and
# stops the fake world; puts the harness loader into the dev venv and takes it out again (packaging/fake_world.py).
param([Parameter(Mandatory = $true)][string]$Report)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
$here = $PSScriptRoot
$crate = Split-Path $here -Parent
$repo = Split-Path (Split-Path $crate -Parent) -Parent
$venv = Join-Path $repo '.venv'
$py = Join-Path $venv 'Scripts\python.exe'
$root = 'D:\Temp\lf-real-shapes'
function Assert-Throwaway([string]$p) {
    $full = [IO.Path]::GetFullPath($p)
    if ($full -ne $root) { throw "refused: $p resolves to $full, not $root" }
    if (Test-Path $full) {
        $item = Get-Item -LiteralPath $full -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "refused: $full is a link" }
    }
    return $full
}
function Remove-Throwaway {
    $full = Assert-Throwaway $root
    if (Test-Path $full) {
        # never follow a link inside: delete reparse points as entries, then the rest
        Get-ChildItem -LiteralPath $full -Recurse -Force -Attributes ReparsePoint -ErrorAction SilentlyContinue | ForEach-Object { [IO.Directory]::Delete($_.FullName) }
        Remove-Item -LiteralPath $full -Recurse -Force
    }
}
Remove-Throwaway
$ws = Join-Path $root 'ws'; $out = Join-Path $root 'out'; $stop = Join-Path $root 'stop.flag'
New-Item -ItemType Directory -Force $ws, $out | Out-Null
$serve = $null
$code = 1
# native programs write progress to stderr: under 'Stop' PowerShell 5.1 would end the script at their first line
$ErrorActionPreference = 'Continue'
try {
    & $py -X utf8 (Join-Path $here 'fake_world.py') prepare --ws $ws --out $out
    & $py -X utf8 (Join-Path $here 'fake_world.py') loader on --venv $venv
    $serve = Start-Process -FilePath $py -ArgumentList @('-X', 'utf8', (Join-Path $here 'fake_world.py'), 'serve', '--out', $out, '--stop', $stop, '--bound', '1200') -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    $env:LF_REAL_WS = $ws; $env:LF_REAL_OUT = $out
    Push-Location $crate
    cargo test --locked --test real_engine_shapes -- --ignored --nocapture 2>&1 | ForEach-Object { "$_" }
    $cargo = $LASTEXITCODE
    Pop-Location
    "cargo test exit: $cargo"
    $answers = Join-Path $out 'answers.json'
    if (Test-Path $answers) { Copy-Item $answers $Report -Force }
    Push-Location (Join-Path $repo 'app\ui')
    $env:LF_REAL_ANSWERS = $out
    node --test tests/seam-shape.test.mjs 2>&1 | ForEach-Object { "$_" }
    $node = $LASTEXITCODE
    Pop-Location
    "shape check exit: $node"
    $refused = Join-Path $out 'guard.log'
    $n = 0; if (Test-Path $refused) { $n = @(Get-Content $refused).Count }
    "guard: outside attempts refused and logged: $n"
    if ($cargo -eq 0 -and $node -eq 0) { $code = 0 }
} finally {
    Remove-Item Env:LF_REAL_WS, Env:LF_REAL_OUT, Env:LF_REAL_ANSWERS -ErrorAction SilentlyContinue
    New-Item -ItemType File -Force $stop | Out-Null
    if ($serve) { if (-not $serve.WaitForExit(15000)) { Stop-Process -Id $serve.Id -Force } }
    & $py -X utf8 (Join-Path $here 'fake_world.py') loader off --venv $venv
    Remove-Throwaway
    "throwaway folder left: $(Test-Path $root)"
}
if ($code -eq 0) { 'REAL SHAPES PASS' } else { 'REAL SHAPES FAIL' }
exit $code
