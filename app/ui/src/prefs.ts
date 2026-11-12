/**
 * The window's own look: theme and accent. The engine does not know them (they are not in `Settings`, and
 * `settings_get` / `settings_set` never carry them); the Rust core merges nothing. They live in the page's
 * browser storage, under one key.
 *
 * This is the only file that touches browser storage. Every read and every write is inside try/catch: storage
 * can be off, full, or throw a SecurityError on first access, and the page must still render, with the
 * defaults. `store` is a parameter so a test can hand in a storage that throws.
 */

export type ThemeSetting = "light" | "dark" | "system";
export type AccentSetting = "cobalt" | "brass" | "celadon" | "ember";

export const THEMES: readonly ThemeSetting[] = ["light", "dark", "system"];
export const ACCENT_IDS: readonly AccentSetting[] = ["cobalt", "brass", "celadon", "ember"];

export interface Look {
  theme: ThemeSetting;
  accent: AccentSetting;
}

export const DEFAULT_LOOK: Look = { theme: "system", accent: "cobalt" };
export const LOOK_KEY = "leadforge.look";

type Store = Pick<Storage, "getItem" | "setItem">;

/** The browser's storage, looked up inside the caller's try: even naming `localStorage` can throw. */
function browserStore(): Store {
  return globalThis.localStorage;
}

/** The saved look; the default for anything missing, damaged or unreadable. Never throws. */
export function readLook(store: () => Store = browserStore): Look {
  try {
    const raw = store().getItem(LOOK_KEY);
    if (!raw) return { ...DEFAULT_LOOK };
    const saved = JSON.parse(raw) as Record<string, unknown> | null;
    const theme = THEMES.find((t) => t === saved?.theme) ?? DEFAULT_LOOK.theme;
    const accent = ACCENT_IDS.find((a) => a === saved?.accent) ?? DEFAULT_LOOK.accent;
    return { theme, accent };
  } catch {
    return { ...DEFAULT_LOOK };
  }
}

/** Saves the look. Returns false when the browser would not keep it; the look still applies for this session. */
export function writeLook(look: Look, store: () => Store = browserStore): boolean {
  try {
    store().setItem(LOOK_KEY, JSON.stringify({ theme: look.theme, accent: look.accent }));
    return true;
  } catch {
    return false;
  }
}
