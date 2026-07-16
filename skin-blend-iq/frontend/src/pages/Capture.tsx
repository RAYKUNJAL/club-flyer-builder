import { useEffect, useRef, useState } from 'react'
import { api, errText, getToken, rgbToCss } from '../api'

type Rect = { x: number; y: number; w: number; h: number }

export default function Capture() {
  const [clients, setClients] = useState<any[]>([])
  const [cases, setCases] = useState<any[]>([])
  const [cards, setCards] = useState<any[]>([])
  const [clientId, setClientId] = useState('')
  const [caseId, setCaseId] = useState('')
  const [cardId, setCardId] = useState('')
  const [capture, setCapture] = useState<any>(null)
  const [activeImage, setActiveImage] = useState<any>(null)
  const [analysis, setAnalysis] = useState<any>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/v1/clients').then(setClients)
    api.get('/v1/reference-cards').then((c) => {
      setCards(c)
      if (c.length) setCardId(c[0].id)
    })
  }, [])

  useEffect(() => {
    if (!clientId) return
    api.get(`/v1/clients/${clientId}`).then((c) => setCases(c.cases ?? []))
  }, [clientId])

  const refreshCapture = async (id: string) => {
    const cap = await api.get(`/v1/captures/${id}`)
    setCapture(cap)
    if (activeImage) {
      const img = cap.images.find((i: any) => i.id === activeImage.id)
      if (img) setActiveImage(img)
    }
    return cap
  }

  const start = async () => {
    setError('')
    setAnalysis(null)
    try {
      const cap = await api.post('/v1/captures', {
        case_id: caseId,
        mode: 'calibrated',
        reference_card_id: cardId,
      })
      setCapture({ ...cap, images: [] })
      setActiveImage(null)
    } catch (e) {
      setError(errText(e))
    }
  }

  const upload = async (file: File) => {
    setError('')
    setBusy(true)
    try {
      const img = await api.upload(`/v1/captures/${capture.id}/images`, file)
      const cap = await refreshCapture(capture.id)
      setActiveImage(cap.images.find((i: any) => i.id === img.id))
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const analyze = async () => {
    setError('')
    try {
      setAnalysis(await api.post(`/v1/captures/${capture.id}/analyze`))
    } catch (e) {
      setError(errText(e))
    }
  }

  const card = cards.find((c) => c.id === cardId)

  return (
    <div>
      <h2>Guided calibrated capture</h2>
      <div className="banner">
        Place the reference card in the same plane and light as untreated skin. No filters, no
        mixed lighting, no glare. Capture at least <b>3 photos</b>; mark the card patches and
        unaffected skin regions on each.
      </div>
      <div className="panel">
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Client</label>
            <select value={clientId} onChange={(e) => setClientId(e.target.value)}>
              <option value="">— select —</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>{c.display_code} {c.legal_name}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Case</label>
            <select value={caseId} onChange={(e) => setCaseId(e.target.value)}>
              <option value="">— select —</option>
              {cases.map((c) => <option key={c.id} value={c.id}>{c.case_type} ({c.status})</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Reference card</label>
            <select value={cardId} onChange={(e) => setCardId(e.target.value)}>
              {cards.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
        </div>
        <button className="btn" disabled={!caseId || !cardId} onClick={start}>
          Start capture session
        </button>
      </div>

      {capture && (
        <div className="panel">
          <h3>Images ({capture.images?.length ?? 0}) — need ≥3 passing</h3>
          <input
            type="file"
            accept="image/*"
            disabled={busy}
            onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
          />
          <table style={{ marginTop: 10 }}>
            <thead><tr><th>File</th><th>Grade</th><th>Correction</th><th>Patches</th><th></th></tr></thead>
            <tbody>
              {(capture.images ?? []).map((img: any) => (
                <tr key={img.id} className="clickable" onClick={() => setActiveImage(img)}>
                  <td>{img.filename}</td>
                  <td>
                    <span className={`chip ${img.grade === 'pass' ? 'ok' : img.grade === 'marginal' ? 'warn' : 'bad'}`}>
                      {img.grade}
                    </span>
                  </td>
                  <td>
                    {img.correction_residual != null
                      ? `residual ΔE00 ${img.correction_residual}${img.correction_passed ? '' : ' (FAILED)'}`
                      : 'not fitted'}
                  </td>
                  <td>{img.skin_patches?.length ?? 0}</td>
                  <td>{activeImage?.id === img.id ? '◀ editing' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {activeImage && card && (
            <ImageAnnotator
              key={activeImage.id}
              image={activeImage}
              cardPatchCount={card.patches.length}
              cardPatchNames={card.patches.map((p: any) => p.name)}
              onChanged={() => refreshCapture(capture.id)}
            />
          )}
          <button className="btn" onClick={analyze} style={{ marginTop: 14 }}>
            Analyze capture
          </button>
        </div>
      )}

      {analysis && <AnalysisResult m={analysis} />}
      {error && <div className="error">{error}</div>}
    </div>
  )
}

function ImageAnnotator({
  image,
  cardPatchCount,
  cardPatchNames,
  onChanged,
}: {
  image: any
  cardPatchCount: number
  cardPatchNames: string[]
  onChanged: () => void
}) {
  const [mode, setMode] = useState<'card' | 'skin'>(image.correction_residual == null ? 'card' : 'skin')
  const [rects, setRects] = useState<Rect[]>([])
  const [drag, setDrag] = useState<Rect | null>(null)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const imgRef = useRef<HTMLImageElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  const scale = () => {
    const el = imgRef.current!
    return el.naturalWidth / el.clientWidth
  }

  const pos = (e: React.MouseEvent) => {
    const r = wrapRef.current!.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  const down = (e: React.MouseEvent) => {
    const p = pos(e)
    setDrag({ x: p.x, y: p.y, w: 0, h: 0 })
  }
  const move = (e: React.MouseEvent) => {
    if (!drag) return
    const p = pos(e)
    setDrag({ ...drag, w: p.x - drag.x, h: p.y - drag.y })
  }
  const up = () => {
    if (drag && Math.abs(drag.w) > 4 && Math.abs(drag.h) > 4) {
      const norm = {
        x: Math.min(drag.x, drag.x + drag.w),
        y: Math.min(drag.y, drag.y + drag.h),
        w: Math.abs(drag.w),
        h: Math.abs(drag.h),
      }
      setRects([...rects, norm])
    }
    setDrag(null)
  }

  const submit = async () => {
    setError('')
    setMsg('')
    const s = scale()
    const natural = rects.map((r) => ({
      x: Math.round(r.x * s),
      y: Math.round(r.y * s),
      w: Math.round(r.w * s),
      h: Math.round(r.h * s),
    }))
    try {
      if (mode === 'card') {
        const res = await api.post(`/v1/images/${image.id}/card-patches`, { patches: natural })
        setMsg(`Correction fitted: residual ΔE00 ${res.residual_delta_e00} (${res.passed ? 'passed' : 'FAILED'})`)
      } else {
        await api.post(`/v1/images/${image.id}/skin-patches`, { patches: natural })
        setMsg(`${natural.length} skin patch(es) added`)
      }
      setRects([])
      onChanged()
    } catch (e) {
      setError(errText(e))
    }
  }

  const need = mode === 'card' ? cardPatchCount : null

  return (
    <div style={{ marginTop: 14 }}>
      <h3>Mark regions on {image.filename}</h3>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <button className={`btn small ${mode === 'card' ? '' : 'secondary'}`} onClick={() => { setMode('card'); setRects([]) }}>
          Card patches ({cardPatchCount}, in order: {cardPatchNames.join(', ')})
        </button>
        <button className={`btn small ${mode === 'skin' ? '' : 'secondary'}`} onClick={() => { setMode('skin'); setRects([]) }}>
          Skin patches
        </button>
        <button className="btn small secondary" onClick={() => setRects([])}>Clear</button>
        <button
          className="btn small"
          disabled={need != null ? rects.length !== need : rects.length === 0}
          onClick={submit}
        >
          Submit {rects.length}{need != null ? `/${need}` : ''} rect(s)
        </button>
      </div>
      <div
        ref={wrapRef}
        className="imgwrap"
        onMouseDown={down}
        onMouseMove={move}
        onMouseUp={up}
        onMouseLeave={up}
        style={{ cursor: 'crosshair' }}
      >
        <img
          ref={imgRef}
          src={`/v1/images/${image.id}/file?token=`}
          draggable={false}
          alt="capture"
          onError={(e) => {
            // fetch with auth header instead (img tag cannot send it)
            const el = e.currentTarget
            if (el.dataset.retried) return
            el.dataset.retried = '1'
            fetch(`/v1/images/${image.id}/file`, {
              headers: { Authorization: `Bearer ${getToken()}` },
            })
              .then((r) => r.blob())
              .then((b) => (el.src = URL.createObjectURL(b)))
          }}
        />
        {[...rects, ...(drag ? [drag] : [])].map((r, i) => (
          <div
            key={i}
            className={`rect ${mode}`}
            style={{
              left: Math.min(r.x, r.x + r.w),
              top: Math.min(r.y, r.y + r.h),
              width: Math.abs(r.w),
              height: Math.abs(r.h),
            }}
          >
            {mode === 'card' ? cardPatchNames[i] : `skin ${i + 1}`}
          </div>
        ))}
      </div>
      <div className="hint">
        Drag rectangles. Card mode: mark all {cardPatchCount} card patches in the listed order.
        Skin mode: mark unaffected skin only — avoid glare, shadow, hair, redness, and scar tissue.
      </div>
      {(image.skin_patches ?? []).length > 0 && (
        <table style={{ marginTop: 8 }}>
          <thead><tr><th>Patch</th><th>Median RGB</th><th>L*a*b*</th><th>Pixels</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {image.skin_patches.map((p: any, i: number) => (
              <tr key={p.id}>
                <td>
                  <span className="swatch" style={{ width: 22, height: 22, display: 'inline-block', background: rgbToCss(p.corrected_rgb ?? p.median_rgb) }} />
                </td>
                <td>{(p.corrected_rgb ?? p.median_rgb)?.map((v: number) => Math.round(v)).join(', ')}</td>
                <td>{p.lab?.map((v: number) => v.toFixed(1)).join(', ')}</td>
                <td>{p.pixel_count}</td>
                <td>{p.rejected ? <span className="chip bad">rejected: {p.reject_reason}</span> : <span className="chip ok">accepted</span>}</td>
                <td>
                  {!p.rejected && (
                    <button
                      className="btn small secondary"
                      onClick={() =>
                        api.post(`/v1/patches/${p.id}/reject`, { reason: 'outlier' }).then(onChanged).catch((e) => setError(errText(e)))
                      }
                    >
                      reject
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {msg && <div className="success">{msg}</div>}
      {error && <div className="error">{error}</div>}
    </div>
  )
}

export function AnalysisResult({ m }: { m: any }) {
  return (
    <div className="panel">
      <h2>Analysis result</h2>
      <div className="row">
        <div>
          <div className="swatch large" style={{ background: rgbToCss(m.rgb_display) }} />
          <div className="hint" style={{ marginTop: 4 }}>display approximation</div>
        </div>
        <div className="kv" style={{ flex: 1 }}>
          <div><b>L* a* b*</b> {m.lab_l}, {m.lab_a}, {m.lab_b} ({m.illuminant}/{m.observer})</div>
          <div><b>RGB (display only)</b> {m.rgb_display?.map((v: number) => Math.round(v)).join(', ')}</div>
          <div><b>HSV</b> {m.hsv?.map((v: number) => v.toFixed(2)).join(', ')}</div>
          <div><b>ITA°</b> {m.ita_degrees ?? '—'}</div>
          <div><b>Undertone</b> {m.undertone} (confidence {m.undertone_confidence})</div>
          <div><b>Uncertainty (ΔE)</b> ±{m.delta_e_uncertainty}</div>
          <div>
            <b>Treatment grade</b>{' '}
            {m.treatment_grade ? (
              <span className="chip ok">yes — calibrated & quality gates passed</span>
            ) : (
              <span className="chip bad">no</span>
            )}
          </div>
          <div><b>Measurement ID</b> <code style={{ fontSize: '0.75rem' }}>{m.id}</code></div>
        </div>
      </div>
      {(m.warnings ?? []).map((w: string, i: number) => (
        <div className="banner danger" key={i} style={{ marginTop: 10 }}>{w}</div>
      ))}
      <div className="hint" style={{ marginTop: 8 }}>
        Use this measurement ID in the Formula Lab to generate a drop formula.
      </div>
    </div>
  )
}
