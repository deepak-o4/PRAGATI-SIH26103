import { useGet } from '../hooks/useApi'
import { BarBox } from '../charts/charts'
import { ErrorBox, Loading, Page, Table } from '../components/ui'
import { fmtCrore, fmtDays, fmtNum } from '../utils/format'

export default function Bottlenecks() {
  const { data, error, loading } = useGet('/bottlenecks')
  return (
    <Page title="Bottleneck Analytics" sub="Implementation bottlenecks aggregated from open issues recorded against projects. Nothing here is estimated.">
      <ErrorBox error={error} /><Loading loading={loading} />
      {data && <><div className="card"><h2>Projects affected by category</h2><BarBox data={data.items} x="category" y="projects_affected" horizontal /></div>
        <div className="card" style={{ marginTop: 12 }}><Table rows={data.items} empty="No open issues recorded." columns={[
          { key: 'category', label: 'Category' }, { key: 'projects_affected', label: 'Projects affected' }, { key: 'open_issues', label: 'Open issues' }, { key: 'critical_issues', label: 'Critical' },
          { key: 'avg_delay_days', label: 'Average delay', render: (r) => fmtDays(r.avg_delay_days == null ? null : Math.round(r.avg_delay_days)) }, { key: 'avg_risk', label: 'Average risk', render: (r) => fmtNum(r.avg_risk, 1) },
          { key: 'affected_project_value_crore', label: 'Affected project value', render: (r) => fmtCrore(r.affected_project_value_crore) }]} /></div></>}
    </Page>
  )
}
