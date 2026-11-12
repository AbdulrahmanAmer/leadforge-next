// The window's version for the build: the `[package]` version of app/src-tauri/Cargo.toml, the one file the
// window's crate version comes from (tests/version_agrees.rs in the shell ties it to pyproject.toml).
// vite.config.ts writes it into the build as `__WINDOW_VERSION__`; src/version.ts reads that constant.
// Plain .mjs on purpose: it needs node:fs, and the screens' TypeScript has no Node types (no new package).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const CARGO_TOML = fileURLToPath(new URL("../src-tauri/Cargo.toml", import.meta.url));

/** The version in [package] of `cargoToml`. Throws when there is none: a build with no version stops. */
export function windowVersion(cargoToml = CARGO_TOML) {
  let inPackage = false;
  for (const raw of readFileSync(cargoToml, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (line.startsWith("[")) inPackage = line === "[package]";
    else if (inPackage) {
      const m = /^version\s*=\s*"([^"]+)"/.exec(line);
      if (m) return m[1];
    }
  }
  throw new Error(`no version in [package] of ${cargoToml}`);
}
