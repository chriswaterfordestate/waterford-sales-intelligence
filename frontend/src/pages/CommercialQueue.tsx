import { useState, useEffect } from 'react'
import { Search, AlertTriangle, CheckCircle, Loader2 } from 'lucide-react'
import { commercialApi, clientsApi, type CommercialDebtor } from '../lib/api'

function fmtR(n: number | null | undefined) {
  if (!n) return 'R0'
  return `R${Math.round(n).toLocaleString('en-ZA')}`
}
function fmt(n: number | null | undefined) {
  return Math.round(n || 0).toLocaleString('en-ZA')
}

export function CommercialQueuePage() {
  const [debtors, setDebtors] = useState<CommercialDebtor[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<CommercialDebtor | null>(null)
  const [search, setSearch] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [resolving, setResolving] = useState(false)
  const [lastResult, setLastResult] = useState<string | null>(null)
  const [resolved, setResolved] = useState<Set<string>>(new Set())

  function load() {
    return commercialApi.debtorQueue(100)
      .then(d => setDebtors(d.debtors))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  useEffect(() => {
    if (search.length < 2) { setSearchResults([]); return }
    const t = setTimeout(() => {
      clientsApi.search(search, 8).then(r => setSearchResults(r.results))
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  async function resolveToClient(debtorCode: string, _debtorName: string, clientId: string, clientName: string) {
    setResolving(true)
    setLastResult(null)
    try {
      // POST debtor identity + client ID — backend derives all applicable queue rows

      const res = await commercialApi.resolveDebtor(debtorCode, clientId, 'MAP')
      setLastResult(
        `${res.resolved} rows resolved to ${clientName}. ` +
        (res.skipped > 0 ? `${res.skipped} skipped (product unresolved). ` : '') +
        (res.failed > 0 ? `${res.failed} failed.` : '')
      )
      setResolved(prev => new Set([...prev, debtorCode]))
      setSelected(null)
      setSearch('')
      setSearchResults([])
      load()
    } catch (e: any) {
      setLastResult(`Error: ${e.message}`)
    } finally {
      setResolving(false)
    }
  }

  const visible = debtors.filter(d => !resolved.has(d.erp_debtor_code))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#1F3864]">Commercial Client Queue</h1>
        <p className="text-gray-500 text-sm mt-1">
          Unresolved commercial ERP debtors — prioritised by confirmed revenue.
          DTC, export, and internal accounts are excluded.
        </p>
      </div>

      {lastResult && (
        <div className="flex items-start gap-3 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3 text-sm">
          <CheckCircle size={16} className="text-emerald-600 flex-shrink-0 mt-0.5" />
          <span className="text-emerald-800">{lastResult}</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-gray-400 text-sm">
          <Loader2 size={14} className="animate-spin" /> Loading prioritised queue…
        </div>
      ) : (
        <div className="grid md:grid-cols-3 gap-4">

          {/* Debtor list */}
          <div className="md:col-span-2 bg-white border border-gray-200 rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-700">
                {visible.length} commercial debtors to resolve
              </h2>
              <span className="text-xs text-gray-400">Sorted by confirmed revenue</span>
            </div>
            <div className="divide-y divide-gray-50 max-h-[65vh] overflow-y-auto">
              {visible.map(d => (
                <button
                  key={d.erp_debtor_code}
                  className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors
                    ${selected?.erp_debtor_code === d.erp_debtor_code ? 'bg-blue-50 border-l-2 border-[#1F3864]' : ''}`}
                  onClick={() => {
                    setSelected(d)
                    setLastResult(null)
                    setSearch(d.erp_debtor_name.split(' ').slice(0, 3).join(' '))
                  }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 truncate">{d.erp_debtor_name}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{d.erp_debtor_group} · {d.erp_debtor_code}</p>
                      {d.probable_match && (
                        <p className="text-xs text-blue-600 mt-0.5">Possible match: {d.probable_match}</p>
                      )}
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-sm font-semibold text-gray-900">{fmtR(d.total_rv_confirmed)}</p>
                      <p className="text-xs text-gray-500">{fmt(d.total_bottles)} btls</p>
                      <p className="text-[10px] text-gray-400">{d.row_count} rows</p>
                    </div>
                  </div>
                </button>
              ))}
              {visible.length === 0 && (
                <div className="px-4 py-8 text-center text-gray-400 text-sm">
                  <CheckCircle size={24} className="mx-auto mb-2 text-emerald-400" />
                  All commercial debtors resolved
                </div>
              )}
            </div>
          </div>

          {/* Resolution panel */}
          <div className="space-y-3">
            {selected ? (
              <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-4 sticky top-4">
                <div>
                  <h3 className="text-sm font-semibold text-gray-800">{selected.erp_debtor_name}</h3>
                  <p className="text-xs text-gray-500 mt-0.5">{selected.erp_debtor_code} · {selected.erp_debtor_group}</p>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                    {[
                      ['Revenue', fmtR(selected.total_rv_confirmed)],
                      ['Bottles', fmt(selected.total_bottles)],
                      ['Periods', String(selected.period_count)],
                      ['Last period', selected.last_period || '—'],
                    ].map(([label, val]) => (
                      <div key={label} className="bg-gray-50 rounded p-2">
                        <p className="text-gray-400">{label}</p>
                        <p className="font-semibold text-gray-800">{val}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-gray-600 block mb-1.5">
                    Search canonical clients
                  </label>
                  <div className="relative">
                    <Search size={12} className="absolute left-2.5 top-2.5 text-gray-400" />
                    <input
                      type="text"
                      value={search}
                      onChange={e => setSearch(e.target.value)}
                      placeholder="Client name…"
                      className="w-full pl-7 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#1F3864]"
                    />
                  </div>
                  {searchResults.length > 0 && (
                    <div className="mt-1 bg-white border border-gray-200 rounded-lg shadow-sm divide-y divide-gray-50 max-h-64 overflow-y-auto">
                      {searchResults.map(c => (
                        <button
                          key={c.id}
                          onClick={() => resolveToClient(
                            selected.erp_debtor_code,
                            selected.erp_debtor_name,
                            c.id,
                            c.canonical_name
                          )}
                          disabled={resolving}
                          className="w-full text-left px-3 py-2.5 hover:bg-blue-50 text-sm transition-colors"
                        >
                          <p className="font-medium text-gray-800">{c.canonical_name}</p>
                          <p className="text-xs text-gray-400">
                            {c.territory_code} · {c.outlet_type} · {Math.round(c.score)}% match
                          </p>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <button
                  onClick={() => { setSelected(null); setSearch(''); setSearchResults([]) }}
                  className="w-full text-xs py-2 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50"
                >
                  Cancel
                </button>

                {resolving && (
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <Loader2 size={12} className="animate-spin" />
                    Registering alias and retroactively resolving all applicable rows…
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center text-gray-400 text-sm">
                <AlertTriangle size={20} className="mx-auto mb-2 text-gray-300" />
                Select a debtor to resolve
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
