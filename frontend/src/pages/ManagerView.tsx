import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { crmApi } from '../lib/api'
import { Loader2, Users, AlertCircle, TrendingDown } from 'lucide-react'

function fmtDate(d:string|null|undefined){if(!d)return'—';return new Date(d).toLocaleDateString('en-ZA',{day:'numeric',month:'short'})}

export function ManagerViewPage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const nav = useNavigate()

  useEffect(() => { crmApi.managerView().then(setData).finally(()=>setLoading(false)) }, [])

  if (loading) return <div className="flex items-center gap-2 p-8 text-gray-400 text-sm"><Loader2 size={16} className="animate-spin"/>Loading…</div>

  const team = data?.team_activity || []
  const overdue = data?.all_overdue || []
  const support = data?.support_requests || []
  const concern = data?.accounts_of_concern || []
  const opps = data?.opportunities_by_rep || []

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-[#1F3864]">Manager View</h1>

      {/* Team activity */}
      <div className="bg-white border border-gray-200 rounded-lg">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
          <Users size={14} className="text-[#1F3864]" />
          <h2 className="text-sm font-semibold text-gray-700">Team Activity</h2>
        </div>
        {team.length === 0
          ? <p className="px-4 py-4 text-sm text-gray-400">No activity logged yet</p>
          : <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="px-4 py-2 text-left">Rep</th>
                  <th className="px-4 py-2 text-right">Last 7 days</th>
                  <th className="px-4 py-2 text-right">This month</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {team.map((r:any,i:number)=>(
                  <tr key={i}>
                    <td className="px-4 py-2.5 font-medium text-gray-800">{r.full_name}</td>
                    <td className="px-4 py-2.5 text-right text-gray-700">{r.recent}</td>
                    <td className="px-4 py-2.5 text-right text-gray-700">{r.this_month}</td>
                  </tr>
                ))}
              </tbody>
            </table>
        }
      </div>

      <div className="grid md:grid-cols-2 gap-4">

        {/* All overdue */}
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
            <AlertCircle size={14} className="text-red-500" />
            <h2 className="text-sm font-semibold text-gray-700">Overdue actions ({overdue.length})</h2>
          </div>
          <div className="divide-y divide-gray-50 max-h-64 overflow-y-auto">
            {overdue.map((o:any,i:number)=>(
              <button key={i} onClick={()=>nav(`/clients/${o.client_id}`)}
                className="w-full text-left px-4 py-3 hover:bg-gray-50">
                <div className="flex justify-between items-start">
                  <div className="min-w-0">
                    <p className="text-xs text-gray-500">{o.follow_up_type} · {o.rep_name}</p>
                    <p className="text-sm font-medium text-gray-800 truncate">{o.client_name}</p>
                    <p className="text-xs text-gray-500 truncate">{o.description}</p>
                  </div>
                  <span className="text-[10px] bg-red-100 text-red-700 px-1.5 rounded ml-2 flex-shrink-0">
                    {o.days_overdue}d
                  </span>
                </div>
              </button>
            ))}
            {overdue.length===0 && <p className="px-4 py-4 text-sm text-gray-400 text-center">No overdue actions</p>}
          </div>
        </div>

        {/* Support requests */}
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700">Support requests ({support.length})</h2>
          </div>
          <div className="divide-y divide-gray-50 max-h-64 overflow-y-auto">
            {support.map((s:any,i:number)=>(
              <button key={i} onClick={()=>nav(`/clients/${s.client_id}`)}
                className="w-full text-left px-4 py-3 hover:bg-gray-50">
                <div className="flex justify-between items-start">
                  <div className="min-w-0">
                    <p className="text-xs text-gray-500">{s.support_type} · by {s.requested_by}</p>
                    <p className="text-sm font-medium text-gray-800 truncate">{s.client_name}</p>
                    <p className="text-xs text-gray-500">{s.assigned_to ? `→ ${s.assigned_to}` : 'Unassigned'}</p>
                  </div>
                  <div className="text-right flex-shrink-0 ml-2">
                    <span className={`text-[10px] font-medium px-1.5 rounded ${s.status==='REQUESTED'?'bg-amber-100 text-amber-700':'bg-blue-100 text-blue-700'}`}>
                      {s.status}
                    </span>
                    {s.required_by && <p className="text-[10px] text-gray-400 mt-0.5">By {fmtDate(s.required_by)}</p>}
                  </div>
                </div>
              </button>
            ))}
            {support.length===0 && <p className="px-4 py-4 text-sm text-gray-400 text-center">No outstanding requests</p>}
          </div>
        </div>

        {/* Accounts of concern */}
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
            <TrendingDown size={14} className="text-amber-500" />
            <h2 className="text-sm font-semibold text-gray-700">Accounts declining (&gt;20% YoY)</h2>
          </div>
          <div className="divide-y divide-gray-50 max-h-64 overflow-y-auto">
            {concern.map((c:any,i:number)=>(
              <button key={i} onClick={()=>nav(`/clients/${c.client_id}`)}
                className="w-full text-left px-4 py-3 hover:bg-gray-50">
                <div className="flex justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-800">{c.canonical_name}</p>
                    <p className="text-xs text-gray-500">{c.rep_name || 'Unassigned'}</p>
                  </div>
                  <span className="text-xs font-semibold text-red-600">{c.yoy_pct}%</span>
                </div>
              </button>
            ))}
            {concern.length===0 && <p className="px-4 py-4 text-sm text-gray-400 text-center">No accounts declining &gt;20%</p>}
          </div>
        </div>

        {/* Opportunities summary */}
        <div className="bg-white border border-gray-200 rounded-lg">
          <div className="px-4 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-700">Opportunities by rep</h2>
          </div>
          <div className="p-4">
            {opps.length===0
              ? <p className="text-sm text-gray-400">No opportunities entered yet</p>
              : <table className="w-full text-xs">
                  <thead className="text-gray-500 uppercase">
                    <tr>
                      <th className="text-left pb-2">Rep</th>
                      <th className="text-left pb-2">Status</th>
                      <th className="text-right pb-2">Count</th>
                      <th className="text-right pb-2">Btls</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {opps.map((o:any,i:number)=>(
                      <tr key={i}>
                        <td className="py-1.5 text-gray-700">{o.rep_name}</td>
                        <td className="py-1.5 text-gray-500">{o.status}</td>
                        <td className="py-1.5 text-right text-gray-700">{o.count}</td>
                        <td className="py-1.5 text-right text-gray-500">{Math.round(o.total_bottles||0)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
            }
          </div>
        </div>
      </div>
    </div>
  )
}
