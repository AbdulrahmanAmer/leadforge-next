// The window's one call: engine_version, no arguments. Reply: { version, origin, millis } or an error { kind, message }.
const out = document.getElementById('engine');
window.__TAURI__.core.invoke('engine_version')
  .then((v) => { out.textContent = `leadforge ${v.version} (${v.origin}, ${v.millis} ms)`; })
  .catch((e) => { out.textContent = `no answer: ${e.kind}: ${e.message}`; });
