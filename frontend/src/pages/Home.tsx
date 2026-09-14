import { useState, useEffect } from 'react'
import { Package, Users, Loader2, TrendingUp, TrendingDown, Truck } from 'lucide-react'
import { commercialApi, queueApi, type CommercialDashboard } from '../lib/api'

function KPI({ label, value, sub, accent = false, warn = false }:
  { label: string; value: string; sub?: string; accent?: boolean; warn?: boolean }) {
  return (
    <div className={`rounded-lg border p-4 ${accent ? 'bg-[#1F3864] text-white border-[#1F3864]'
      : warn ? 'bg-amber-50 border-amber-200' : 'bg-white border-gray-200'}`}>
      <p className={`text-xs uppercase tracking-wide ${accent ? 'text-blue-200' : warn ? 'text-amber-600' : 'text-gray-500'}`}>{label}</p>
      <p className={`text-2xl font-bold mt-1 ${accent ? 'text-white' : warn ? 'text-amber-900' : 'text-[#1F3864]'}`}>{value}</p>
      {sub && <p className={`text-xs mt-0.5 ${accent ? 'text-blue-300' : warn ? 'text-amber-700' : 'text-gray-400'}`}>{sub}</p>}
    </div>
  )
}

function fmtR(n: number | null | undefined) {
  if (!n) return 'R0'
  return `R${Math.round(n).toLocaleString('en-ZA')}`
}
function fmt(n: number | null | undefined) {
  if (!n) return '0'
  return Math.round(n).toLocaleString('en-ZA')
}
function yoyBadge(pct: number | null | undefined) {
  if (pct == null) return null
  const up = pct >= 0
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded
      ${up ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
      <Icon size={10} />{up ? '+' : ''}{pct}%
    </span>
  )
}

export function HomePage() {
  const [dash, setDash] = useState<CommercialDashboard | null>(null)
  const [queue, setQueue] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      commercialApi.dashboard('FY2027', 'FY2026'),
      queueApi.summary(),
    ]).then(([d, q]) => {
      setDash(d)
      setQueue(q.summary)
    }).catch(e => setErr(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex items-center gap-2 text-gray-500 text-sm p-8">
      <Loader2 size={16} className="animate-spin" /> Loading FY2027 dashboard…
    </div>
  )

  if (err || !dash) return (
    <div className="p-8 text-red-600 text-sm">Error: {err || 'No data'}</div>
  )

  const t = dash.totals
  const si = dash.distributor_sell_in
  const unknownCount = queue.find((s: any) => s.issue_type === 'UNKNOWN_CLIENT')?.count || 0

  // Territory breakdown (DIRECT_SALE rows only, for end-client performance)
  const terrRows = dash.fy27_breakdown.filter(r => r.transaction_type !== 'DISTRIBUTOR_SELL_IN')
  const topProd = dash.product_mix.slice(0, 10)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#1F3864]">FY2027 Commercial Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">
            {dash.ytd_label} vs equivalent {dash.compare_year} period.
            ERP revenue confirmed · Sell-through estimated.
          </p>
        </div>
        {dash.queue.open_items > 0 && (
          <span className="text-xs bg-amber-100 text-amber-800 px-2 py-1 rounded font-medium">
            {dash.queue.open_items.toLocaleString('en-ZA')} pending queue items
          </span>
        )}
      </div>

      {/* Main KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI
          label="Commercial Bottles (FY27 YTD)"
          value={fmt(t.fy27_bottles)}
          sub={`vs ${fmt(t.fy26_bottles)} in FY26`}
          accent
        />
        <KPI
          label="Confirmed ERP Revenue"
          value={fmtR(t.fy27_rv_confirmed)}
          sub={`vs ${fmtR(t.fy26_rv_confirmed)} FY26`}
        />
        <KPI
          label="YoY vs FY26 (same period)"
          value={t.yoy_pct != null ? `${t.yoy_pct > 0 ? '+' : ''}${t.yoy_pct}%` : '—'}
          sub={`${dash.ytd_label}`}
        />
        <KPI
          label="Pending Resolution"
          value={fmt(unknownCount)}
          sub={`${fmt(dash.queue.pending_bottles)} btls on hold`}
          warn={unknownCount > 100}
        />
      </div>

      {/* Distributor sell-in notice (separate from commercial) */}
      <div className="flex items-start gap-3 bg-blue-50 border border-blue-200 rounded-lg px-4 py-3">
        <Truck size={15} className="text-blue-500 flex-shrink-0 mt-0.5" />
        <div className="text-sm">
          <p className="font-medium text-blue-800">
            Distributor sell-in: {fmt(si.bottles)} btls · {fmtR(si.rv_confirmed)} confirmed
          </p>
          <p className="text-blue-600 text-xs mt-0.5">
            Confirmed Waterford revenue from distributor pipeline — shown separately, not in commercial totals.
          </p>
        </div>
      </div>

      {/* Product mix + Territory breakdown */}
      <div className="grid md:grid-cols-2 gap-4">

        {/* Product mix FY2027 YTD */}
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
            <Package size={15} className="text-[#1F3864]" />
            <h2 className="text-sm font-semibold text-gray-700">
              Product Mix — {dash.ytd_label}
            </h2>
          </div>
          <div className="divide-y divide-gray-50">
            {topProd.length === 0 && (
              <p className="px-4 py-3 text-xs text-gray-400">No product data yet</p>
            )}
            {topProd.map((p: any, i: number) => {
              const maxBtls = topProd[0]?.bottles || 1
              const pct = Math.round((p.bottles / maxBtls) * 100)
              return (
                <div key={i} className="px-4 py-2.5">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-[10px] font-mono text-gray-400 w-12 flex-shrink-0">{p.sku_code}</span>
                      <span className="text-sm text-gray-800 truncate">{p.product_name}</span>
                      {p.bottle_size_ml !== 750 && (
                        <span className="text-[10px] text-gray-400">{p.bottle_size_ml}ml</span>
                      )}
                    </div>
                    <span className="text-xs font-semibold text-gray-700 ml-2">{fmt(p.bottles)}</span>
                  </div>
                  <div className="ml-14 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full bg-[#1F3864] rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Territory breakdown */}
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
            <Users size={15} className="text-[#1F3864]" />
            <h2 className="text-sm font-semibold text-gray-700">
              By Territory — {dash.ytd_label}
            </h2>
          </div>
          <div className="divide-y divide-gray-50">
            {terrRows.length === 0 && (
              <p className="px-4 py-3 text-xs text-gray-400">No territory data yet</p>
            )}
            {terrRows.map((r: any, i: number) => {
              const maxBtls = terrRows[0]?.bottles || 1
              const pct = Math.round(((r.bottles || 0) / maxBtls) * 100)
              const tgt = dash.targets.find((tg: any) => tg.territory_code === r.territory_code)
              const ach = (tgt?.target_rv ?? 0) > 0
                ? Math.round((r.rv_confirmed / (tgt!.target_rv ?? 1)) * 100) : null
              return (
                <div key={i} className="px-4 py-2.5">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-gray-800 truncate">
                      {r.territory_name || r.territory_code || 'Unknown'}
                    </span>
                    <div className="flex items-center gap-2 ml-2 flex-shrink-0">
                      {ach != null && (
                        <span className={`text-[10px] font-medium px-1 rounded
                          ${ach >= 100 ? 'bg-emerald-100 text-emerald-700'
                            : ach >= 75 ? 'bg-amber-100 text-amber-700'
                            : 'bg-red-100 text-red-700'}`}>
                          {ach}%
                        </span>
                      )}
                      <span className="text-xs font-semibold text-gray-700">{fmt(r.bottles)} btls</span>
                    </div>
                  </div>
                  <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full bg-[#2E5395] rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* YoY comparison note */}
      <div className="flex items-center gap-2 text-xs text-gray-400 border-t border-gray-100 pt-3">
        <span>
          Comparison: {dash.ytd_label} ({dash.actual_year}) vs same calendar months in {dash.compare_year}.
          Commercial market view only — DIRECT_SALE + DISTRIBUTOR_SELL_THROUGH subject to DC rules.
          Distributor sell-in excluded from these totals.
        </span>
        {yoyBadge(t.yoy_pct)}
      </div>
    </div>
  )
}
