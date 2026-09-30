import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import Layout from './Layout'

vi.mock('../services/auth', () => ({
  useAuth: () => ({
    user: { name: 'Test User', role: 'ADMIN' },
    ready: true,
    logout: vi.fn(),
  }),
}))

test('links the authenticated brand to the public landing page', () => {
  render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Layout />
    </MemoryRouter>,
  )

  expect(screen.getByRole('link', { name: /PRAGATI Portfolio intelligence/i })).toHaveAttribute('href', '/')
})
