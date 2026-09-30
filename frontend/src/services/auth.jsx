import { createContext, useContext, useEffect, useState } from 'react'
import api from './api'

const Ctx = createContext(null)
export const useAuth = () => useContext(Ctx)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!sessionStorage.getItem('pragati_token')) { setReady(true); return }
    api.get('/auth/me').then((r) => setUser(r.data)).catch(() => sessionStorage.removeItem('pragati_token')).finally(() => setReady(true))
  }, [])
  const login = async (email, password) => {
    const r = await api.post('/auth/login', { email, password })
    sessionStorage.setItem('pragati_token', r.data.accessToken)
    setUser(r.data.user)
  }
  const logout = async () => {
    try { await api.post('/auth/logout') } catch { /* ignore */ }
    sessionStorage.removeItem('pragati_token')
    setUser(null)
  }
  const canWrite = ['SUPER_ADMIN', 'ADMIN', 'PROGRAM_MANAGER', 'PROJECT_MANAGER'].includes(user?.role)
  const canAnalyse = canWrite || user?.role === 'ANALYST'
  return <Ctx.Provider value={{ user, ready, login, logout, canWrite, canAnalyse }}>{children}</Ctx.Provider>
}
