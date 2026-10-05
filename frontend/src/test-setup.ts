/**
 * Global test setup.
 *
 * jsdom provides no localStorage, and ThemeService reads it in its constructor.
 * A minimal in-memory implementation keeps the theme tests meaningful instead of
 * skipping every assertion that touches storage.
 */
const store = new Map<string, string>();

const storage: Storage = {
  get length() {
    return store.size;
  },
  clear: () => store.clear(),
  getItem: (key: string) => store.get(key) ?? null,
  key: (index: number) => [...store.keys()][index] ?? null,
  removeItem: (key: string) => void store.delete(key),
  setItem: (key: string, value: string) => void store.set(key, value),
};

Object.defineProperty(globalThis, 'localStorage', {
  value: storage,
  configurable: true,
  writable: true,
});
