// The store touches localStorage at MODULE LOAD (persist middleware,
// auth token) — before any test hook runs. Stub it at setup-file scope;
// setupFiles execute before test files are imported.
const stub: Storage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
  clear: () => {},
  key: () => null,
  length: 0,
} as unknown as Storage;

(globalThis as any).localStorage = stub;
