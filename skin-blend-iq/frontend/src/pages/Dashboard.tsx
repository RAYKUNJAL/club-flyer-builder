import { useEffect, useState } from 'react'
import { api } from '../api'
import type { PageId } from '../App'

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

export default function Dashboard({
  mode,
  setMode,
  go,
}: {
  mode: 'simple' | 'advanced'
  setMode: (m: 'simple' | 'advanced') => void
  go: (p: PageId) => void
}) {
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  useEffect(() => {
    api.get('/v1/dashboard').then(setStats)
  }, [])

  return mode === 'simple' ? (
    <SimpleDashboard stats={stats} go={go} onAdvanced={() => setMode('advanced')} />
  ) : (
    <AdvancedDashboard stats={stats} onSimple={() => setMode('simple')} />
  )
}

function SimpleDashboard({
  stats,
  go,
  onAdvanced,
}: {
  stats: Record<string, number> | null
  go: (p: PageId) => void
  onAdvanced: () => void
}) {
  const alerts: { text: string; page: PageId }[] = []
  if (stats?.blocked_lots)
    alerts.push({
      text: `${stats.blocked_lots} pigment lot${stats.blocked_lots > 1 ? 's are' : ' is'} blocked (recalled, expired, or quarantined) and cannot be used.`,
      page: 'pigments',
    })
  if (stats?.test_spots_pending)
    alerts.push({
      text: `${stats.test_spots_pending} test spot${stats.test_spots_pending > 1 ? 's are' : ' is'} healing and waiting for review.`,
      page: 'clients',
    })

  const steps: { n: number; title: string; desc: string; action: string; page: PageId }[] = [
    {
      n: 1,
      title: 'Add a client',
      desc: 'Create the client record, record their consents, and open a case for the area being treated.',
      action: 'Open Clients',
      page: 'clients',
    },
    {
      n: 2,
      title: 'Capture their skin tone',
      desc: 'Photograph untreated skin next to the reference card (3+ photos), mark the card and skin, and analyze.',
      action: 'Start a Capture',
      page: 'capture',
    },
    {
      n: 3,
      title: 'Build the drop formula',
      desc: 'Generate a whole-drop recipe from your pigment kit, verify it on an external swatch, then approve and lock it.',
      action: 'Open Formula Lab',
      page: 'formula',
    },
  ]

  return (
    <div>
      <h2>Welcome to Skin Blend IQ</h2>
      <p className="hint" style={{ maxWidth: 640, marginTop: -4 }}>
        This tool helps you measure a client's skin tone and mix a matching pigment formula. It
        supports your judgment — it never diagnoses, and every formula needs your swatch test and
        approval before use.
      </p>

      {alerts.map((a, i) => (
        <div className="banner danger" key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ flex: 1 }}>{a.text}</span>
          <button className="btn small" onClick={() => go(a.page)}>Review</button>
        </div>
      ))}

      <div className="steps">
        {steps.map((s) => (
          <div className="panel step-card" key={s.n}>
            <div className="step-n">{s.n}</div>
            <h3 style={{ margin: '6px 0' }}>{s.title}</h3>
            <p className="hint" style={{ minHeight: 54 }}>{s.desc}</p>
            <button className="btn" onClick={() => go(s.page)}>{s.action}</button>
          </div>
        ))}
      </div>

      <p className="hint" style={{ marginTop: 18 }}>
        Want studio numbers, inventory, and the full workflow?{' '}
        <a href="#" onClick={(e) => { e.preventDefault(); onAdvanced() }}>
          Switch to the advanced view
        </a>
        .
      </p>
    </div>
  )
}

function AdvancedDashboard({
  stats,
  onSimple,
}: {
  stats: Record<string, number> | null
  onSimple: () => void
}) {
  return (
    <div>
      <div className="banner">
        Skin Blend IQ is an <b>artist decision-support system</b>. Treatment-grade output requires
        calibrated capture, measured pigment data, whole-drop quantization, an external swatch, and
        your approval. Recalled, expired, and quarantined lots are blocked automatically.
      </div>
      <h2 style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        Studio dashboard
        <a href="#" className="hint" style={{ fontWeight: 400 }} onClick={(e) => { e.preventDefault(); onSimple() }}>
          switch to simple view
        </a>
      </h2>
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
