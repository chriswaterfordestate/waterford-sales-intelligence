import { useState, useEffect, useCallback } from 'react'
import { Search, MapPin, Tag, TrendingUp, Loader2, ArrowLeft } from 'lucide-react'
import { clientsApi, type ClientResult } from '../lib/api'

function fmt(n: number | undefined | null) {
  if (!n) return '0'
  return Number(n).toLocaleString('en-ZA')
}

function fmtR(n: number | undefined | null) {
  if (!n) return 'R0'
  return `R${Number(n).toLocaleString('en-ZA')}`
}

// ── Client 360 detail view ────────────────────────────────────────────────────

function Client360({ id, onBack }: { id: string; onBack: () => void }) {
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    clientsApi.get(id)
      .then(d => setData(d as Record<string, unknown>))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return (
    <div className="flex items-center gap-2 text-gray-500 text-sm p-6">
      <Loader2 size={16} className="animate-spin" /> Loading client…
    </div>
  )
  if (!data || (data as any).error) return (
    <div className="p-6 text-gray-500 text-sm">Client not found.</div>
  )

  const client    = (data as any).client || {}
  const aliases   = (data as any).aliases || []
  const reps      = (data as any).current_reps || []
  const periods   = (data as any).period_summary || []
  const totals    = (data as any).totals || {}

  // Build period grid: FY2026, months 1-12
  const periodMap: Record<string, { bottles: number; rv: number; estimated: number }> = {}
  for (const p of periods) {
    if (!p.excluded_from_market_view) {
      const key = `${p.calendar_year}-${String(p.calendar_month).padStart(2,'0')}`
      if (!periodMap[key]) periodMap[key] = { bottles: 0, rv: 0, estimated: 0 }
      periodMap[key].bottles   += Number(p.bottles) || 0
      periodMap[key].rv        += Number(p.rv_confirmed) || 0
      periodMap[key].estimated += Number(p.rv_estimated) || 0
    }
  }
  const MONTHS = ['Jul','Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar','Apr','May','Jun']
  const fyMonths = [
    '2025-07','2025-08','2025-09','2025-10','2025-11','2025-12',
    '2026-01','2026-02','2026-03','2026-04','2026-05','2026-06',
  ]
  const maxBtls = Math.max(1, ...fyMonths.map(k => periodMap[k]?.bottles || 0))

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start gap-3">
        <button onClick={onBack} className="mt-1 text-gray-400 hover:text-gray-600 flex-shrink-0">
          <ArrowLeft size={18} />
        </button>
        <div className="min-w-0">
          <h2 className="text-xl font-bold text-[#1F3864] truncate">{client.canonical_name}</h2>
          {client.trading_name && client.trading_name !== client.canonical_name && (
            <p className="text-sm text-gray-500">t/a {client.trading_name}</p>
          )}
          <div className="flex items-center gap-3 mt-1.5 flex-wrap text-xs text-gray-500">
            {client.territory_name && (
              <span className="flex items-center gap-1"><MapPin size={12} />{client.territory_name}</span>
            )}
            {client.outlet_type && (
              <span className="flex items-center gap-1"><Tag size={12} />{client.outlet_type}</span>
            )}
            {client.tier && (
              <span className="inline-flex items-center px-2 py-0.5 rounded bg-[#DCE6F1] text-[#1F3864] font-medium">
                {client.tier}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Summary totals */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-[#1F3864] rounded-lg p-4 text-white">
          <p className="text-xs text-blue-200 uppercase tracking-wide">FY2026 Bottles</p>
          <p className="text-2xl font-bold mt-1">{fmt(totals.bottles)}</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">FY2026 Revenue</p>
          <p className="text-2xl font-bold text-[#1F3864] mt-1">{fmtR(totals.rv_confirmed)}</p>
          <p className="text-xs text-gray-400 mt-0.5">confirmed ERP</p>
        </div>
      </div>

      {/* Monthly bar chart */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
          FY2026 — Bottles by month (market view)
        </p>
        <div className="flex items-end gap-1.5 h-24">
          {fyMonths.map((key, i) => {
            const btls = periodMap[key]?.bottles || 0
            const h = maxBtls > 0 ? Math.round((btls / maxBtls) * 100) : 0
            return (
              <div key={key} className="flex-1 flex flex-col items-center gap-1" title={`${MONTHS[i]}: ${btls} btls`}>
                <div
                  className="w-full rounded-t transition-all"
                  style={{ height: `${h}%`, minHeight: btls > 0 ? 3 : 0, background: btls > 0 ? '#1F3864' : '#E5E7EB' }}
                />
                <span className="text-[9px] text-gray-400">{MONTHS[i]}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Reps */}
      {reps.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Current Ownership</p>
          {reps.map((r: any, i: number) => (
            <div key={i} className="flex items-center justify-between text-sm py-1">
              <span className="font-medium text-gray-800">{r.full_name}</span>
              <span className="text-xs text-gray-500">
                from {r.effective_from}{r.effective_to ? ` to ${r.effective_to}` : ' (current)'}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Aliases */}
      {aliases.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Source Aliases</p>
          <div className="flex flex-wrap gap-1.5">
            {aliases.map((a: any, i: number) => (
              <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-100 text-gray-700 text-xs rounded-full">
                <span className="text-gray-400 text-[10px]">{a.data_source}</span>
                {a.source_code}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main search page ──────────────────────────────────────────────────────────

export function ClientsPage() {
  const [query, setQuery]         = useState('')
  const [results, setResults]     = useState<ClientResult[]>([])
  const [searched, setSearched]   = useState(false)
  const [loading, setLoading]     = useState(false)
  const [selectedId, setSelected] = useState<string | null>(null)

  const runSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); setSearched(false); return }
    setLoading(true)
    setSearched(true)
    try {
      const r = await clientsApi.search(q, 20)
      setResults(r.results)
    } catch { setResults([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    const t = setTimeout(() => runSearch(query), 300)
    return () => clearTimeout(t)
  }, [query, runSearch])

  if (selectedId) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-[#1F3864] mb-5">Client 360</h1>
        <Client360 id={selectedId} onBack={() => setSelected(null)} />
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-[#1F3864]">Clients</h1>
        <p className="text-gray-500 text-sm mt-1">Search canonical clients across all source aliases and ERP codes.</p>
      </div>

      {/* Search input */}
      <div className="relative max-w-lg">
        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search by name, trading name, or ERP debtor code…"
          className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg text-sm
                     focus:outline-none focus:ring-2 focus:ring-[#2E5395] focus:border-transparent
                     shadow-sm bg-white"
        />
        {loading && (
          <Loader2 size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 animate-spin" />
        )}
      </div>

      {/* Results */}
      {!searched && (
        <div className="text-center py-12 text-gray-400">
          <TrendingUp size={36} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">Start typing to search clients</p>
          <p className="text-xs mt-1">Searches canonical names, trading names, and all source aliases</p>
        </div>
      )}

      {searched && results.length === 0 && !loading && (
        <div className="text-center py-12 text-gray-400">
          <p className="text-sm">No clients matched <strong>"{query}"</strong></p>
          <p className="text-xs mt-1">Try a different name or ERP code</p>
        </div>
      )}

      {results.length > 0 && (
        <div className="grid gap-2">
          {results.map(c => (
            <button
              key={c.id}
              onClick={() => setSelected(c.id)}
              className="w-full text-left bg-white border border-gray-200 rounded-lg px-4 py-3
                         hover:border-[#2E5395] hover:bg-[#F0F5FF] transition-all group"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-gray-900 truncate">{c.canonical_name}</p>
                  {c.trading_name && c.trading_name !== c.canonical_name && (
                    <p className="text-xs text-gray-500 truncate">t/a {c.trading_name}</p>
                  )}
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    {c.territory_code && (
                      <span className="text-xs text-gray-500 flex items-center gap-0.5">
                        <MapPin size={10} />{c.territory_code}
                      </span>
                    )}
                    {c.outlet_type && (
                      <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">{c.outlet_type}</span>
                    )}
                    {c.erp_codes?.slice(0, 3).map((code, i) => (
                      <span key={i} className="text-xs px-1.5 py-0.5 bg-[#DCE6F1] text-[#1F3864] rounded font-mono">{code}</span>
                    ))}
                  </div>
                </div>
                <ChevronRight size={16} className="flex-shrink-0 mt-1 text-gray-300 group-hover:text-[#2E5395] transition-colors" />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// pull in ChevronRight (was missing from imports)
function ChevronRight({ size = 16, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <polyline points="9 18 15 12 9 6" />
    </svg>
  )
}
