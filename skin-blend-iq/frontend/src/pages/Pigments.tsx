import { useEffect, useState } from 'react'
import { api, errText } from '../api'

export default function Pigments() {
  const [products, setProducts] = useState<any[]>([])
  const [lots, setLots] = useState<any[]>([])
  const [kits, setKits] = useState<any[]>([])
  const [cals, setCals] = useState<any[]>([])
  const [error, setError] = useState('')
  const [pform, setPform] = useState({ manufacturer: '', product_name: '', internal_code: '', color_role: 'primary_yellow' })
  const [lform, setLform] = useState({ product_id: '', lot_number: '', expiry_date: '', quantity_ml: 15 })
  const [cform, setCform] = useState({ drop_volume_ml_mean: 0.05, drop_volume_ml_std: 0.002, sample_count: 20 })

  const load = () => {
    api.get('/v1/pigment-products').then(setProducts)
    api.get('/v1/pigment-lots').then(setLots)
    api.get('/v1/pigment-kits').then(setKits)
    api.get('/v1/dropper-calibrations').then(setCals)
  }
  useEffect(load, [])

  const productName = (id: string) => products.find((p) => p.id === id)?.product_name ?? id.slice(0, 8)

  const act = (fn: () => Promise<any>) => fn().then(load).catch((e) => setError(errText(e)))

  return (
    <div>
      <h2>Pigments, lots & inventory</h2>
      {error && <div className="error">{error}</div>}
      <div className="row">
        <div className="panel">
          <h3>Lots (recalled / expired / quarantined are blocked from formulas)</h3>
          <table>
            <thead><tr><th>Product</th><th>Lot</th><th>Expiry</th><th>mL</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {lots.map((l) => (
                <tr key={l.id}>
                  <td>{productName(l.product_id)}</td>
                  <td>{l.lot_number}</td>
                  <td>{l.expiry_date}</td>
                  <td>{l.quantity_ml}</td>
                  <td>
                    {l.blocked_reason
                      ? <span className="chip bad">{l.blocked_reason}</span>
                      : <span className="chip ok">active</span>}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {!l.blocked_reason && (
                      <>
                        <button className="btn small secondary" onClick={() => act(() => api.post(`/v1/pigment-lots/${l.id}/quarantine`, { reason: 'quarantined from UI' }))}>
                          quarantine
                        </button>{' '}
                        <button className="btn small secondary" onClick={() => act(() => api.post(`/v1/recalls?lot_id=${l.id}`, { reason: 'recall from UI' }))}>
                          recall
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Add lot</h3>
          <div className="row">
            <div style={{ flex: 2 }}>
              <label>Product</label>
              <select value={lform.product_id} onChange={(e) => setLform({ ...lform, product_id: e.target.value })}>
                <option value="">— select —</option>
                {products.map((p) => <option key={p.id} value={p.id}>{p.product_name} ({p.internal_code})</option>)}
              </select>
            </div>
            <div><label>Lot #</label><input value={lform.lot_number} onChange={(e) => setLform({ ...lform, lot_number: e.target.value })} /></div>
            <div><label>Expiry (YYYY-MM-DD)</label><input value={lform.expiry_date} onChange={(e) => setLform({ ...lform, expiry_date: e.target.value })} /></div>
            <div><label>mL</label><input type="number" value={lform.quantity_ml} onChange={(e) => setLform({ ...lform, quantity_ml: Number(e.target.value) })} /></div>
          </div>
          <button className="btn small" disabled={!lform.product_id || !lform.lot_number || !lform.expiry_date}
            onClick={() => act(() => api.post('/v1/pigment-lots', lform))}>
            Add lot
          </button>
        </div>

        <div className="panel" style={{ maxWidth: 380 }}>
          <h3>Pigment products</h3>
          <table>
            <thead><tr><th>Code</th><th>Name</th><th>Role</th></tr></thead>
            <tbody>
              {products.map((p) => (
                <tr key={p.id}><td>{p.internal_code}</td><td>{p.product_name}</td><td>{p.color_role}</td></tr>
              ))}
            </tbody>
          </table>
          <h3>Add product</h3>
          <label>Manufacturer</label>
          <input value={pform.manufacturer} onChange={(e) => setPform({ ...pform, manufacturer: e.target.value })} />
          <label>Product name</label>
          <input value={pform.product_name} onChange={(e) => setPform({ ...pform, product_name: e.target.value })} />
          <label>Internal code (e.g. P-Y)</label>
          <input value={pform.internal_code} onChange={(e) => setPform({ ...pform, internal_code: e.target.value })} />
          <label>Color role</label>
          <select value={pform.color_role} onChange={(e) => setPform({ ...pform, color_role: e.target.value })}>
            {['primary_yellow', 'warm_yellow', 'ochre', 'orange', 'warm_red', 'cool_red', 'primary_red', 'primary_blue',
              'olive', 'warm_brown', 'cool_brown', 'neutralizer', 'white', 'black', 'diluent'].map((r) => <option key={r}>{r}</option>)}
          </select>
          <button className="btn small" disabled={!pform.manufacturer || !pform.product_name || !pform.internal_code}
            onClick={() => act(() => api.post('/v1/pigment-products', pform))}>
            Add product
          </button>

          <h3>Kits</h3>
          {kits.map((k) => (
            <div key={k.id} className="kv" style={{ marginBottom: 8 }}>
              <b>{k.name}</b> — {k.dataset_version}{' '}
              {k.data_source === 'synthetic'
                ? <span className="chip bad">synthetic</span>
                : <span className="chip ok">measured</span>}
              <div className="hint">{k.pigments.map((p: any) => p.code).join(', ')} · {k.sample_count} mixture samples</div>
            </div>
          ))}

          <h3>Dropper calibration</h3>
          <div className="hint">Calibrate before treating "20 drops" as reproducible.</div>
          <label>Mean drop volume (mL)</label>
          <input type="number" step="0.001" value={cform.drop_volume_ml_mean} onChange={(e) => setCform({ ...cform, drop_volume_ml_mean: Number(e.target.value) })} />
          <label>Std dev (mL)</label>
          <input type="number" step="0.001" value={cform.drop_volume_ml_std} onChange={(e) => setCform({ ...cform, drop_volume_ml_std: Number(e.target.value) })} />
          <label>Sample count</label>
          <input type="number" value={cform.sample_count} onChange={(e) => setCform({ ...cform, sample_count: Number(e.target.value) })} />
          <button className="btn small" onClick={() => act(() => api.post('/v1/dropper-calibrations', cform))}>
            Record calibration
          </button>
          {cals.slice(-3).map((c) => (
            <div key={c.id} className="hint" style={{ marginTop: 4 }}>
              {c.drop_volume_ml_mean} ± {c.drop_volume_ml_std} mL (n={c.sample_count}){' '}
              {c.within_tolerance ? <span className="chip ok">in tolerance</span> : <span className="chip bad">out of tolerance</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
