import { useState } from 'react'
import { api, errText, setToken } from '../api'

export default function Login({ onLogin }: { onLogin: (u: any) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [form, setForm] = useState({ email: '', password: '', name: '', studio_name: '' })
  const [error, setError] = useState('')
  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e: any) => {
    e.preventDefault()
    setError('')
    try {
      const data =
        mode === 'login'
          ? await api.post('/v1/auth/login', { email: form.email, password: form.password })
          : await api.post('/v1/auth/register-studio', form)
      setToken(data.token)
      onLogin(data.user)
    } catch (err) {
      setError(errText(err))
    }
  }

  return (
    <div className="login-shell">
      <div className="panel login-card">
        <h2>Skin Blend IQ</h2>
        <p className="hint">
          Professional decision-support for paramedical tattoo practitioners. Demo studio:{' '}
          <code>demo@skinblendiq.test</code> / <code>demo-password-123</code>
        </p>
        <form onSubmit={submit}>
          {mode === 'register' && (
            <>
              <label>Studio name</label>
              <input value={form.studio_name} onChange={set('studio_name')} required />
              <label>Your name</label>
              <input value={form.name} onChange={set('name')} required />
            </>
          )}
          <label>Email</label>
          <input value={form.email} onChange={set('email')} required />
          <label>Password</label>
          <input type="password" value={form.password} onChange={set('password')} required />
          <button className="btn" type="submit">
            {mode === 'login' ? 'Sign in' : 'Register studio'}
          </button>
          <button
            className="btn secondary"
            type="button"
            style={{ marginLeft: 8 }}
            onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          >
            {mode === 'login' ? 'New studio' : 'Back to sign in'}
          </button>
        </form>
        {error && <div className="error">{error}</div>}
      </div>
    </div>
  )
}
