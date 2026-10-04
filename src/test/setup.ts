import "@testing-library/jest-dom";
import { JSDOM } from "jsdom";

// Recent Node versions expose an unavailable file-backed localStorage global.
// Bind tests to browser Storage semantics instead, without a shared disk file.
const storageWindow = new JSDOM('', { url: 'https://buildsignals.test' }).window;
Object.defineProperty(window, 'localStorage', { configurable: true, value: storageWindow.localStorage });
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storageWindow.localStorage });

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});
