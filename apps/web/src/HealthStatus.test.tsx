import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { HealthStatus } from './HealthStatus'

afterEach(() => vi.unstubAllGlobals())

test('renders loading then healthy state', async () => {
  let resolveResponse: (value: Response) => void = () => undefined
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { resolveResponse = resolve })))

  render(<HealthStatus />)
  expect(screen.getByText('Checking backend health…')).toBeInTheDocument()

  resolveResponse(new Response(JSON.stringify({ status: 'ok' }), { status: 200 }))
  expect(await screen.findByText('Backend connected and healthy')).toBeInTheDocument()
})

test('renders unavailable state when the request fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

  render(<HealthStatus />)
  expect(await screen.findByText('Backend unavailable')).toBeInTheDocument()
})

