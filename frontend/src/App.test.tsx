import '@testing-library/jest-dom/vitest'

import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import App from './App.tsx'

test('shows the Phase 0 product boundary', () => {
  render(<App />)

  expect(screen.getByRole('heading', { name: 'SOLoRa' })).toBeInTheDocument()
  expect(screen.getByText(/not implemented yet/i)).toBeInTheDocument()
})
