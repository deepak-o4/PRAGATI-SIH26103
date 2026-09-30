import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet.markercluster'
import { useGet } from '../hooks/useApi'
import { ErrorBox, Page } from '../components/ui'
import { BAND_COLORS, fmtCrore, fmtPct } from '../utils/format'

export default function MapPage() {
  const [f, setF] = useState({ sector: '', state: '', risk_level: '', min_cost: '', max_cost: '', min_progress: '', max_progress: '' })
  const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ''))
  const { data, error } = useGet('/map', params)
  const el = useRef(null); const map = useRef(null); const layer = useRef(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  useEffect(() => {
    if (!map.current) {
      map.current = L.map(el.current).setView([22.5, 79], 5)
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap contributors', maxZoom: 18 }).addTo(map.current)
    }
    return undefined
  }, [])
  useEffect(() => {
    if (!map.current || !data) return
    if (layer.current) map.current.removeLayer(layer.current)
    layer.current = L.markerClusterGroup()
    data.projects.forEach((p) => {
      const m = L.circleMarker([p.lat, p.lng], { radius: 8, color: '#fff', weight: 1.5, fillColor: BAND_COLORS[p.risk_band], fillOpacity: 0.95 })
      const div = document.createElement('div')
      const b = document.createElement('b'); b.textContent = `${p.project_name}`; div.appendChild(b)
      const lines = [`Code: ${p.project_code}`, `Sector: ${p.sector ?? 'n/a'}`, `Progress: ${fmtPct(p.progress)}`, `Risk: ${p.risk_band} (${Math.round(p.risk_score)})`, `Cost: ${fmtCrore(p.cost_crore)}`, `Status: ${p.status}`]
      lines.forEach((t) => { div.appendChild(document.createElement('br')); div.appendChild(document.createTextNode(t)) })
      const a = document.createElement('a'); a.href = `/projects/${encodeURIComponent(p.project_code)}`; a.textContent = 'Open cockpit →'
      div.appendChild(document.createElement('br')); div.appendChild(a)
      m.bindPopup(div)
      layer.current.addLayer(m)
    })
    map.current.addLayer(layer.current)
  }, [data])

  return (
    <Page title="Infrastructure Map" sub="Project locations. Markers are coloured by risk band; only projects with recorded coordinates are shown.">
      <div className="filters">
        <input placeholder="Sector" aria-label="Sector" value={f.sector} onChange={set('sector')} />
        <input placeholder="State" aria-label="State" value={f.state} onChange={set('state')} />
        <select aria-label="Risk" value={f.risk_level} onChange={set('risk_level')}><option value="">Any risk</option>{['CRITICAL', 'WARNING', 'WATCH', 'STABLE'].map((b) => <option key={b}>{b}</option>)}</select>
        <input type="number" placeholder="Min cost" aria-label="Min cost" value={f.min_cost} onChange={set('min_cost')} />
        <input type="number" placeholder="Max cost" aria-label="Max cost" value={f.max_cost} onChange={set('max_cost')} />
        <input type="number" placeholder="Min progress" aria-label="Min progress" value={f.min_progress} onChange={set('min_progress')} />
        <input type="number" placeholder="Max progress" aria-label="Max progress" value={f.max_progress} onChange={set('max_progress')} />
      </div>
      <ErrorBox error={error} />
      <div ref={el} style={{ height: 560, borderRadius: 6, border: '1px solid var(--line)' }} role="img" aria-label="Map of infrastructure projects" />
      {data && <div className="note">{data.projects.length} shown · {data.excluded_without_coordinates} without coordinates (not plotted). Base map tiles require internet access.</div>}
    </Page>
  )
}
