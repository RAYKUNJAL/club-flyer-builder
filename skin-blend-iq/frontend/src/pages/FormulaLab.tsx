import { useEffect, useState } from 'react'
import { api, errText, getToken, rgbToCss } from '../api'

export default function FormulaLab() {
  const [kits, setKits] = useState<any[]>([])
  const [lots, setLots] = useState<any[]>([])
  const [products, setProducts] = useState<any[]>([])
  const [formulas, setFormulas] = useState<any[]>([])
  const [formula, setFormula] = useState<any>(null)
  const [error, setError] = useState('')

  const [gen, setGen] = useState({
    target_measurement_id: '',
    pigment_kit_id: '',
    total_drops: 20,
    purpose: 'full_session',
  })
  const [lotSel, setLotSel] = useState<Record<string, string>>({})

  const load = () => {
    api.get('/v1/pigment-kits').then((k) => {
      setKits(k)
      if (k.length && !gen.pigment_kit_id) setGen((g) => ({ ...g, pigment_kit_id: k[0].id }))
    })
    api.get('/v1/pigment-lots').then(setLots)
    api.get('/v1/pigment-products').then(setProducts)
    api.get('/v1/formulas').then(setFormulas)
  }
  useEffect(load, [])

  const kit = kits.find((k) => k.id === gen.pigment_kit_id)
  const productById = (id: string) => products.find((p) => p.id === id)
  const lotsForProduct = (pid: string) => lots.filter((l) => l.product_id === pid && !l.blocked_reason)

  const openFormula = (id: string) =>
    api.get(`/v1/formulas/${id}`).then(setFormula).catch((e) => setError(errText(e)))

  const generate = async () => {
    setError('')
    try {
      const f = await api.post('/v1/formulas/generate', {
        ...gen,
        total_drops: Number(gen.total_drops),
        lot_selection: lotSel,
      })
      setFormula(f)
      load()
    } catch (e) {
      setError(errText(e))
    }
  }

  return (
    <div>
      <h2>Formula Lab</h2>
      <div className="row">
        <div className="panel" style={{ maxWidth: 430 }}>
          <h3>Generate formula</h3>
          <label>Target measurement ID (from capture analysis)</label>
          <input
            value={gen.target_measurement_id}
            onChange={(e) => setGen({ ...gen, target_measurement_id: e.target.value.trim() })}
            placeholder="paste measurement id"
          />
          <label>Pigment kit</label>
          <select value={gen.pigment_kit_id} onChange={(e) => setGen({ ...gen, pigment_kit_id: e.target.value })}>
            {kits.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name} [{k.data_source}] — {k.dataset_version}
              </option>
            ))}
          </select>
          {kit?.data_source === 'synthetic' && (
            <div className="banner danger" style={{ marginTop: 8 }}>
              Prototype kit with synthetic data — formulas are never treatment-grade and must never
              be used on a person.
            </div>
          )}
          <label>Total drops</label>
          <select value={gen.total_drops} onChange={(e) => setGen({ ...gen, total_drops: Number(e.target.value) })}>
            {[10, 20, 40].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <label>Purpose</label>
          <select value={gen.purpose} onChange={(e) => setGen({ ...gen, purpose: e.target.value })}>
            <option value="test_spot">test spot</option>
            <option value="full_session">full session</option>
            <option value="touch_up">touch-up</option>
          </select>
          {kit && (
            <>
              <h3>Lot selection (blocked lots are hidden)</h3>
              {kit.pigments.map((p: any) => (
                <div key={p.code}>
                  <label>{p.code} — {productById(p.product_id)?.product_name}</label>
                  <select
                    value={lotSel[p.code] ?? ''}
                    onChange={(e) => setLotSel({ ...lotSel, [p.code]: e.target.value })}
                  >
                    <option value="">— select lot —</option>
                    {lotsForProduct(p.product_id).map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.lot_number} (exp {l.expiry_date}, {l.quantity_ml} mL)
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </>
          )}
          <button className="btn" onClick={generate} disabled={!gen.target_measurement_id || !kit}>
            Generate formula
          </button>
          {error && <div className="error">{error}</div>}

          <h3>Recent formulas</h3>
          <table>
            <thead><tr><th>Status</th><th>ΔE00</th><th>Drops</th><th>Grade</th></tr></thead>
            <tbody>
              {formulas.slice(0, 8).map((f) => (
                <tr key={f.id} className="clickable" onClick={() => openFormula(f.id)}>
                  <td><span className="chip neutral">{f.status}</span></td>
                  <td>{f.predicted_delta_e00}</td>
                  <td>{f.cap_total_drops}</td>
                  <td>{f.treatment_grade ? <span className="chip ok">tx</span> : <span className="chip bad">no-tx</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {formula && <FormulaDetail formula={formula} refresh={() => openFormula(formula.id)} onError={setError} />}
      </div>
    </div>
  )
}

function FormulaDetail({ formula: f, refresh, onError }: { formula: any; refresh: () => void; onError: (s: string) => void }) {
  const [reason, setReason] = useState('')
  const [drops, setDrops] = useState<Record<string, number>>({ ...f.recipe })
  const [swatchLab, setSwatchLab] = useState('')
  const [scaled, setScaled] = useState<any>(null)
  const [batch, setBatch] = useState<any>(null)

  useEffect(() => setDrops({ ...f.recipe }), [f.id, JSON.stringify(f.recipe)])

  const post = (path: string, body?: any) =>
    api.post(path, body).then(refresh).catch((e) => onError(errText(e)))

  const activeSwatch = (f.swatches ?? []).find((s: any) => s.status === 'prepared')
  const totalEdit = Object.values(drops).reduce((a, b) => a + Number(b || 0), 0)

  const measureSwatch = () => {
    const lab = swatchLab.split(',').map((v) => parseFloat(v.trim()))
    if (lab.length !== 3 || lab.some(isNaN)) return onError('Enter swatch L*a*b* as three comma-separated numbers')
    post(`/v1/swatches/${activeSwatch.id}/measure`, { lab, source_type: 'instrument' })
  }

  const scale = (preset: string) =>
    api.post(`/v1/formulas/${f.id}/scale`, { preset }).then(setScaled).catch((e) => onError(errText(e)))

  const makeBatch = () =>
    api.post('/v1/batches', { formula_id: f.id, preset: '1/4_fl_oz' }).then(setBatch).catch((e) => onError(errText(e)))

  const downloadPdf = async () => {
    const res = await fetch(`/v1/formulas/${f.id}/report.pdf`, { headers: { Authorization: `Bearer ${getToken()}` } })
    const blob = await res.blob()
    window.open(URL.createObjectURL(blob))
  }

  return (
    <div className="panel" style={{ flex: 2 }}>
      <h2>
        Formula v{f.version} <span className="chip neutral">{f.status}</span>{' '}
        {f.treatment_grade ? <span className="chip ok">treatment grade</span> : <span className="chip bad">NOT treatment grade</span>}{' '}
        {f.gamut_status === 'outside' && <span className="chip warn">out of gamut</span>}
      </h2>
      {(f.warnings ?? []).map((w: string, i: number) => (
        <div className="banner danger" key={i}>{w}</div>
      ))}

      <div className="row">
        <div>
          <div style={{ display: 'flex', gap: 10 }}>
            <div>
              <div className="swatch large" style={{ background: rgbToCss(f.target_rgb_display) }} />
              <div className="hint">target</div>
            </div>
            <div>
              <div className="swatch large" style={{ background: rgbToCss(f.predicted_rgb_display) }} />
              <div className="hint">predicted</div>
            </div>
          </div>
        </div>
        <div className="kv" style={{ flex: 1 }}>
          <div><b>Target L*a*b*</b> {f.target_lab?.join(', ')}</div>
          <div><b>Predicted L*a*b*</b> {f.predicted_lab?.join(', ')}</div>
          <div><b>Predicted ΔE2000</b> {f.predicted_delta_e00} (ΔE76 {f.predicted_delta_e76})</div>
          <div><b>Rounding ΔE added</b> {f.rounding_delta_e}</div>
          <div><b>Confidence</b> {f.confidence}</div>
          <div><b>Model / dataset</b> {f.model_version} / {f.dataset_version}</div>
          <div><b>Verification</b> external swatch mandatory</div>
        </div>
      </div>

      <h3>Recipe — {f.cap_total_drops} drops</h3>
      {Object.entries(f.recipe ?? {}).map(([code, n]: any) => (
        <div className="recipe-row" key={code}>
          <span className="code">{code}</span>
          <div className="bar" style={{ width: Math.max(6, n * 14) }} />
          <span>{n} drops</span>
          {['draft', 'swatch_prepared', 'swatch_measured', 'artist_adjusted'].includes(f.status) && (
            <>
              <button className="btn small secondary" onClick={() => setDrops({ ...drops, [code]: Math.max(0, (drops[code] ?? 0) - 1) })}>−</button>
              <button className="btn small secondary" onClick={() => setDrops({ ...drops, [code]: (drops[code] ?? 0) + 1 })}>+</button>
              {drops[code] !== n && <span className="chip warn">→ {drops[code]}</span>}
            </>
          )}
        </div>
      ))}
      <div className="hint">Lots: {(f.ingredients ?? []).map((i: any) => `${i.code}:${i.lot_number}`).join('  ')}</div>

      {['draft', 'swatch_prepared', 'swatch_measured', 'artist_adjusted'].includes(f.status) && (
        <>
          {JSON.stringify(drops) !== JSON.stringify(f.recipe) && (
            <div style={{ marginTop: 8 }}>
              <label>Adjustment reason (required, total now {totalEdit})</label>
              <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. healed too warm last session" />
              <button className="btn small" disabled={reason.length < 3} onClick={() => post(`/v1/formulas/${f.id}/adjust`, { drops, reason })}>
                Apply adjustment
              </button>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            {[10, 20, 40].filter((n) => n !== f.cap_total_drops).map((n) => (
              <button key={n} className="btn small secondary" onClick={() => post(`/v1/formulas/${f.id}/quantize`, { total_drops: n })}>
                Re-quantize to {n} drops
              </button>
            ))}
          </div>
        </>
      )}

      <h3>Verification & lifecycle</h3>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        {['draft', 'artist_adjusted'].includes(f.status) && (
          <button className="btn small" onClick={() => post('/v1/swatches', { formula_id: f.id })}>
            Prepare external swatch
          </button>
        )}
        {f.status === 'swatch_prepared' && activeSwatch && (
          <>
            <input
              style={{ width: 200 }}
              placeholder="measured swatch L*, a*, b*"
              value={swatchLab}
              onChange={(e) => setSwatchLab(e.target.value)}
            />
            <button className="btn small" onClick={measureSwatch}>Record swatch measurement</button>
          </>
        )}
        {f.status === 'swatch_measured' && (
          <button className="btn small" onClick={() => post(`/v1/formulas/${f.id}/approve`)}>
            Approve (artist)
          </button>
        )}
        {f.status === 'approved' && (
          <button className="btn small" onClick={() => post(`/v1/formulas/${f.id}/lock`)}>
            Lock formula & lots
          </button>
        )}
        {['locked', 'used'].includes(f.status) && (
          <>
            <button className="btn small secondary" onClick={() => scale('1/2_fl_oz')}>Scale to 1/2 oz</button>
            <button className="btn small secondary" onClick={makeBatch}>Prepare 1/4 oz batch</button>
            <button className="btn small secondary" onClick={() => post(`/v1/formulas/${f.id}/new-version`)}>New version</button>
          </>
        )}
        <button className="btn small secondary" onClick={downloadPdf}>PDF report</button>
      </div>

      {(f.swatches ?? []).length > 0 && (
        <table style={{ marginTop: 10 }}>
          <thead><tr><th>Swatch</th><th>Status</th><th>ΔE00 vs target</th></tr></thead>
          <tbody>
            {f.swatches.map((s: any) => (
              <tr key={s.id}>
                <td>{s.substrate}</td>
                <td>{s.status}</td>
                <td>{s.measurements?.map((m: any) => m.delta_e00_vs_target).join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {scaled && (
        <>
          <h3>Scaled batch ({scaled.basis}) — total {scaled.total_ml} mL</h3>
          <table>
            <thead><tr><th>Pigment</th><th>mL</th><th>Rounding diff</th></tr></thead>
            <tbody>
              {Object.entries(scaled.ingredients_ml).map(([c, ml]: any) => (
                <tr key={c}>
                  <td>{c}</td>
                  <td>{ml}</td>
                  <td>{scaled.rounding_differences_ml?.[c]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {batch && (
        <>
          <h3>Batch {batch.display_code}</h3>
          <pre className="label">{batch.label_text}</pre>
        </>
      )}
    </div>
  )
}
