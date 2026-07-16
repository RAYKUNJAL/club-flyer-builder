import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

// Chart color roles (validated: poles pass CVD/contrast checks on light surface).
const POLE_IN = '#2a78d6' // net inflow (received)
const POLE_OUT = '#e34948' // net outflow (used/discarded)
const NEUTRAL = '#f0efec' // diverging midpoint: balanced / no net flow
const BAR = '#8a5a3b' // single-series funnel bars (app accent)

type Cell = { in_ml: number; out_ml: number; net_ml: number }
type Row = { code: string; product: string; cells: Cell[]; total_in_ml: number; total_out_ml: number }
type Flow = {
  pipeline: { stage: string; label: string; count: number }[]
  inventory_footprint: { weeks: string[]; rows: Row[] }
}

const fmt = (v: number) => {
  const r = Math.round(v * 10) / 10
  return Number.isInteger(r) ? String(r) : r.toFixed(1)
}

function mix(hex: string, alpha: number): string {
  // Blend a pole color over the white panel at the given strength.
  const n = parseInt(hex.slice(1), 16)
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  const f = (c: number) => Math.round(255 + (c - 255) * alpha)
  return `rgb(${f(r)}, ${f(g)}, ${f(b)})`
}

export default function FlowCharts() {
  const [flow, setFlow] = useState<Flow | null>(null)
  const [tip, setTip] = useState<{ x: number; y: number; lines: string[] } | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.get('/v1/dashboard/flow').then(setFlow)
  }, [])

  if (!flow) return null

  const showTip = (e: React.MouseEvent, lines: string[]) => {
    const r = wrapRef.current!.getBoundingClientRect()
    setTip({ x: e.clientX - r.left + 14, y: e.clientY - r.top + 14, lines })
  }

  const maxCount = Math.max(1, ...flow.pipeline.map((p) => p.count))
  const fp = flow.inventory_footprint
  const maxNet = Math.max(0.001, ...fp.rows.flatMap((r) => r.cells.map((c) => Math.abs(c.net_ml))))

  const cellStyle = (c: Cell): React.CSSProperties => {
    if (c.in_ml === 0 && c.out_ml === 0) return { background: 'transparent' }
    if (c.net_ml === 0) return { background: NEUTRAL }
    const strength = 0.12 + 0.43 * (Math.abs(c.net_ml) / maxNet) // cap keeps ink readable
    return { background: mix(c.net_ml > 0 ? POLE_IN : POLE_OUT, strength) }
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative' }} onMouseLeave={() => setTip(null)}>
      <div className="panel">
        <h2>Client order flow</h2>
        <p className="hint" style={{ marginTop: -6 }}>
          Live counts from your records at each stage of the workflow.
        </p>
        <div className="funnel">
          {flow.pipeline.map((p) => (
            <div
              className="funnel-row"
              key={p.stage}
              onMouseMove={(e) => showTip(e, [p.label, `${p.count} total`])}
              onMouseLeave={() => setTip(null)}
            >
              <span className="funnel-label">{p.label}</span>
              <span className="funnel-track">
                <span
                  className="funnel-bar"
                  style={{ width: `${(p.count / maxCount) * 100}%`, background: BAR }}
                />
              </span>
              <span className="funnel-count">{p.count}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>Pigment volume footprint</h2>
        <p className="hint" style={{ marginTop: -6 }}>
          mL <b>in × out</b> per product per week, from inventory transactions. In = received;
          out = used in batches or discarded.
        </p>
        <div className="fp-legend">
          <span><i style={{ background: mix(POLE_IN, 0.45) }} /> net inflow</span>
          <span><i style={{ background: NEUTRAL }} /> balanced</span>
          <span><i style={{ background: mix(POLE_OUT, 0.45) }} /> net outflow</span>
          <span className="hint">cell shows in × out (mL)</span>
        </div>
        {fp.rows.length === 0 ? (
          <p className="hint">No pigment inventory activity yet — add lots and prepare batches to see flow here.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="fp-table">
              <thead>
                <tr>
                  <th>Pigment</th>
                  {fp.weeks.map((w) => <th key={w} className="fp-week">{w}</th>)}
                  <th className="fp-total">total in / out</th>
                </tr>
              </thead>
              <tbody>
                {fp.rows.map((r) => (
                  <tr key={r.code}>
                    <td className="fp-name"><b>{r.code}</b> <span className="hint">{r.product}</span></td>
                    {r.cells.map((c, i) => (
                      <td
                        key={i}
                        className="fp-cell"
                        style={cellStyle(c)}
                        onMouseMove={(e) =>
                          showTip(e, [
                            `${r.code} — ${fp.weeks[i]}`,
                            `in ${fmt(c.in_ml)} mL · out ${fmt(c.out_ml)} mL`,
                            `net ${c.net_ml > 0 ? '+' : ''}${fmt(c.net_ml)} mL`,
                          ])
                        }
                        onMouseLeave={() => setTip(null)}
                      >
                        {c.in_ml === 0 && c.out_ml === 0 ? '' : `${fmt(c.in_ml)} × ${fmt(c.out_ml)}`}
                      </td>
                    ))}
                    <td className="fp-total">{fmt(r.total_in_ml)} / {fmt(r.total_out_ml)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {tip && (
        <div className="chart-tip" style={{ left: tip.x, top: tip.y }}>
          {tip.lines.map((l, i) => (
            <div key={i} style={i === 0 ? { fontWeight: 600 } : undefined}>{l}</div>
          ))}
        </div>
      )}
    </div>
  )
}
