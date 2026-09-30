import { useCallback, useEffect, useState } from 'react'
import api, { errMsg } from '../services/api'

export function useGet(url, params) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const key = JSON.stringify(params || {})
  const load = useCallback(() => {
    setLoading(true)
    api.get(url, { params: JSON.parse(key) })
      .then((r) => { setData(r.data); setError(null) })
      .catch((e) => setError(errMsg(e)))
      .finally(() => setLoading(false))
  }, [url, key])
  useEffect(() => { load() }, [load])
  return { data, error, loading, reload: load }
}
