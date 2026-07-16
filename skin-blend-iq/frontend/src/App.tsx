import { useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Clients from './pages/Clients'
import Capture from './pages/Capture'
import FormulaLab from './pages/FormulaLab'
import Pigments from './pages/Pigments'
import Audit from './pages/Audit'

const CORE_PAGES = [
  ['dashboard', 'Dashboard'],
  ['clients', 'Clients'],
  ['capture', 'New Capture'],
  ['formula', 'Formula Lab'],
] as const

const ADVANCED_PAGES = [
  ['pigments', 'Pigments & Inventory'],
  ['audit', 'Audit Log'],
] as const

export type PageId =
  | (typeof CORE_PAGES)[number][0]
  | (typeof ADVANCED_PAGES)[number][0]

export type ViewMode = 'simple' | 'advanced'

export default function App() {
  const [user, setUser] = useState<any>(null)
  const [checked, setChecked] = useState(false)
  const [page, setPage] = useState<PageId>('dashboard')
  // New users start in the simple view; the choice sticks per browser.
  const [mode, setModeState] = useState<ViewMode>(
    (localStorage.getItem('sbi_view_mode') as ViewMode) || 'simple',
  )
  const setMode = (m: ViewMode) => {
    localStorage.setItem('sbi_view_mode', m)
    setModeState(m)
  }

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

  const navPages = mode === 'simple' ? CORE_PAGES : [...CORE_PAGES, ...ADVANCED_PAGES]
  // If the current page is hidden by simple mode, fall back to the dashboard.
  if (!navPages.some(([id]) => id === page)) setPage('dashboard')

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="brand">
          Skin Blend IQ
          <small>artist decision support — not a diagnosis</small>
        </div>
        {navPages.map(([id, label]) => (
          <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)}>
            {label}
          </button>
        ))}
        <div className="spacer" />
        <div className="mode-toggle">
          <button
            className={mode === 'simple' ? 'on' : ''}
            onClick={() => setMode('simple')}
            title="Core screens and a guided dashboard"
          >
            Simple
          </button>
          <button
            className={mode === 'advanced' ? 'on' : ''}
            onClick={() => setMode('advanced')}
            title="All screens, studio stats, inventory, and audit log"
          >
            Advanced
          </button>
        </div>
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
        {page === 'dashboard' && <Dashboard mode={mode} setMode={setMode} go={setPage} />}
        {page === 'clients' && <Clients />}
        {page === 'capture' && <Capture />}
        {page === 'formula' && <FormulaLab />}
        {page === 'pigments' && <Pigments />}
        {page === 'audit' && <Audit />}
      </main>
    </div>
  )
}
