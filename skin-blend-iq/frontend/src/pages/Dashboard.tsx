import { useEffect, useState } from 'react'
import { api } from '../api'

const LABELS: Record<string, string> = {
  clients: 'Clients',
  cases: 'Cases',
  formulas: 'Formulas',
  locked_formulas: 'Locked formulas',
  treatment_sessions: 'Treatment sessions',
  test_spots_pending: 'Test spots healing',
  blocked_lots: 'Blocked lots',
  active_lots: 'Active lots',
}

export default function Dashboard() {
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  useEffect(() => {
    api.get('/v1/dashboard').then(setStats)
  }, [])

  return (
    <div>
      <div className="banner">
        Skin Blend IQ is an <b>artist decision-support system</b>. Treatment-grade output requires
        calibrated capture, measured pigment data, whole-drop quantization, an external swatch, and
        your approval. Recalled, expired, and quarantined lots are blocked automatically.
      </div>
      <h2>Studio dashboard</h2>
      <div className="grid">
        {stats &&
          Object.entries(stats).map(([k, v]) => (
            <div className="stat" key={k}>
              <div className="n">{v}</div>
              <div className="l">{LABELS[k] ?? k}</div>
            </div>
          ))}
      </div>
      <div className="panel" style={{ marginTop: 18 }}>
        <h2>Workflow</h2>
        <p className="hint">
          Client → consent → calibrated capture (reference card, 3+ photos) → patch selection →
          analysis → formula generation → whole-drop quantization → <b>external swatch</b> →
          approve → lock → test spot → healed review → full session → follow-up.
        </p>
      </div>
    </div>
  )
}
