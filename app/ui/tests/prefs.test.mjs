// The window's own look (theme and accent): kept in browser storage by src/prefs.ts, never by the engine.
// The page must render with the defaults when storage throws, so every path that touches storage is tried with one that does.
import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_LOOK, LOOK_KEY, readLook, writeLook } from "../src/prefs.ts";

const memory = (initial = {}) => {
  const data = new Map(Object.entries(initial));
  return { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => { data.set(k, String(v)); }, data };
};
const throwing = () => { throw new DOMException("The operation is insecure.", "SecurityError"); };

test("the defaults are system and cobalt", () => {
  assert.deepEqual(DEFAULT_LOOK, { theme: "system", accent: "cobalt" });
  assert.deepEqual(readLook(() => memory()), DEFAULT_LOOK);
});

test("a saved look reads back", () => {
  const store = memory();
  assert.equal(writeLook({ theme: "dark", accent: "ember" }, () => store), true);
  assert.deepEqual(JSON.parse(store.data.get(LOOK_KEY)), { theme: "dark", accent: "ember" });
  assert.deepEqual(readLook(() => store), { theme: "dark", accent: "ember" });
});

test("storage that throws on first access: the defaults, no exception", () => {
  assert.deepEqual(readLook(throwing), DEFAULT_LOOK);
  assert.equal(writeLook({ theme: "dark", accent: "brass" }, throwing), false);
});

test("storage whose getItem or setItem throws: the defaults, no exception, false from the write", () => {
  const getFails = { getItem: throwing, setItem: () => {} };
  const setFails = { getItem: () => null, setItem: throwing };
  assert.deepEqual(readLook(() => getFails), DEFAULT_LOOK);
  assert.equal(writeLook({ theme: "light", accent: "celadon" }, () => setFails), false);
  assert.deepEqual(readLook(() => setFails), DEFAULT_LOOK);
});

test("damaged or foreign content falls back per field", () => {
  assert.deepEqual(readLook(() => memory({ [LOOK_KEY]: "{not json" })), DEFAULT_LOOK);
  assert.deepEqual(readLook(() => memory({ [LOOK_KEY]: "null" })), DEFAULT_LOOK);
  assert.deepEqual(readLook(() => memory({ [LOOK_KEY]: JSON.stringify({ theme: "purple", accent: "brass" }) })), { theme: "system", accent: "brass" });
  assert.deepEqual(readLook(() => memory({ [LOOK_KEY]: JSON.stringify({ theme: "light", accent: 7 }) })), { theme: "light", accent: "cobalt" });
});

test("a look that is not a Storage at all (undefined) is survived", () => {
  assert.deepEqual(readLook(() => undefined), DEFAULT_LOOK);
  assert.equal(writeLook(DEFAULT_LOOK, () => undefined), false);
});
