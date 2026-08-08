import { HealthStatus } from './HealthStatus'

export function App() {
  return (
    <main>
      <p className="eyebrow">Phase 1 foundation</p>
      <h1>Portable ATC Radar Trainer</h1>
      <p className="summary">
        Local, offline-first application foundation. Training and simulation features arrive in later packets.
      </p>
      <HealthStatus />
    </main>
  )
}

