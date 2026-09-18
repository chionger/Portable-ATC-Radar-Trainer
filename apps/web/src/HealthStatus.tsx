import { useEffect, useState } from 'react'

type Readiness = 'healthy' | 'degraded' | 'unready'
type HealthState = 'loading' | Readiness | 'unavailable'
type Component = { component: string; status: Readiness; reason: string }
const statuses = ['healthy', 'degraded', 'unready']
const reasons: Record<string, string> = {
  operational: 'operational', starting: 'starting', failed: 'failed',
  timeout: 'status expired', not_configured: 'not configured',
}
const apiUrl = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export function HealthStatus() {
  const [state, setState] = useState<HealthState>('loading')
  const [components, setComponents] = useState<Component[]>([])

  useEffect(() => {
    let stopped = false
    let next: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | undefined
    async function loadHealth() {
      controller = new AbortController()
      const deadline = setTimeout(() => controller?.abort(), 3000)
      try {
        const response = await fetch(`${apiUrl}/health`, { signal: controller.signal })
        if (!response.ok) throw new Error('Health unavailable')
        const health = await response.json() as Record<string, unknown>
        const readiness = health.readiness ?? 'healthy'
        const values = health.components ?? []
        if (health.status !== 'ok' || !statuses.includes(readiness as string) || !Array.isArray(values)
          || !values.every((item: Component) => item && typeof item.component === 'string'
            && /^[a-z][a-z0-9_]{0,47}$/.test(item.component) && statuses.includes(item.status)
            && Object.hasOwn(reasons, item.reason))) throw new Error('Invalid health response')
        if (!stopped) {
          setState(readiness as Readiness)
          setComponents(values as Component[])
        }
      } catch {
        if (!stopped) {
          setState('unavailable')
          setComponents([])
        }
      } finally {
        clearTimeout(deadline)
        if (!stopped) next = setTimeout(() => { void loadHealth() }, 5000)
      }
    }
    void loadHealth()
    return () => {
      stopped = true
      clearTimeout(next)
      controller?.abort()
    }
  }, [])

  const label = {
    loading: 'Checking backend health…', healthy: 'Backend connected and healthy',
    degraded: 'Backend connected with reduced readiness', unready: 'Backend is not ready',
    unavailable: 'Backend unavailable',
  }[state]
  return (
    <section className={`health health--${state}`} aria-live="polite">
      <span className="health__indicator" aria-hidden="true" />
      <div>
        <strong>System status</strong>
        <p>{label}</p>
        {components.length > 0 && <ul aria-label="Component status">
          {components.map((item) => <li key={item.component}>
            {item.component.replaceAll('_', ' ')}: {item.status} ({reasons[item.reason]})
          </li>)}
        </ul>}
      </div>
    </section>
  )
}
