import { useGet } from '../hooks/useApi'
import { ErrorBox, Loading, Page, Table } from '../components/ui'
import { useAuth } from '../services/auth'

export default function SettingsPage() {
  const { user } = useAuth()
  const { data, error, loading } = useGet('/risk-config')
  return (
    <Page title="Settings" sub="Signed-in account and risk-engine configuration (read-only)">
      <div className="card"><h2>Account</h2><div>{user.name} · {user.email} · <span className="tag">{user.role}</span></div></div>
      <ErrorBox error={error} /><Loading loading={loading} />
      {data && <div className="card" style={{ marginTop: 12 }}><h2>Risk engine {data.version}</h2>
        <Table rows={Object.entries(data.weights_pct_normalised).map(([k, v]) => ({ id: k, component: k, weight: `${v.toFixed(1)}%` }))} columns={[{ key: 'component', label: 'Component' }, { key: 'weight', label: 'Weight' }]} />
        <div className="note">Bands: {Object.entries(data.bands).map(([k, v]) => `${k} ${v}`).join(' · ')}. {data.disclaimer} Change weights via the RISK_WEIGHTS_JSON environment variable.</div></div>}
    </Page>
  )
}
