import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1', timeout: 30000, withCredentials: true })

api.interceptors.request.use((cfg) => {
  const t = sessionStorage.getItem('pragati_token')
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

let refreshing = null
api.interceptors.response.use((r) => r, async (err) => {
  const orig = err.config
  if (err.response?.status === 401 && orig && !orig._retry && !orig.url.includes('/auth/')) {
    orig._retry = true
    try {
      refreshing = refreshing || axios.post('/api/v1/auth/refresh', {}, { withCredentials: true })
      const res = await refreshing
      sessionStorage.setItem('pragati_token', res.data.accessToken)
      orig.headers.Authorization = `Bearer ${res.data.accessToken}`
      return api(orig)
    } catch {
      sessionStorage.removeItem('pragati_token')
      window.location.assign('/login')
    } finally { refreshing = null }
  }
  return Promise.reject(err)
})

export const errMsg = (e) => e?.response?.data?.error?.message || e?.message || 'Request failed'
export default api
