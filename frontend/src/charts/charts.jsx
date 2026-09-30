import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BAND_COLORS } from '../utils/format'

const H = 260
export const BarBox = ({ data, x, y, color = '#3f7cc4', fmt, horizontal }) => (
  <ResponsiveContainer width="100%" height={H}>
    <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={{ left: horizontal ? 60 : 0 }}>
      <CartesianGrid strokeDasharray="3 3" />
      {horizontal ? <><XAxis type="number" /><YAxis type="category" dataKey={x} width={130} tick={{ fontSize: 11 }} /></> : <><XAxis dataKey={x} tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={60} /><YAxis /></>}
      <Tooltip formatter={fmt} /><Bar dataKey={y} fill={color} />
    </BarChart>
  </ResponsiveContainer>
)

export const RiskDistChart = ({ data }) => (
  <ResponsiveContainer width="100%" height={H}>
    <BarChart data={data}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="bucket" /><YAxis allowDecimals={false} /><Tooltip />
      <Bar dataKey="count">{data.map((d) => <Cell key={d.bucket} fill={BAND_COLORS[d.bucket]} />)}</Bar></BarChart>
  </ResponsiveContainer>
)

export const LineBox = ({ data, x, lines, domain }) => (
  <ResponsiveContainer width="100%" height={H}>
    <LineChart data={data}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey={x} tick={{ fontSize: 11 }} /><YAxis domain={domain} /><Tooltip /><Legend />
      {lines.map((l) => <Line key={l.key} type="monotone" dataKey={l.key} name={l.name || l.key} stroke={l.color} dot={false} strokeWidth={2} connectNulls={false} />)}</LineChart>
  </ResponsiveContainer>
)
