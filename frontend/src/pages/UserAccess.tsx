/**
 * Admin-only Users/Access screen.
 * Maps Clerk user IDs to Waterford rep records.
 * Uses the central apiRequest client (Clerk token injected by getClerkToken()).
 */
import { useState, useEffect } from 'react'
import { crmApi, apiRequest, type Rep } from '../lib/api'
import { Loader2, Plus, Trash2, CheckCircle } from 'lucide-react'

interface Mapping {
  id: string
  clerk_user_id: string
  clerk_email: string
  rep_code: string
  full_name: string
  is_active: boolean
}

export function UserAccessPage() {
  const [mappings, setMappings] = useState<Mapping[]>([])
  const [reps, setReps] = useState<Rep[]>([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ clerk_user_id: '', clerk_email: '', rep_id: '' })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  function loadMappings() {
    return apiRequest<{ mappings: Mapping[] }>('/api/auth/user-mappings')
      .then(d => setMappings(d.mappings || []))
      .catch(e => setMsg(`Error loading mappings: ${e.message}`))
  }

  useEffect(() => {
    Promise.all([loadMappings(), crmApi.reps()])
      .then(([, r]) => setReps(r.reps))
      .finally(() => setLoading(false))
  }, [])

  async function saveMapping() {
    if (!form.clerk_user_id || !form.rep_id) {
      setMsg('Clerk User ID and rep selection are required.')
      return
    }
    setSaving(true); setMsg('')
    try {
      await apiRequest('/api/auth/user-mappings', {
        method: 'POST',
        body: JSON.stringify(form),
      })
      setMsg('Mapping saved.')
      setForm({ clerk_user_id: '', clerk_email: '', rep_id: '' })
      loadMappings()
    } catch (e: any) {
      setMsg(`Error: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  async function removeMapping(clerk_user_id: string) {
    if (!confirm(`Deactivate mapping for ${clerk_user_id}?`)) return
    await apiRequest(`/api/auth/user-mappings/${encodeURIComponent(clerk_user_id)}`, { method: 'DELETE' })
    loadMappings()
  }

  const inp = "w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#1F3864]"

  if (loading) return (
    <div className="flex items-center gap-2 p-8 text-gray-400 text-sm">
      <Loader2 size={16} className="animate-spin" /> Loading…
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[#1F3864]">Users &amp; Access</h1>
        <p className="text-gray-500 text-sm mt-1">
          Map Clerk-authenticated users to Waterford rep records.
          After mapping, a rep's My Day loads automatically when they log in.
          Roles (REP / MANAGER / ADMIN) are set in the Clerk dashboard.
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-5 space-y-4">
        <h2 className="text-sm font-semibold text-gray-700">Add / Update Mapping</h2>
        <div className="grid md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Clerk User ID <span className="text-gray-400">(Clerk dashboard → Users)</span>
            </label>
            <input value={form.clerk_user_id}
              onChange={e => setForm(f => ({ ...f, clerk_user_id: e.target.value }))}
              placeholder="user_2abc…" className={inp} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Email (for reference)</label>
            <input value={form.clerk_email}
              onChange={e => setForm(f => ({ ...f, clerk_email: e.target.value }))}
              placeholder="koliswa@waterfordestate.co.za" className={inp} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Waterford Rep</label>
            <select value={form.rep_id}
              onChange={e => setForm(f => ({ ...f, rep_id: e.target.value }))}
              className={inp}>
              <option value="">— select rep —</option>
              {reps.map(r => <option key={r.id} value={r.id}>{r.full_name} ({r.rep_code})</option>)}
            </select>
          </div>
        </div>
        {msg && (
          <p className={`text-sm ${msg.startsWith('Error') ? 'text-red-600' : 'text-emerald-600'}`}>
            {!msg.startsWith('Error') && <CheckCircle size={12} className="inline mr-1" />}
            {msg}
          </p>
        )}
        <button onClick={saveMapping} disabled={saving}
          className="flex items-center gap-2 bg-[#1F3864] text-white text-sm px-4 py-2 rounded-lg hover:bg-[#2E5395] disabled:opacity-60 transition-colors">
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          Save mapping
        </button>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Current Mappings</h2>
        {mappings.length === 0
          ? <p className="text-sm text-gray-400">No mappings yet.</p>
          : <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                  <tr>
                    <th className="px-4 py-2 text-left">Clerk User ID</th>
                    <th className="px-4 py-2 text-left">Email</th>
                    <th className="px-4 py-2 text-left">Rep</th>
                    <th className="px-4 py-2 text-left">Status</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {mappings.map(m => (
                    <tr key={m.id}>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-700">{m.clerk_user_id}</td>
                      <td className="px-4 py-2.5 text-gray-600">{m.clerk_email || '—'}</td>
                      <td className="px-4 py-2.5 font-medium text-gray-800">
                        {m.full_name} <span className="text-gray-400 text-xs">({m.rep_code})</span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${m.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
                          {m.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-2.5">
                        {m.is_active && (
                          <button onClick={() => removeMapping(m.clerk_user_id)}
                            className="text-gray-400 hover:text-red-500 transition-colors">
                            <Trash2 size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
        }
      </div>

      <div className="text-xs text-gray-400 space-y-1 border-t border-gray-100 pt-4">
        <p>Find Clerk User ID: <a href="https://dashboard.clerk.com" target="_blank" rel="noopener noreferrer" className="underline">clerk.com</a> → Users → copy the ID starting with <code className="bg-gray-100 px-1 rounded">user_</code></p>
        <p>Set roles in Clerk: Users → select user → Public Metadata → set <code className="bg-gray-100 px-1 rounded">{`{"role":"REP"}`}</code>, <code className="bg-gray-100 px-1 rounded">{`{"role":"MANAGER"}`}</code>, or <code className="bg-gray-100 px-1 rounded">{`{"role":"ADMIN"}`}</code></p>
      </div>
    </div>
  )
}
