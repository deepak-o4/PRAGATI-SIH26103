export const fmtCrore = (v) => (v == null ? 'n/a' : `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })} Cr`)
export const fmtPct = (v, d = 1) => (v == null ? 'n/a' : `${Number(v).toFixed(d)}%`)
export const fmtNum = (v, d = 0) => (v == null ? 'n/a' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d }))
export const fmtDays = (v) => (v == null ? 'n/a' : `${Number(v).toLocaleString('en-IN')} d`)
export const fmtDate = (v) => (v ? String(v).slice(0, 10) : 'n/a')
export const BAND_COLORS = { STABLE: '#2e7d32', WATCH: '#f9a825', WARNING: '#ef6c00', CRITICAL: '#c62828' }
export const bandOf = (score) => {
  if (score == null) return null
  const s = Math.round(score)
  return s <= 30 ? 'STABLE' : s <= 60 ? 'WATCH' : s <= 80 ? 'WARNING' : 'CRITICAL'
}
