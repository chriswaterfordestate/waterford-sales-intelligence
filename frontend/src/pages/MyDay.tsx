import { apiRequest } from '../lib/api'
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, AlertCircle, Calendar, Loader2, TrendingDown } from 'lucide-react'

function fmtDate(d: string | null | undefined) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-ZA', { day: 'numeric', month: 'short' })
}
const SB: Record<string, string> = {
  POSITIVE: 'bg-emerald-100 text-emerald-700', NEUTRAL: 'bg-gray-100 text-gray-600',
  NEGATIVE: 'bg-amber-100 text-amber-800', AT_RISK: 'bg-red-100 text-red-700',
}
const SL: Record<string, string> = { POSITIVE: 'Positive', NEUTRAL: 'Neutral', NEGATIVE: 'Concern', AT_RISK: 'At Risk' }

export function MyDayPage() {
  const [data, setData] = useState<any>(null)
  const [repName, setRepName] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const nav = useNavigate()

  useEffect(() => {
    // Identity derived server-side: /api/auth/me → user_rep_mappings
    // Token obtained from Clerk session (central api.ts getClerkToken).
    // No rep_id in the URL — REP cannot choose their own identity.
    apiRequest<{rep: {full_name: string} | null}>('/api/auth/me')
      .then(me => {
        if (!me.rep) {
          setError('Your account is not mapped to a rep. Ask an admin to set this up via Users / Access.')
          setLoading(false)
          return
        }
        setRepName(me.rep.full_name || '')
        return apiRequest<any>('/api/crm/my-day')
      })
      .then(d => { if (d) setData(d) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex items-center gap-2 p-8 text-gray-400 text-sm">
      <Loader2 size={16} className="animate-spin" /> Loading My Day…
    </div>
  )

  if (error) return (
    <div className="p-8 space-y-2">
      <p className="text-amber-800 text-sm font-medium">My Day unavailable</p>
      <p className="text-amber-700 text-sm">{error}</p>
      <p className="text-gray-500 text-xs">
        Ask an admin to map your login via{' '}
        <button onClick={() => nav('/users')} className="underline">Users / Access</button>.
      </p>
    </div>
  )

  const overdue = data?.overdue || []
  const dueToday = data?.due_today || []
  const upcoming = data?.upcoming || []
  const recent = data?.recent_activity || []
  const attention = data?.accounts_needing_attention || []
  const opps = data?.opportunities || []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#1F3864]">My Day{repName ? ` — ${repName}` : ''}</h1>
        <p className="text-gray-500 text-sm">
          {data?.as_of ? new Date(data.as_of).toLocaleDateString('en-ZA', { weekday: 'long', day: 'numeric', month: 'long' }) : ''}
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        {[
          { label: 'Overdue', count: overdue.length, colour: overdue.length > 0 ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-500' },
          { label: 'Due today', count: dueToday.length, colour: dueToday.length > 0 ? 'bg-amber-100 text-amber-800' : 'bg-gray-100 text-gray-500' },
          { label: 'Next 7 days', count: upcoming.length, colour: 'bg-blue-100 text-blue-800' },
        ].map(k => (
          <div key={k.label} className={`rounded-lg px-4 py-3 text-center ${k.colour}`}>
            <p className="text-2xl font-bold">{k.count}</p>
            <p className="text-xs font-medium mt-0.5">{k.label}</p>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
            <AlertCircle size={14} className="text-red-500" />
            <h2 className="text-sm font-semibold text-gray-700">Requires action</h2>
          </div>
          <div className="divide-y divide-gray-50 max-h-72 overflow-y-auto">
            {[...overdue.map((x: any) => ({ ...x, _t: 'o' })), ...dueToday.map((x: any) => ({ ...x, _t: 'd' }))].map((a: any, i: number) => (
              <button key={i} onClick={() => nav(`/clients/${a.client_id}`)} className="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{a.follow_up_type}</p>
                    <p className="text-sm font-medium text-gray-800 truncate">{a.client_name}</p>
                    <p className="text-xs text-gray-500 truncate">{a.description}</p>
                  </div>
                  <div className="flex-shrink-0 text-right">
                    {a._t === 'o'
                      ? <span className="text-[10px] font-medium bg-red-100 text-red-700 px-1.5 py-0.5 rounded">{a.days_overdue}d overdue</span>
                      : <span className="text-[10px] font-medium bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">Today</span>}
                    <p className="text-[10px] text-gray-400 mt-0.5">{fmtDate(a.due_date)}</p>
                  </div>
                </div>
              </button>
            ))}
            {overdue.length === 0 && dueToday.length === 0 && (
              <div className="px-4 py-6 text-center text-gray-400 text-sm">
                <CheckCircle size={18} className="mx-auto mb-1 text-emerald-400" />
                No overdue or due-today actions
              </div>
            )}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
            <TrendingDown size={14} className="text-amber-500" />
            <h2 className="text-sm font-semibold text-gray-700">Accounts needing attention</h2>
          </div>
          <div className="divide-y divide-gray-50 max-h-72 overflow-y-auto">
            {attention.map((a: any, i: number) => (
              <button key={i} onClick={() => nav(`/clients/${a.client_id}`)} className="w-full text-left px-4 py-3 hover:bg-gray-50">
                <div className="flex items-center justify-between">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{a.canonical_name}</p>
                    <div className="flex gap-3 text-[10px] text-gray-500 mt-0.5">
                      {a.days_since_order && <span>Last order: {a.days_since_order}d ago</span>}
                      {!a.days_since_visit
                        ? <span className="text-amber-600">No visit recorded</span>
                        : <span>Last visit: {a.days_since_visit}d ago</span>}
                    </div>
                  </div>
                  <AlertCircle size={14} className="text-amber-500 flex-shrink-0" />
                </div>
              </button>
            ))}
            {attention.length === 0 && <p className="px-4 py-6 text-center text-gray-400 text-sm">All accounts on track</p>}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
            <Calendar size={14} className="text-[#1F3864]" />
            <h2 className="text-sm font-semibold text-gray-700">Next 7 days</h2>
          </div>
          <div className="divide-y divide-gray-50 max-h-56 overflow-y-auto">
            {upcoming.map((u: any, i: number) => (
              <button key={i} onClick={() => nav(`/clients/${u.client_id}`)} className="w-full text-left px-4 py-3 hover:bg-gray-50">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs text-gray-500">{u.follow_up_type}</p>
                    <p className="text-sm font-medium text-gray-800">{u.client_name}</p>
                  </div>
                  <span className="text-xs text-gray-500">{fmtDate(u.due_date)}</span>
                </div>
              </button>
            ))}
            {upcoming.length === 0 && <p className="px-4 py-4 text-sm text-gray-400 text-center">Nothing scheduled</p>}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700">Recent activity (14 days)</h2>
          </div>
          <div className="divide-y divide-gray-50 max-h-56 overflow-y-auto">
            {recent.map((r: any, i: number) => (
              <button key={i} onClick={() => nav(`/clients/${r.client_id}`)} className="w-full text-left px-4 py-3 hover:bg-gray-50">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-gray-800 truncate">{r.client_name}</p>
                      {r.overall_sentiment && (
                        <span className={`text-[10px] px-1.5 rounded ${SB[r.overall_sentiment] || ''}`}>
                          {SL[r.overall_sentiment] || r.overall_sentiment}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 truncate">{r.general_notes}</p>
                  </div>
                  <span className="text-xs text-gray-400 flex-shrink-0">{fmtDate(r.activity_date)}</span>
                </div>
              </button>
            ))}
            {recent.length === 0 && <p className="px-4 py-4 text-sm text-gray-400 text-center">No recent activity</p>}
          </div>
        </div>
      </div>

      {opps.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700">Open opportunities ({opps.length})</h2>
          </div>
          <div className="divide-y divide-gray-50">
            {opps.map((o: any, i: number) => (
              <button key={i} onClick={() => nav(`/clients/${o.client_id}`)}
                className="w-full text-left px-4 py-3 hover:bg-gray-50 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{o.title}</p>
                  <p className="text-xs text-gray-500">{o.client_name}</p>
                </div>
                {o.potential && (
                  <span className={`text-[10px] font-medium px-1.5 rounded ${o.potential === 'HIGH' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                    {o.potential}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
