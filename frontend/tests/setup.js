// Vitest global setup — runs once per test file before any test code.
//
// Wires in @testing-library/jest-dom matchers (toBeInTheDocument,
// toHaveTextContent, etc.) so tests can assert against the rendered DOM
// directly. Also stubs a few browser globals that components touch on
// import — Clerk's hooks are mocked per-test where they're needed, but
// crypto.randomUUID is used by some helpers and isn't always present
// in happy-dom < 20.

import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// React Testing Library mounts each test into the same document root by
// default; without explicit cleanup, components from one test leak into
// the next. cleanup() unmounts everything between tests.
afterEach(() => {
  cleanup()
})
