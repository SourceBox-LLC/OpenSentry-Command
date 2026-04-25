// Smoke test #1 — proves the test runner is wired up at all.
//
// If this file ever stops passing the rest of the suite is meaningless,
// so it has its own slot at the front of the sort order.

import { describe, it, expect } from 'vitest'

describe('vitest sanity', () => {
  it('runs', () => {
    expect(1 + 1).toBe(2)
  })

  it('has happy-dom DOM globals available', () => {
    // Confirms test.environment === 'happy-dom' from vite.config.js
    // actually wired in. If a future config change drops this, every
    // component test breaks before it runs — easier to catch here.
    expect(typeof document).toBe('object')
    expect(typeof window).toBe('object')
  })

  it('has @testing-library/jest-dom matchers loaded', () => {
    // Indirect probe — these matchers are added via setup.js. If the
    // setup file fails to load, expect.extend never ran and this assertion
    // surfaces it immediately rather than from a confusing per-test failure.
    const div = document.createElement('div')
    div.textContent = 'hello'
    document.body.appendChild(div)
    expect(div).toBeInTheDocument()
    document.body.removeChild(div)
  })
})
