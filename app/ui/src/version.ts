/**
 * The window's own version: a constant the build writes in (vite.config.ts `define`), read from
 * app/src-tauri/Cargo.toml, the file the window's crate version comes from. No Tauri call, no plugin,
 * no permission. Outside a build (Node tests, the dev server before a restart) it is "unknown".
 * tests/window-version.test.mjs fails when the constant and Cargo.toml differ.
 */
declare const __WINDOW_VERSION__: string | undefined;

export const WINDOW_VERSION: string = typeof __WINDOW_VERSION__ === "string" ? __WINDOW_VERSION__ : "unknown";
