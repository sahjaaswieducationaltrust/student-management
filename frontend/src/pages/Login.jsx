import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Field } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { errorMessage } from '../lib/api'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(form.email.trim(), form.password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(errorMessage(err, 'Unable to sign in'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <img src="/hellokids-logo.png" alt="Hello Kids" />
        </div>
        <h1 style={{ textAlign: 'center', marginBottom: 4 }}>Hello Kids</h1>
        {/* The settings endpoint needs a token, so the trust is named here
            statically — this page renders before anyone has signed in. */}
        <p className="muted small" style={{ textAlign: 'center', marginBottom: 2 }}>
          A unit of Sahjaswi Educational Trust
        </p>
        <p className="muted small" style={{ textAlign: 'center', marginBottom: 18 }}>
          School Management · children, teachers, fees &amp; attendance
        </p>

        <Card>
          <form onSubmit={submit} className="stack" style={{ gap: 14 }}>
            {error && <div className="alert error">{error}</div>}

            <Field label="Email address" required>
              <input
                type="email"
                autoComplete="username"
                autoFocus
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="you@example.com"
              />
            </Field>

            <Field label="Password" required>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder="••••••••"
              />
            </Field>

            <button className="btn primary block" type="submit" disabled={busy}>
              {busy ? <span className="spinner" /> : 'Sign in'}
            </button>

            <div className="login-hint">
              Forgotten your password? Ask an administrator to reset it from the
              Users page.
            </div>
          </form>
        </Card>
      </div>
    </div>
  )
}
