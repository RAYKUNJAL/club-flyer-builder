import { useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Clients from './pages/Clients'
import Capture from './pages/Capture'
import FormulaLab from './pages/FormulaLab'
import Pigments from './pages/Pigments'
import Audit from './pages/Audit'

const PAGES = [
  ['dashboard', 'Dashboard'],
  ['clients', 'Clients'],
  ['capture', 'New Capture'],
  ['formula', 'Formula Lab'],
  ['pigments', 'Pigments & Inventory'],
  ['audit', 'Audit Log'],
] as const

export type PageId = (typeof PAGES)[number][0]

export default function App() {
  const [user, setUser] = useState<any>(null)
  const [checked, setChecked] = useState(false)
  const [page, setPage] = useState<PageId>('dashboard')

  useEffect(() => {
    if (!getToken()) {
      setChecked(true)
      return
    }
    api
      .get('/v1/auth/me')
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setChecked(true))
  }, [])

  if (!checked) return null
  if (!user) return <Login onLogin={setUser} />

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="brand">
          Skin Blend IQ
          <small>artist decision support — not a diagnosis</small>
        </div>
        {PAGES.map(([id, label]) => (
          <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)}>
            {label}
          </button>
        ))}
        <div className="spacer" />
        <div className="who">
          {user.name} ({user.role})
          <br />
          <a
            href="#"
            style={{ color: '#b3a89e' }}
            onClick={(e) => {
              e.preventDefault()
              setToken(null)
              setUser(null)
            }}
          >
            Sign out
          </a>
        </div>
      </nav>
      <main className="main">
        {!user.professional_ack_at && (
          <div className="banner danger">
            <b>Professional acknowledgment required.</b> This platform supports — never replaces —
            professional judgment. It does not diagnose, and photographs cannot guarantee healed
            color.{' '}
            <button
              className="btn small"
              onClick={() => api.post('/v1/auth/acknowledge').then(setUser)}
            >
              I acknowledge
            </button>
          </div>
        )}
        {page === 'dashboard' && <Dashboard />}
        {page === 'clients' && <Clients />}
        {page === 'capture' && <Capture />}
        {page === 'formula' && <FormulaLab />}
        {page === 'pigments' && <Pigments />}
        {page === 'audit' && <Audit />}
      </main>
    </div>
  )
}
