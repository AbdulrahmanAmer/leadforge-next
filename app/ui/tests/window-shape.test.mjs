// The shape the shell requires of the window, as tests that read the source:
//   - the Tauri commands are exactly the ones docs/window-actions.md lists, and none of them sends anything (C14)
//   - no remote resource, no inline style or script, no eval, no link that opens a browser, no file or network access
//   - screens talk to the engine through the interface only
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { ACTIONS } from "../src/engine.ts";
import { COMMANDS } from "../src/engine.tauri.ts";

const ui = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => readFileSync(join(ui, ...parts), "utf8");

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? files(join(dir, entry.name)) : [join(dir, entry.name)]);
}
const sources = files(join(ui, "src")).map((path) => ({ name: relative(ui, path).replaceAll("\\", "/"), text: readFileSync(path, "utf8") }));
const page = read("..", "..", "docs", "window-actions.md");

test("every action has one Tauri command, and no two actions share one", () => {
  assert.deepEqual(Object.keys(COMMANDS).sort(), [...ACTIONS].sort());
  assert.equal(new Set(Object.values(COMMANDS)).size, ACTIONS.length);
});

test("docs/window-actions.md lists every Tauri command, and only those", () => {
  const table = page.slice(page.indexOf("## Tauri commands"), page.indexOf("## Missing in the engine"));
  const listed = [...table.matchAll(/^\| `([a-z_]+)` \|/gm)].map((m) => m[1]);
  assert.deepEqual(listed.sort(), Object.values(COMMANDS).sort());
});

test("no command and no action sends anything (C14)", () => {
  for (const name of [...Object.values(COMMANDS), ...ACTIONS]) {
    assert.doesNotMatch(name, /send|outreach|mail|smtp|deliver/i, name);
  }
});

test("no screen offers to send: no send or outreach wording on a control", () => {
  for (const { name, text } of sources.filter((s) => s.name.startsWith("src/screens/") || s.name === "src/App.tsx")) {
    assert.doesNotMatch(text, />\s*(Send|Email them|Start outreach|Contact them)\b/, name);
  }
});

test("nothing remote: no web address in the source, the styles or the page", () => {
  const where = [...sources, { name: "index.html", text: read("index.html") }, { name: "public/leadforge-mark.svg", text: read("public", "leadforge-mark.svg") }];
  for (const { name, text } of where) {
    // an SVG namespace is a name, not a request; the content security policy names Tauri's own bridge
    const cleaned = text.replaceAll("http://www.w3.org/2000/svg", "").replaceAll("http://ipc.localhost", "");
    assert.doesNotMatch(cleaned, /https?:\/\/|url\(\s*["']?(?!#)|@import|@font-face/, name);
  }
});

test("nothing that needs a relaxed policy: no style attribute, no inline script, no eval", () => {
  for (const { name, text } of sources.filter((s) => /\.tsx?$/.test(s.name))) {
    assert.doesNotMatch(text, /\bstyle=|dangerouslySetInnerHTML|\.innerHTML|\beval\(|new Function\(|\.setAttribute\(\s*["']style/, name);
  }
  const html = read("index.html");
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>|<style|\son[a-z]+=|\sstyle=/i, "index.html");
});

test("no link that opens a browser, and no file or network access from the window", () => {
  for (const { name, text } of sources.filter((s) => /\.tsx?$/.test(s.name))) {
    assert.doesNotMatch(text, /<a\s|window\.open|location\.href\s*=|target="_blank"/, name);
    assert.doesNotMatch(text, /\bfetch\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|indexedDB|showOpenFilePicker|type="file"/, name);
  }
});

test("browser storage is touched in one file only (src/prefs.ts: the window's look), and only inside try/catch", () => {
  for (const { name, text } of sources.filter((s) => /\.tsx?$/.test(s.name))) {
    if (name === "src/prefs.ts") continue;
    assert.doesNotMatch(text, /localStorage|sessionStorage/, name);
  }
  const prefs = sources.find((s) => s.name === "src/prefs.ts").text;
  assert.doesNotMatch(prefs, /sessionStorage|indexedDB|document\.cookie/);
  // every call into the store sits in a try block: `store()` appears only after a `try {` in its own function
  for (const fn of ["readLook", "writeLook"]) {
    const body = prefs.slice(prefs.indexOf(`export function ${fn}(`));
    const end = body.indexOf("\n}\n");
    const text = body.slice(0, end);
    assert.match(text, /try \{[\s\S]*store\(\)[\s\S]*\} catch/, fn);
  }
  // the browser's own object is named only inside the one helper that callers wrap in their try
  const named = [...prefs.matchAll(/globalThis\.localStorage/g)].length;
  assert.equal(named, 1);
});

test("the settings the engine returns carry no theme and no accent, and the About no window version", () => {
  const engine = read("src", "engine.ts");
  const settings = engine.slice(engine.indexOf("export interface Settings {"), engine.indexOf("export type SettingsPatch"));
  assert.doesNotMatch(settings, /\btheme\b|\baccent\b/);
  assert.match(settings, /sources: SourceId\[\]/);
  assert.doesNotMatch(engine.slice(engine.indexOf("export type SettingsPatch")), /^export type SettingsPatch[^\n]*(theme|accent)/);
  const about = engine.slice(engine.indexOf("export interface About {"), engine.indexOf("/* ----------------------------------------------------------------- the seam */"));
  assert.doesNotMatch(about, /windowVersion/);
});

test("only the Tauri engine imports Tauri, and it imports nothing but invoke and Channel", () => {
  for (const { name, text } of sources) {
    if (name === "src/engine.tauri.ts") {
      const imports = [...text.matchAll(/from "(@tauri-apps\/[^"]+)"/g)].map((m) => m[1]);
      assert.deepEqual(imports, ["@tauri-apps/api/core"]);
    } else {
      assert.doesNotMatch(text, /@tauri-apps|__TAURI__\b/, name);
    }
  }
});

test("screens and components talk to the interface: none imports an engine implementation", () => {
  for (const { name, text } of sources.filter((s) => s.name.startsWith("src/screens/") || s.name.startsWith("src/components/") || s.name === "src/App.tsx")) {
    assert.doesNotMatch(text, /engine\.(mock|tauri)/, name);
  }
});

test("the build's policy allows nothing remote and nothing inline", () => {
  const config = read("vite.config.ts");
  const policy = config.slice(config.indexOf("CONTENT_SECURITY_POLICY ="), config.indexOf("function contentSecurityPolicy"));
  assert.match(policy, /default-src 'none'/);
  assert.match(policy, /script-src 'self';/);
  assert.match(policy, /style-src 'self';/);
  assert.doesNotMatch(policy, /unsafe-inline|unsafe-eval|https?:\/\/(?!ipc\.localhost)|\*|data:|blob:/);
});
