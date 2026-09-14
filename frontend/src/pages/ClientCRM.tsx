/**
 * Client 360 with CRM layer — Sprint 5
 * Shows commercial performance + relationship context + action panel.
 * Log Visit modal is embedded.
 */
import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Loader2, Plus, CheckCircle, AlertCircle, Calendar, Download } from 'lucide-react'
import { commercialApi, crmApi, apiRequest, FOLLOW_UP_TYPES, SUPPORT_TYPES, SENTIMENTS, type Rep } from '../lib/api'

function fmtR(n:number|null|undefined){if(!n)return'R0';return`R${Math.round(n).toLocaleString('en-ZA')}`}
function fmt(n:number|null|undefined){return Math.round(n||0).toLocaleString('en-ZA')}
function fmtDate(d:string|null|undefined){if(!d)return'—';return new Date(d).toLocaleDateString('en-ZA',{day:'numeric',month:'short',year:'numeric'})}

const SENTIMENT_CLASSES:Record<string,string>={POSITIVE:'bg-emerald-100 text-emerald-700 border-emerald-200',NEUTRAL:'bg-gray-100 text-gray-600 border-gray-200',NEGATIVE:'bg-amber-100 text-amber-800 border-amber-200',AT_RISK:'bg-red-100 text-red-700 border-red-200'}

// ── Log Visit Modal ──────────────────────────────────────────────────────────
function LogVisitModal({clientId, clientName, reps, onClose, onSaved}:
  {clientId:string;clientName:string;reps:Rep[];onClose:()=>void;onSaved:()=>void}) {
  const [isManager, setIsManager] = useState(false)
  const [form, setForm] = useState({
    rep_id: reps[0]?.id || '',
    activity_date: new Date().toISOString().split('T')[0],
    contact_person: '', outcome: '', general_notes: '',
    overall_sentiment: 'POSITIVE',
    has_followup: false,
    fu_type: 'Follow-up', fu_due: '', fu_note: '',
    has_support: false,
    sr_type: 'Samples', sr_note: '', sr_due: '',
  })
  const [saving, setSaving] = useState(false)
  const [calLink, setCalLink] = useState<string|null>(null)

  // Resolve identity on mount
  useState(() => {
    apiRequest<{rep: {id: string; full_name: string} | null; role: string}>('/api/auth/me')
      .then(me => {
        const role = me.role || 'REP'
        setIsManager(role === 'MANAGER' || role === 'ADMIN')
        if (me.rep) {
          setForm(f => ({ ...f, rep_id: me.rep!.id }))
        }
      })
      .catch(() => {})
  })

  async function save() {
    setSaving(true)
    try {
      const body: Record<string,unknown> = {
        client_id: clientId, rep_id: form.rep_id,
        activity_date: form.activity_date, activity_type: 'VISIT',
        contact_person: form.contact_person || undefined,
        outcome: form.outcome || undefined,
        general_notes: form.general_notes,
        overall_sentiment: form.overall_sentiment,
        created_by: 'webapp',
      }
      if (form.has_followup && form.fu_note) {
        body.follow_up = {
          follow_up_type: form.fu_type, due_date: form.fu_due || undefined,
          description: form.fu_note, priority: 'MEDIUM',
          assigned_to_rep_id: form.rep_id,
        }
      }
      if (form.has_support && form.sr_type) {
        body.support_request = {
          support_type: form.sr_type, notes: form.sr_note,
          required_by: form.sr_due || undefined,
        }
      }
      const result = await crmApi.createActivity(body)
      if (result.follow_up_id && form.fu_note && form.fu_due) {
        setCalLink(crmApi.calendarEventUrl(clientName, form.fu_type, form.fu_due, form.fu_note, result.follow_up_id))
      }
      onSaved()
      if (!calLink) onClose()
    } catch(e:any) { alert(`Error: ${e.message}`) }
    finally { setSaving(false) }
  }

  function Field({label,children}:{label:string;children:React.ReactNode}){
    return <div><label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>{children}</div>
  }
  const inp = "w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#1F3864]"

  if (calLink) return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl p-6 max-w-sm w-full space-y-4">
        <CheckCircle size={32} className="text-emerald-500 mx-auto" />
        <h2 className="text-center font-semibold text-gray-800">Visit logged</h2>
        <p className="text-sm text-center text-gray-600">Would you like to add the follow-up to your calendar?</p>
        <a href={calLink} download className="flex items-center justify-center gap-2 w-full bg-[#1F3864] text-white text-sm py-2.5 rounded-lg hover:bg-[#2E5395] transition-colors">
          <Download size={14} /> Download .ics (Add to Outlook)
        </a>
        <p className="text-[10px] text-gray-400 text-center">Your Waterford Sales Intelligence app remains the system of record. The .ics file adds an entry to Outlook or any calendar.</p>
        <button onClick={onClose} className="w-full text-sm text-gray-500 py-2 hover:text-gray-700">Done</button>
      </div>
    </div>
  )

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl p-6 max-w-lg w-full space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-800">Log Visit — {clientName}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg">✕</button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Rep">
            {isManager
              ? <select value={form.rep_id} onChange={e=>setForm(f=>({...f,rep_id:e.target.value}))} className={inp}>
                  {reps.map(r=><option key={r.id} value={r.id}>{r.full_name}</option>)}
                </select>
              : <div className={`${inp} bg-gray-50 text-gray-700`}>
                  {reps.find(r=>r.id===form.rep_id)?.full_name || 'Loading…'}
                </div>
            }
          </Field>
          <Field label="Date">
            <input type="date" value={form.activity_date}
              onChange={e=>setForm(f=>({...f,activity_date:e.target.value}))} className={inp} />
          </Field>
        </div>

        <Field label="Contact (optional)">
          <input value={form.contact_person} onChange={e=>setForm(f=>({...f,contact_person:e.target.value}))}
            placeholder="Person spoken to" className={inp} />
        </Field>

        <Field label="Outcome">
          <div className="flex gap-2">
            {SENTIMENTS.map(s=>(
              <button key={s.value}
                className={`flex-1 text-xs py-2 rounded-lg border transition-colors
                  ${form.overall_sentiment===s.value
                    ? SENTIMENT_CLASSES[s.value]||'bg-blue-100 text-blue-700 border-blue-200'
                    : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'}`}
                onClick={()=>setForm(f=>({...f,overall_sentiment:s.value}))}>
                {s.label}
              </button>
            ))}
          </div>
        </Field>

        <Field label="Notes">
          <textarea value={form.general_notes} onChange={e=>setForm(f=>({...f,general_notes:e.target.value}))}
            rows={3} placeholder="What happened? Key observations…" className={`${inp} resize-none`} />
        </Field>

        {/* Optional next step */}
        <div className="border-t border-gray-100 pt-3">
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input type="checkbox" checked={form.has_followup}
              onChange={e=>setForm(f=>({...f,has_followup:e.target.checked}))} className="rounded" />
            Add a next action
          </label>
          {form.has_followup && (
            <div className="mt-3 space-y-3 pl-5">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Action type">
                  <select value={form.fu_type} onChange={e=>setForm(f=>({...f,fu_type:e.target.value}))} className={inp}>
                    {FOLLOW_UP_TYPES.map(t=><option key={t}>{t}</option>)}
                  </select>
                </Field>
                <Field label="Due date">
                  <input type="date" value={form.fu_due} onChange={e=>setForm(f=>({...f,fu_due:e.target.value}))} className={inp} />
                </Field>
              </div>
              <Field label="Note">
                <input value={form.fu_note} onChange={e=>setForm(f=>({...f,fu_note:e.target.value}))}
                  placeholder="Brief description" className={inp} />
              </Field>
            </div>
          )}
        </div>

        {/* Optional support request */}
        <div className="border-t border-gray-100 pt-3">
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input type="checkbox" checked={form.has_support}
              onChange={e=>setForm(f=>({...f,has_support:e.target.checked}))} className="rounded" />
            Request support
          </label>
          {form.has_support && (
            <div className="mt-3 space-y-3 pl-5">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Support type">
                  <select value={form.sr_type} onChange={e=>setForm(f=>({...f,sr_type:e.target.value}))} className={inp}>
                    {SUPPORT_TYPES.map(t=><option key={t}>{t}</option>)}
                  </select>
                </Field>
                <Field label="Required by">
                  <input type="date" value={form.sr_due} onChange={e=>setForm(f=>({...f,sr_due:e.target.value}))} className={inp} />
                </Field>
              </div>
              <Field label="Notes">
                <input value={form.sr_note} onChange={e=>setForm(f=>({...f,sr_note:e.target.value}))}
                  placeholder="What is needed?" className={inp} />
              </Field>
            </div>
          )}
        </div>

        <button onClick={save} disabled={saving}
          className="w-full bg-[#1F3864] text-white text-sm py-2.5 rounded-lg hover:bg-[#2E5395] transition-colors disabled:opacity-60 flex items-center justify-center gap-2">
          {saving && <Loader2 size={14} className="animate-spin" />}
          Save visit
        </button>
      </div>
    </div>
  )
}

// ── Main Client CRM Page ─────────────────────────────────────────────────────
export function ClientCRMPage() {
  const { clientId } = useParams<{clientId:string}>()
  const nav = useNavigate()
  const [perf, setPerf] = useState<any>(null)
  const [timeline, setTimeline] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  const [gap, setGap] = useState<any>(null)
  const [reps, setReps] = useState<Rep[]>([])
  const [loading, setLoading] = useState(true)
  const [showLog, setShowLog] = useState(false)

  function reload() {
    if (!clientId) return
    Promise.all([
      commercialApi.client360(clientId),
      crmApi.clientTimeline(clientId),
      crmApi.accountHealth(clientId),
      crmApi.rangeGap(clientId),
      crmApi.reps(),
    ]).then(([p,t,h,g,r]) => {
      setPerf(p); setTimeline(t); setHealth(h); setGap(g); setReps(r.reps)
    }).finally(() => setLoading(false))
  }
  useEffect(reload, [clientId])

  if (loading) return <div className="flex items-center gap-2 p-8 text-gray-400 text-sm"><Loader2 size={16} className="animate-spin"/>Loading…</div>
  if (!perf) return <div className="p-8 text-red-500 text-sm">Client not found</div>

  const client = perf.client || {}
  const pf = perf.performance || {}
  const lv = timeline?.last_visit

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button onClick={() => nav(-1)} className="text-xs text-gray-400 hover:text-gray-600 mb-1">← Back</button>
          <h1 className="text-xl font-bold text-[#1F3864]">{client.canonical_name}</h1>
          <p className="text-gray-500 text-sm">{client.territory_name} · {client.outlet_type}</p>
        </div>
        <button onClick={() => setShowLog(true)}
          className="flex items-center gap-2 bg-[#1F3864] text-white text-sm px-4 py-2 rounded-lg hover:bg-[#2E5395] transition-colors">
          <Plus size={14} /> Log Visit
        </button>
      </div>

      {/* Health flags */}
      {health?.flags?.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {health.flags.map((f:any,i:number) => (
            <div key={i} className="text-xs bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              <p className="font-medium text-amber-800">{f.label}</p>
              <p className="text-amber-700">{f.detail}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">

        {/* Commercial performance */}
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Commercial Performance</h2>
          <div className="grid grid-cols-2 gap-3">
            {[
              ['FY2027 YTD bottles', fmt(pf.fy27_bottles)],
              ['FY2026 equiv bottles', fmt(pf.fy26_bottles)],
              ['YoY %', pf.yoy_pct!=null ? `${pf.yoy_pct > 0 ? '+' : ''}${pf.yoy_pct}%` : '—'],
              ['Confirmed revenue', fmtR(pf.fy27_rv_confirmed)],
            ].map(([l,v])=>(
              <div key={String(l)} className="bg-gray-50 rounded p-2">
                <p className="text-[10px] text-gray-400">{l}</p>
                <p className="text-sm font-semibold text-gray-800">{v}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 space-y-1">
            {(perf.product_mix||[]).slice(0,4).map((p:any,i:number)=>(
              <div key={i} className="flex justify-between text-xs text-gray-600">
                <span className="truncate">{p.product_name}</span>
                <span className="font-medium ml-2">{fmt(p.bottles)} btls</span>
              </div>
            ))}
          </div>
        </div>

        {/* Relationship panel */}
        <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Relationship</h2>
          {lv ? (
            <div className={`rounded-lg border p-3 ${SENTIMENT_CLASSES[lv.overall_sentiment||'']||'bg-gray-50 border-gray-200'}`}>
              <p className="text-[10px] font-medium uppercase tracking-wide">{fmtDate(lv.activity_date)} · {lv.rep_name}</p>
              <p className="text-sm mt-0.5">{lv.general_notes}</p>
            </div>
          ) : (
            <div className="bg-amber-50 border border-amber-100 rounded-lg p-3">
              <p className="text-amber-700 text-sm">No visits recorded yet</p>
            </div>
          )}

          {/* Open follow-ups */}
          {timeline?.follow_ups?.filter((f:any)=>f.status==='OPEN').slice(0,3).map((f:any,i:number)=>(
            <div key={i} className="flex items-start gap-2 text-sm">
              <Calendar size={13} className="text-[#1F3864] flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-gray-800">{f.follow_up_type} — due {fmtDate(f.due_date)}</p>
                <p className="text-xs text-gray-500">{f.description}</p>
              </div>
            </div>
          ))}

          {/* Open support requests */}
          {timeline?.support_requests?.filter((s:any)=>s.status==='REQUESTED').slice(0,2).map((s:any,i:number)=>(
            <div key={i} className="flex items-start gap-2 text-sm">
              <AlertCircle size={13} className="text-amber-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-gray-800">{s.support_type}</p>
                <p className="text-xs text-gray-500">{s.notes}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Activity timeline */}
      {timeline?.activities?.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg">
          <h2 className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide border-b border-gray-100">Activity Timeline</h2>
          <div className="divide-y divide-gray-50">
            {timeline.activities.map((a:any,i:number)=>(
              <div key={i} className="px-4 py-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-gray-500">{fmtDate(a.activity_date)}</span>
                  <span className="text-[10px] font-medium bg-gray-100 text-gray-600 px-1.5 rounded">{a.activity_type}</span>
                  {a.overall_sentiment && (
                    <span className={`text-[10px] font-medium px-1.5 rounded ${SENTIMENT_CLASSES[a.overall_sentiment]||''}`}>
                      {a.overall_sentiment.charAt(0)+a.overall_sentiment.slice(1).toLowerCase().replace(/_/,' ')}
                    </span>
                  )}
                  <span className="text-xs text-gray-500 ml-auto">{a.rep_name}</span>
                </div>
                {a.contact_person && <p className="text-xs text-gray-400">Contact: {a.contact_person}</p>}
                <p className="text-sm text-gray-700">{a.general_notes}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Range gap */}
      {gap && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
            Product Range ({gap.currently_buying.length} buying / {gap.gap_count} not buying)
          </h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <p className="text-[10px] font-semibold text-emerald-700 uppercase tracking-wide mb-2">Currently buying</p>
              <div className="space-y-1">
                {gap.currently_buying.slice(0,8).map((p:any,i:number)=>(
                  <div key={i} className="flex justify-between text-xs">
                    <span className="text-gray-700">{p.product_name} {p.bottle_size_ml!==750&&`${p.bottle_size_ml}ml`}</span>
                    <span className="text-gray-500">{fmt(p.total_bottles)} btls</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="text-[10px] font-semibold text-amber-700 uppercase tracking-wide mb-2">Not currently buying</p>
              <div className="space-y-1">
                {gap.not_currently_buying.slice(0,8).map((p:any,i:number)=>(
                  <div key={i} className="flex justify-between text-xs">
                    <span className="text-gray-500">{p.product_name} {p.bottle_size_ml!==750&&`${p.bottle_size_ml}ml`}</span>
                    <span className="text-[10px] text-gray-400">{p.sku_code}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {showLog && (
        <LogVisitModal
          clientId={clientId!} clientName={client.canonical_name} reps={reps}
          onClose={() => setShowLog(false)}
          onSaved={reload}
        />
      )}
    </div>
  )
}
