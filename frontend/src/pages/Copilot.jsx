import { useState } from 'react'
import api, { errMsg } from '../services/api'
import { ErrorBox, Page, Table } from '../components/ui'

const SUGGEST = ['Which projects are at critical risk?', 'Which projects have the highest cost overruns?', 'Which projects have stalled progress?',
  'Which projects have high expenditure but low physical progress?', 'Which sectors have the highest average risk?', 'What projects are approaching their revised completion date?']

export default function Copilot() {
  const [q, setQ] = useState(''); const [msgs, setMsgs] = useState([]); const [busy, setBusy] = useState(false); const [err, setErr] = useState(null)
  const ask = async (text) => {
    if (!text.trim()) return
    setErr(null); setBusy(true); setMsgs((m) => [...m, { u: text }]); setQ('')
    try { const r = await api.post('/copilot', { question: text }); setMsgs((m) => [...m, { a: r.data }]) } catch (e) { setErr(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <Page title="PRAGATI Copilot" sub="Answers are computed from application data; every figure comes with its evidence. Questions outside supported analyses are not guessed.">
      <div className="filters">{SUGGEST.map((s) => <button key={s} className="sec" onClick={() => ask(s)}>{s}</button>)}</div>
      <div className="chat">
        {msgs.map((m, i) => m.u ? <div key={i} className="msg u">{m.u}</div> : (
          <div key={i} className="msg a">
            {m.a.demo_data_notice && <div className="demo">{m.a.demo_data_notice}</div>}
            <div style={{ whiteSpace: 'pre-wrap' }}>{m.a.answer}</div>
            {m.a.table?.length > 0 && <div style={{ marginTop: 8 }}><Table rows={m.a.table} columns={Object.keys(m.a.table[0]).map((k) => ({ key: k, label: k.replace(/_/g, ' ') }))} /></div>}
            {m.a.evidence?.length > 0 && <details style={{ marginTop: 8 }}><summary className="note">Evidence ({m.a.evidence.length})</summary>
              <div className="scroll"><table><thead><tr><th>Project</th><th>As of</th><th>Origin</th><th>Physical %</th><th>Original ₹Cr</th><th>Revised ₹Cr</th><th>Expenditure ₹Cr</th><th>Risk</th></tr></thead><tbody>
                {m.a.evidence.map((e) => <tr key={e.project_code}><td>{e.project_code}</td><td>{e.snapshot_as_of}</td><td>{e.origin}</td><td>{e.physical_progress_pct ?? 'n/a'}</td><td>{e.original_cost_crore ?? 'n/a'}</td><td>{e.revised_cost_crore ?? 'n/a'}</td><td>{e.expenditure_crore ?? 'n/a'}</td><td>{e.risk_score} {e.risk_band}</td></tr>)}</tbody></table></div></details>}
            <div className="note">Sources: {m.a.sources.map((s) => `${s.type}${s.detail ? ` (${s.detail})` : ''}`).join('; ')} · intent: {m.a.intent}</div>
          </div>))}
      </div>
      <ErrorBox error={err} />
      <form className="filters" style={{ marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); ask(q) }}>
        <input style={{ flex: 1, minWidth: 260 }} aria-label="Ask PRAGATI Copilot" placeholder="Ask about projects, risk, cost, delays…" value={q} onChange={(e) => setQ(e.target.value)} maxLength={1000} />
        <button disabled={busy}>{busy ? 'Thinking…' : 'Ask'}</button></form>
    </Page>
  )
}
