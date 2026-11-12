// The About screen's window version is a build-time constant taken from app/src-tauri/Cargo.toml, the file the
// window's crate version comes from. These tests fail when the constant the build writes and that file differ.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import config from "../vite.config.ts";
import { CARGO_TOML, windowVersion } from "../window-version.mjs";

const ui = join(dirname(fileURLToPath(import.meta.url)), "..");

/** The crate's version read another way than the build reads it: the first `version = "` line after `[package]`. */
function crateVersion() {
  const text = readFileSync(CARGO_TOML, "utf8");
  const after = text.slice(text.indexOf("[package]") + "[package]".length);
  const section = after.slice(0, after.search(/^\[/m) === -1 ? undefined : after.search(/^\[/m));
  return /^version\s*=\s*"([^"]+)"/m.exec(section)[1];
}

test("the constant the build writes (vite define) equals the version in app/src-tauri/Cargo.toml", () => {
  assert.equal(CARGO_TOML, join(ui, "..", "src-tauri", "Cargo.toml"));
  assert.match(crateVersion(), /^\d+\.\d+\.\d+/);
  assert.equal(windowVersion(), crateVersion());
  assert.equal(config.define.__WINDOW_VERSION__, JSON.stringify(crateVersion()));
});

test("the version is read from the file it is given, [package] only", () => {
  const dir = mkdtempSync(join(ui, ".version-work-"));
  try {
    const toml = join(dir, "Cargo.toml");
    writeFileSync(toml, '[dependencies]\nfoo = { version = "1.0.0" }\nversion = "7.7.7"\n[package]\nname = "x"\nversion = "9.8.7"\n[profile.release]\nversion = "5.5.5"\n');
    assert.equal(windowVersion(toml), "9.8.7");
    writeFileSync(toml, '[package]\nname = "x"\n');
    assert.throws(() => windowVersion(toml), /no version/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("src/version.ts shows the constant when the build wrote one, and \"unknown\" otherwise", async () => {
  const url = pathToFileURL(join(ui, "src", "version.ts")).href;
  assert.equal((await import(`${url}?none`)).WINDOW_VERSION, "unknown");
  globalThis.__WINDOW_VERSION__ = "1.2.3";
  try {
    assert.equal((await import(`${url}?set`)).WINDOW_VERSION, "1.2.3");
  } finally {
    delete globalThis.__WINDOW_VERSION__;
  }
});

test("the About screen shows that constant, and nothing in the engine's About answer", () => {
  const screen = readFileSync(join(ui, "src", "screens", "Settings.tsx"), "utf8");
  assert.match(screen, /import \{ WINDOW_VERSION \} from "..\/version\.ts"/);
  assert.match(screen, /\["Window", WINDOW_VERSION\]/);
  assert.doesNotMatch(screen, /windowVersion/);
});

const dist = join(ui, "dist", "assets");
test("the built bundle holds the crate's version (needs a build: `npm run build`)", { skip: !existsSync(dist) && "no dist/ yet" }, () => {
  const js = readdirSync(dist).filter((f) => f.endsWith(".js")).map((f) => readFileSync(join(dist, f), "utf8")).join("\n");
  // the About row itself: ["Window", <the constant>] (the mock engine's own engineVersion is not this)
  const row = new RegExp(`\\[["\`']Window["\`'],["\`']${crateVersion().replaceAll(".", "\\.")}["\`']\\]`);
  assert.match(js, row, `the built About row does not read ["Window", "${crateVersion()}"]`);
});
