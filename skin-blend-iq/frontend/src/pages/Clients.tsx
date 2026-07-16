import { useEffect, useState } from 'react'
import { api, errText } from '../api'

const CONSENTS = ['treatment', 'photography', 'education', 'marketing', 'ai_training']
const CASE_TYPES = [
  'surgical_scar', 'traumatic_scar', 'burn_scar', 'stretch_marks', 'hypopigmentation',
  'vitiligo_camouflage', 'areola_restoration', 'cleft_lip_scar', 'hair_transplant_scar',
  'scalp_scar', 'skin_graft_boundary', 'radiation_marker', 'port_scar', 'other',
]

export default function Clients() {
  const [clients, setClients] = useState<any[]>([])
  const [selected, setSelected] = useState<any>(null)
  const [form, setForm] = useState({ legal_name: '', email: '', phone: '', referral_source: '' })
  const [error, setError] = useState('')

  const load = () => api.get('/v1/clients').then(setClients)
  useEffect(() => {
    load()
  }, [])

  const openClient = (id: string) => api.get(`/v1/clients/${id}`).then(setSelected)

  const createClient = async (e: any) => {
    e.preventDefault()
    setError('')
    try {
      const c = await api.post('/v1/clients', form)
      setForm({ legal_name: '', email: '', phone: '', referral_source: '' })
      await load()
      openClient(c.id)
    } catch (err) {
      setError(errText(err))
    }
  }

  return (
    <div className="row">
      <div className="panel" style={{ maxWidth: 420 }}>
        <h2>Clients</h2>
        <table>
          <thead>
            <tr><th>Code</th><th>Name</th><th>Created</th></tr>
          </thead>
          <tbody>
            {clients.map((c) => (
              <tr key={c.id} className="clickable" onClick={() => openClient(c.id)}>
                <td>{c.display_code}</td>
                <td>{c.legal_name}</td>
                <td>{c.created_at?.slice(0, 10)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3>New client</h3>
        <form onSubmit={createClient}>
          <label>Legal name</label>
          <input value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} required />
          <label>Email</label>
          <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <label>Phone</label>
          <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <label>Referral source</label>
          <input value={form.referral_source} onChange={(e) => setForm({ ...form, referral_source: e.target.value })} />
          <button className="btn" type="submit">Create client</button>
        </form>
        {error && <div className="error">{error}</div>}
      </div>
      {selected && <ClientDetail client={selected} refresh={() => openClient(selected.id)} />}
    </div>
  )
}

function ClientDetail({ client, refresh }: { client: any; refresh: () => void }) {
  const [caseType, setCaseType] = useState('vitiligo_camouflage')
  const [error, setError] = useState('')
  const consentState: Record<string, boolean> = {}
  for (const c of client.consents ?? []) consentState[c.kind] = c.granted

  const setConsent = async (kind: string, granted: boolean) => {
    try {
      await api.post(`/v1/clients/${client.id}/consents`, { kind, granted })
      refresh()
    } catch (err) {
      setError(errText(err))
    }
  }

  const addCase = async () => {
    setError('')
    try {
      await api.post('/v1/cases', { client_id: client.id, case_type: caseType })
      refresh()
    } catch (err) {
      setError(errText(err))
    }
  }

  return (
    <div className="panel">
      <h2>
        {client.display_code} — {client.legal_name}
      </h2>
      <div className="kv">
        <div><b>Email</b> {client.email || '—'}</div>
        <div><b>Phone</b> {client.phone || '—'}</div>
        <div><b>Referral</b> {client.referral_source || '—'}</div>
      </div>

      <h3>Consents (recorded separately)</h3>
      {CONSENTS.map((kind) => (
        <div key={kind} style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 0' }}>
          <span className={`chip ${consentState[kind] ? 'ok' : 'neutral'}`} style={{ minWidth: 90, textAlign: 'center' }}>
            {consentState[kind] ? 'granted' : 'not granted'}
          </span>
          <span style={{ flex: 1, fontSize: '0.85rem' }}>{kind.replace('_', ' ')}</span>
          <button className="btn small secondary" onClick={() => setConsent(kind, !consentState[kind])}>
            {consentState[kind] ? 'revoke' : 'grant'}
          </button>
        </div>
      ))}

      <h3>Cases</h3>
      <table>
        <thead><tr><th>Type</th><th>Status</th><th>ID</th></tr></thead>
        <tbody>
          {(client.cases ?? []).map((c: any) => (
            <tr key={c.id}>
              <td>{c.case_type}</td>
              <td><span className="chip neutral">{c.status}</span></td>
              <td style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>{c.id.slice(0, 8)}…</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ display: 'flex', gap: 8, alignItems: 'end' }}>
        <div style={{ flex: 1 }}>
          <label>New case type</label>
          <select value={caseType} onChange={(e) => setCaseType(e.target.value)}>
            {CASE_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
        <button className="btn" onClick={addCase}>Add case</button>
      </div>
      {error && <div className="error">{error}</div>}
    </div>
  )
}
