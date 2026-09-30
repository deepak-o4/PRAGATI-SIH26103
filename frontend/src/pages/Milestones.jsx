import { useState } from 'react'
import { useGet } from '../hooks/useApi'
import { ErrorBox, Loading, Page, ProgressBar, ProjectLink, Table, Tabs } from '../components/ui'
import { fmtDate, fmtDays } from '../utils/format'

export default function Milestones() {
  const [scope, setScope] = useState('overdue')
  const { data, error, loading } = useGet('/milestones', { scope })
  return (
    <Page title="Milestones" sub="Portfolio milestone monitor, derived only from recorded milestones">
      <Tabs tabs={['overdue', 'upcoming', 'delayed', 'all']} value={scope} onChange={setScope} />
      <ErrorBox error={error} /><Loading loading={loading} />
      {data && <div className="card"><div className="note">{data.count} milestone(s)</div><Table rows={data.items} columns={[
        { key: 'project_code', label: 'Project', render: (r) => <ProjectLink code={r.project_code} /> }, { key: 'milestone', label: 'Milestone' },
        { key: 'planned_end', label: 'Planned end', render: (r) => fmtDate(r.planned_end) }, { key: 'actual_end', label: 'Actual end', render: (r) => fmtDate(r.actual_end) },
        { key: 'completion_pct', label: 'Done', render: (r) => <ProgressBar value={r.completion_pct} /> }, { key: 'delay_days', label: 'Delay', render: (r) => fmtDays(r.delay_days) },
        { key: 'status', label: 'Status' }, { key: 'depends_on', label: 'Depends on' }]} /></div>}
    </Page>
  )
}
