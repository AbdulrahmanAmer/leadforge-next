import { defineConfig, type Plugin } from "vite";
import { windowVersion } from "./window-version.mjs";

/**
 * The policy the built window must run under, written into dist/index.html so every render of the
 * build is a render under it: nothing remote, no inline script or style, no eval. `connect-src` names
 * only Tauri's own bridge. The shell sets the same policy in its configuration; this copy cannot loosen it.
 */
export const CONTENT_SECURITY_POLICY =
  "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; " +
  "connect-src ipc: http://ipc.localhost; base-uri 'none'; form-action 'none'";

function contentSecurityPolicy(): Plugin {
  return {
    name: "leadforge-csp",
    apply: "build",
    transformIndexHtml(html) {
      return html.replace("<head>", `<head>\n    <meta http-equiv="Content-Security-Policy" content="${CONTENT_SECURITY_POLICY}" />`);
    },
  };
}

export default defineConfig({
  // relative asset addresses: the shell serves the folder from its own scheme
  base: "./",
  // the window's version, from app/src-tauri/Cargo.toml (window-version.mjs); src/version.ts reads it
  define: { __WINDOW_VERSION__: JSON.stringify(windowVersion()) },
  plugins: [contentSecurityPolicy()],
  server: { host: "127.0.0.1", port: 5183, strictPort: true },
  build: {
    target: "es2022",
    sourcemap: false,
    // no inlined data: addresses, no preload helper: everything is a plain local file
    assetsInlineLimit: 0,
    modulePreload: false,
  },
});
