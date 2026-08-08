import { useEffect, useState } from 'react'

type HealthState = 'loading' | 'healthy' | 'unavailable'
type HealthResponse = { status: 'ok' }

const apiUrl = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export function HealthStatus() {
  const [state, setState] = useState<HealthState>('loading')

  useEffect(() => {
    const controller = new AbortController()

    async function loadHealth() {
      try {
        const response = await fetch(`${apiUrl}/health`, { signal: controller.signal })
        if (!response.ok) throw new Error('API health request failed')
        const health = (await response.json()) as HealthResponse
        setState(health.status === 'ok' ? 'healthy' : 'unavailable')
      } catch (error) {
        if ((error as Error).name !== 'AbortError') setState('unavailable')
      }
    }

    void loadHealth()
    return () => controller.abort()
  }, [])

  const label = {
    loading: 'Checking backend health…',
    healthy: 'Backend connected and healthy',
    unavailable: 'Backend unavailable',
  }[state]

  return (
    <section className={`health health--${state}`} aria-live="polite">
      <span className="health__indicator" aria-hidden="true" />
      <div>
        <strong>System status</strong>
        <p>{label}</p>
      </div>
    </section>
  )
}

