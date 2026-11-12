// blueprint v1.1.0
// One command checks LeadForge: `node check.mjs` (laptop) or `node check.mjs --ci` (CI).
// `--version X.Y.Z` hands a release number to the "versions agree" step.
// Plain commands without Node: `uv run ruff check src tests`, `uv run pytest`.

const STEPS = [
  { name: 'versions agree', cmd: 'python .github/scripts/check_versions.py' },
  { name: 'skill frontmatter', cmd: 'python .github/scripts/check_skill_frontmatter.py' },
  { name: 'skill references', cmd: 'python .github/scripts/check_skill_references.py' },
  { name: 'lint', cmd: 'python -m ruff check src tests' },
  { name: 'tests', cmd: 'python -m pytest' },
  { name: 'cli digest', cmd: 'python .github/scripts/check_digest.py' },
];

// ---- fixed runner (Node built-ins only) ----
import { spawnSync, execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, delimiter } from 'node:path';

const args = process.argv.slice(2);
const ci = args.includes('--ci');
const vi = args.indexOf('--version');
const env = { ...process.env };
if (vi >= 0 && args[vi + 1]) env.LF_RELEASE_VERSION = args[vi + 1];

// Prefer the project venv (made by `uv sync`) so `python` means the locked environment.
for (const bin of ['.venv/Scripts', '.venv/bin']) {
  if (existsSync(bin)) {
    const key = Object.keys(env).find((k) => k.toUpperCase() === 'PATH') || 'PATH';
    env[key] = join(process.cwd(), bin) + delimiter + env[key];
    break;
  }
}

const git = (c) => {
  try { return execSync(`git ${c}`, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); } catch { return ''; }
};

const t0 = Date.now();
let ran = 0, skipped = 0, failed = false;
for (const s of STEPS) {
  const skip = (s.os && s.os !== process.platform) || (s.ci && !ci);
  if (skip) { skipped++; console.log(`skip  ${s.name}  0`); continue; }
  const t = Date.now();
  const r = spawnSync(s.cmd, { shell: true, stdio: 'inherit', env });
  ran++;
  const secs = ((Date.now() - t) / 1000).toFixed(1);
  if (r.status !== 0) { console.log(`FAIL  ${s.name}  ${secs}`); failed = true; break; }
  console.log(`ok  ${s.name}  ${secs}`);
}
const sha = git('rev-parse --short HEAD') || 'none';
const tree = git('status --porcelain') ? 'dirty' : 'clean';
const secs = ((Date.now() - t0) / 1000).toFixed(0);
console.log(`CHECK ${failed ? 'FAIL' : 'PASS'} sha=${sha} tree=${tree} steps=${ran} skipped=${skipped} secs=${secs}`);
process.exit(failed ? 1 : 0);
