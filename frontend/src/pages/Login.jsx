import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../services/auth'
import { errMsg } from '../services/api'
import { ErrorBox } from '../components/ui'

export default function Login() {
  const { user, login } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/dashboard" replace />
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(null)
    try { await login(email, password); nav('/dashboard') } catch (err) { setError(errMsg(err)) } finally { setBusy(false) }
  }
  return (
    <div className="login"><div className="card">
      <h1>PRAGATI</h1><div className="sub">Infrastructure project monitoring &amp; risk intelligence</div>
      <ErrorBox error={error} />
      <form onSubmit={submit}>
        <label htmlFor="em">Email</label><input id="em" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        <label htmlFor="pw">Password</label><input id="pw" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        <p><button disabled={busy} style={{ width: '100%' }}>{busy ? 'Signing in…' : 'Sign in'}</button></p>
      </form>
    </div></div>
  )
}
