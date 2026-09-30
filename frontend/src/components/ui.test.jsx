import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { DemoBanner, RiskBadge, Table } from './ui'
import { bandOf, fmtCrore, fmtPct } from '../utils/format'

test('band thresholds match the risk spec', () => {
  expect([0, 30, 31, 60, 61, 80, 81, 100].map(bandOf)).toEqual(['STABLE', 'STABLE', 'WATCH', 'WATCH', 'WARNING', 'WARNING', 'CRITICAL', 'CRITICAL'])
})
test('formatters never fabricate values for null', () => { expect(fmtCrore(null)).toBe('n/a'); expect(fmtPct(undefined)).toBe('n/a') })
test('demo banner only shows for synthetic data', () => {
  const { rerender } = render(<DemoBanner show={false} />); expect(screen.queryByText(/Demo Data/)).toBeNull()
  rerender(<DemoBanner show />); expect(screen.getByText(/Demo Data/)).toBeInTheDocument()
})
test('risk badge shows band and score', () => { render(<RiskBadge band="CRITICAL" score={87.4} />); expect(screen.getByText(/CRITICAL · 87/)).toBeInTheDocument() })
test('table renders empty state and rows', () => {
  const cols = [{ key: 'a', label: 'A' }]
  const { rerender } = render(<Table columns={cols} rows={[]} empty="nothing" />); expect(screen.getByText('nothing')).toBeInTheDocument()
  rerender(<MemoryRouter><Table columns={cols} rows={[{ a: 'x1' }]} /></MemoryRouter>); expect(screen.getByText('x1')).toBeInTheDocument()
})
