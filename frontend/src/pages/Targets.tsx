import { useState, useEffect } from 'react'
import { reportsApi } from '../lib/api'

interface RepTarget {
  rep_code: string
  rep_name: string
  period_name: string
  calendar_month: number
  calendar_year: number
  target_bottles: number
  target_rv: number
}

interface Actual {
  rep_name: string
  rep_code: string
  period_name: string
  calendar_month: number
  calendar_year: number
  bottles_actual: number
  rv_confirmed: number
  target_bottles: number | null
  target_rv: number | null
  bottles_gap: number | null
  achievement_pct: number | null
}

const PCT_COLOR = (pct: number | null) => {
  if (pct === null) return 'text-gray-400'
  if (pct >= 100) return 'text-green-600 font-semibold'
  if (pct >= 80)  return 'text-amber-600'
  return 'text-red-600'
}

const fmt = (n: number | null, decimals = 0) =>
  n === null ? '—' : n.toLocaleString('en-ZA', { maximumFractionDigits: decimals })

const fmtPct = (n: number | null) =>
  n === null ? '—' : `${n.toFixed(1)}%`

export function TargetsPage() {
  const [data, setData] = useState<{ actuals: Actual[]; targets: RepTarget[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedRep, setSelectedRep] = useState<string>('ALL')

  useEffect(() => {
    const load = async () => {
      try {
        const result = await reportsApi.repPerformance('FY2027', 'FY2027')
        setData(result)
      } catch (e: any) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) return <div className="p-8 text-gray-500">Loading targets…</div>
  if (error)   return <div className="p-8 text-red-600">Error: {error}</div>
  if (!data)   return null

  const reps = ['ALL', ...Array.from(new Set(data.targets.map(t => t.rep_code))).sort()]

  const actuals = selectedRep === 'ALL'
    ? data.actuals
    : data.actuals.filter(a => a.rep_code === selectedRep)

  // Aggregate by month for the selected rep(s)
  type MonthRow = {
    period_name: string; cal_year: number; cal_month: number;
    actual_btls: number; target_btls: number | null;
    gap: number | null; pct: number | null;
  }
  const monthMap = new Map<string, MonthRow>()
  for (const a of actuals) {
    const k = `${a.calendar_year}-${a.calendar_month}`
    const existing = monthMap.get(k)
    if (!existing) {
      monthMap.set(k, {
        period_name: a.period_name,
        cal_year: a.calendar_year,
        cal_month: a.calendar_month,
        actual_btls: Number(a.bottles_actual || 0),
        target_btls: a.target_bottles != null ? Number(a.target_bottles) : null,
        gap: a.bottles_gap != null ? Number(a.bottles_gap) : null,
        pct: a.achievement_pct != null ? Number(a.achievement_pct) : null,
      })
    } else {
      existing.actual_btls += Number(a.bottles_actual || 0)
      if (a.target_bottles != null) {
        existing.target_btls = (existing.target_btls || 0) + Number(a.target_bottles)
      }
    }
  }
  // Recompute gap / pct for aggregated rows
  const months: MonthRow[] = Array.from(monthMap.values())
    .sort((a, b) => a.cal_year - b.cal_year || a.cal_month - b.cal_month)
    .map(m => {
      if (m.target_btls != null && m.target_btls > 0) {
        m.gap = m.actual_btls - m.target_btls
        m.pct = Math.round((m.actual_btls / m.target_btls) * 1000) / 10
      }
      return m
    })

  // YTD totals
  const ytd = months.reduce((acc, m) => {
    acc.actual += m.actual_btls
    if (m.target_btls != null) acc.target += m.target_btls
    return acc
  }, { actual: 0, target: 0 })
  const ytdPct = ytd.target > 0 ? Math.round((ytd.actual / ytd.target) * 1000) / 10 : null

  // Reps with no FY2027 target supplied
  const NO_TARGET_REPS = ['WER001']

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">FY2027 Targets — Actual vs Target</h1>
        <p className="text-sm text-gray-500 mt-1">
          Bottle targets loaded from authoritative rep target PDFs. July 2026 – June 2027.
          Channels (Cellar Door, Events, Exports, Private Clients) and Werner Briedenhann not yet loaded.
        </p>
      </div>

      {/* Rep filter */}
      <div className="mb-4 flex items-center gap-3">
        <label className="text-sm font-medium text-gray-700">Rep / Territory:</label>
        <select
          value={selectedRep}
          onChange={e => setSelectedRep(e.target.value)}
          className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {reps.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        {NO_TARGET_REPS.includes(selectedRep) && (
          <span className="text-amber-600 text-sm">⚠ No FY2027 target data supplied for this rep</span>
        )}
      </div>

      {/* YTD summary cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-lg border p-4">
          <div className="text-xs text-gray-500 mb-1">YTD Actual Bottles</div>
          <div className="text-2xl font-bold text-gray-900">{fmt(ytd.actual)}</div>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="text-xs text-gray-500 mb-1">YTD Target Bottles</div>
          <div className="text-2xl font-bold text-gray-900">
            {ytd.target > 0 ? fmt(ytd.target) : '—'}
          </div>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="text-xs text-gray-500 mb-1">YTD Achievement</div>
          <div className={`text-2xl font-bold ${PCT_COLOR(ytdPct)}`}>
            {fmtPct(ytdPct)}
          </div>
        </div>
      </div>

      {/* Monthly table */}
      <div className="bg-white rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600">Period</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Actual Bottles</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Target Bottles</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Variance</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Achievement %</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {months.map(m => (
              <tr key={`${m.cal_year}-${m.cal_month}`} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-gray-900">{m.period_name}</td>
                <td className="px-4 py-3 text-right text-gray-900">{fmt(m.actual_btls)}</td>
                <td className="px-4 py-3 text-right text-gray-600">
                  {m.target_btls != null ? fmt(m.target_btls) : '—'}
                </td>
                <td className={`px-4 py-3 text-right ${m.gap != null && m.gap < 0 ? 'text-red-600' : 'text-gray-900'}`}>
                  {m.gap != null ? (m.gap >= 0 ? '+' : '') + fmt(m.gap) : '—'}
                </td>
                <td className={`px-4 py-3 text-right ${PCT_COLOR(m.pct)}`}>
                  {fmtPct(m.pct)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-gray-50 border-t font-medium">
            <tr>
              <td className="px-4 py-3 text-gray-900">FY2027 YTD</td>
              <td className="px-4 py-3 text-right text-gray-900">{fmt(ytd.actual)}</td>
              <td className="px-4 py-3 text-right text-gray-600">
                {ytd.target > 0 ? fmt(ytd.target) : '—'}
              </td>
              <td className={`px-4 py-3 text-right ${ytd.target > 0 && ytd.actual - ytd.target < 0 ? 'text-red-600' : 'text-gray-900'}`}>
                {ytd.target > 0 ? (ytd.actual - ytd.target >= 0 ? '+' : '') + fmt(ytd.actual - ytd.target) : '—'}
              </td>
              <td className={`px-4 py-3 text-right ${PCT_COLOR(ytdPct)}`}>
                {fmtPct(ytdPct)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <p className="mt-3 text-xs text-gray-400">
        Target R-values not shown (derived from bottle targets × ASP, not independently set).
        Werner Briedenhann: no FY2027 target supplied — displayed as "Not supplied".
      </p>
    </div>
  )
}
