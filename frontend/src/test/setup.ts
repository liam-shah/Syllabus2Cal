// Runs before every test file (see `test.setupFiles` in vite.config.ts).

import '@testing-library/jest-dom/vitest' // adds matchers like toBeDisabled() and toHaveTextContent()
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup() // remove anything the test rendered, so tests can't affect each other
  vi.unstubAllGlobals() // undo mockFetch()
})
