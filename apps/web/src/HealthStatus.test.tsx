import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { HealthStatus } from './HealthStatus'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers() })

test('renders loading then healthy state', async () => {
  let resolveResponse: (value: Response) => void = () => undefined
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { resolveResponse = resolve })))

  render(<HealthStatus />)
  expect(screen.getByText('Checking backend health…')).toBeInTheDocument()

  resolveResponse(new Response(JSON.stringify({ status: 'ok', configuration_version: '1.0' }), { status: 200 }))
  expect(await screen.findByText('Backend connected and healthy')).toBeInTheDocument()
})

test('renders unavailable state when the request fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

  render(<HealthStatus />)
  expect(await screen.findByText('Backend unavailable')).toBeInTheDocument()
})

test.each(['degraded', 'unready'])('renders %s readiness and component reasons', async (readiness) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    status: 'ok', readiness,
    components: [{ component: 'database', status: 'unready', reason: 'failed' }],
  }))))
  render(<HealthStatus />)
  expect(await screen.findByText('database: unready (failed)')).toBeInTheDocument()
  expect(screen.getByText(readiness === 'degraded'
    ? 'Backend connected with reduced readiness' : 'Backend is not ready')).toBeInTheDocument()
})

test('rejects malformed readiness and component text', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    status: 'ok', readiness: 'healthy', components: [{ component: 'database', status: 'healthy', reason: 'secret' }],
  }))))
  render(<HealthStatus />)
  expect(await screen.findByText('Backend unavailable')).toBeInTheDocument()
  expect(screen.queryByText('secret')).not.toBeInTheDocument()
})

test('polls recovery and cancels polling on unmount', async () => {
  vi.useFakeTimers()
  const fetcher = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok', readiness: 'unready' })))
    .mockResolvedValue(new Response(JSON.stringify({ status: 'ok', readiness: 'healthy' })))
  vi.stubGlobal('fetch', fetcher)
  const view = render(<HealthStatus />)
  await act(async () => { await vi.advanceTimersByTimeAsync(0) })
  expect(screen.getByText('Backend is not ready')).toBeInTheDocument()
  await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
  expect(screen.getByText('Backend connected and healthy')).toBeInTheDocument()
  view.unmount()
  await vi.advanceTimersByTimeAsync(10000)
  expect(fetcher).toHaveBeenCalledTimes(2)
})

