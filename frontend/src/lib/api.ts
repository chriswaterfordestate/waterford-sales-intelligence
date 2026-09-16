/**
 * API client — all requests to /api use this module.
 *
 * Auth: Clerk session token obtained via window.Clerk.session.getToken().
 *       In development (no Clerk loaded), sends no token; backend dev-bypass accepts.
 *       Never hard-codes a token string.
 *
 * URL:  All relative paths (/api/...) are automatically prefixed with VITE_API_BASE_URL
 *       so that frontend static-site and backend API service can live on separate Render
 *       origins without per-call manual concatenation.
 *       Pass a full https:// URL to skip prefixing (e.g. the ICS download).
 */

/**
 * Token provider registered by ClerkTokenBridge component (see App.tsx).
 * Uses the official @clerk/clerk-react useAuth() hook, which is the documented
 * way to get the session token inside a React application.
 */
let _clerkGetToken: (() => Promise<string | null>) | null = null

/**
 * Called once from ClerkTokenBridge (mounted inside <ClerkProvider>).
 * Bridges the React auth context into this standalone module.
 */
export function setClerkTokenProvider(fn: () => Promise<string | null>): void {
  _clerkGetToken = fn
}

/** Obtain the current Clerk session JWT for API requests. */
export async function getClerkToken(): Promise<string | null> {
  if (_clerkGetToken) {
    try { return await _clerkGetToken() } catch { /* session not ready */ }
  }
  // Fallback: window.Clerk is also set by @clerk/clerk-react v5 when ClerkProvider
  // initialises the underlying Clerk JS SDK. Used when called outside React (e.g. tests).
  try {
    // @ts-ignore
    const session = window?.Clerk?.session
    if (session) return await session.getToken()
  } catch { /* Clerk not loaded */ }
  return null
}

/** Production API origin from Vite build-time env var. Empty string = same origin (dev proxy). */
export const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

/**
 * Central fetch wrapper.
 * - Prepends API_BASE to relative paths (starting with /).
 * - Attaches Clerk Bearer token when available.
 * - Throws on non-2xx responses.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getClerkToken()

  // Prepend backend origin to relative paths.
  // Full URLs (https://...) pass through unchanged.
  const url = path.startsWith('/') ? `${API_BASE}${path}` : path

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export const api = {
  health: () => apiRequest<{ status: string }>(`/api/health`),
  healthDb: () => apiRequest<{ status: string; tables: number }>(`/api/health/db`),
  healthCoverage: () => apiRequest<{ coverage_summary: Record<string, number> }>('/api/health/coverage'),
}

// ── Sprint 3 API methods ──────────────────────────────────────────────────────

export interface QueueItem {
  queue_item_id: string
  issue_type: string
  severity: string
  source_value: string
  erp_debtor_code: string
  erp_debtor_name: string
  erp_debtor_group: string
  salgrpname: string
  stockunit: string
  bottles: string
  net_rv: string
  finmth: string
  finyear: string
  mapping_error: string
  file_name: string
  source_code: string
}

export interface DebtoRow {
  erp_debtor_code: string
  erp_debtor_name: string
  erp_debtor_group: string
  queue_items: number
  total_bottles: number
  total_rv: number
  first_period: string
  last_period: string
}

export interface ClientResult {
  id: string
  canonical_name: string
  trading_name: string
  outlet_type: string
  tier: string
  territory_code: string
  erp_codes: string[]
  alias_names: string[]
  score: number
}

export const queueApi = {
  summary: () => apiRequest<{ summary: Array<{ issue_type: string; count: number; total_bottles: number }> }>('/api/queue/summary'),
  list: (params?: { issue_type?: string; source_code?: string; debtor_code?: string; page?: number; page_size?: number }) => {
    const qs = new URLSearchParams()
    if (params?.issue_type)   qs.set('issue_type', params.issue_type)
    if (params?.source_code)  qs.set('source_code', params.source_code)
    if (params?.debtor_code)  qs.set('debtor_code', params.debtor_code)
    if (params?.page)         qs.set('page', String(params.page))
    if (params?.page_size)    qs.set('page_size', String(params.page_size))
    return apiRequest<{ total: number; page: number; items: QueueItem[] }>(`/api/queue?${qs}`)
  },
  debtors: (minBottles = 0) =>
    apiRequest<{ debtors: DebtoRow[] }>(`/api/queue/debtors?min_bottles=${minBottles}`),
  resolve: (queueItemIds: string[], clientId: string, sourceCode: string, sourceName: string) =>
    apiRequest<{ resolved: number; skipped: number; failed: number; canonical_client: string }>(`/api/queue/resolve`, {
      method: 'POST',
      body: JSON.stringify({ queue_item_ids: queueItemIds, client_id: clientId, source_code: sourceCode, source_name: sourceName }),
    }),
}

export const clientsApi = {
  search: (q: string, limit = 10) =>
    apiRequest<{ results: ClientResult[]; total_searched: number }>(`/api/clients/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  get: (id: string) =>
    apiRequest<{ client: Record<string, unknown>; aliases: unknown[]; current_reps: unknown[]; period_summary: unknown[]; totals: { bottles: number; rv_confirmed: number } }>(`/api/clients/${id}`),
}

export const reportsApi = {
  marketView: (params?: { year_label?: string; sku_code?: string }) => {
    const qs = new URLSearchParams()
    if (params?.year_label) qs.set('year_label', params.year_label)
    if (params?.sku_code)   qs.set('sku_code', params.sku_code)
    return apiRequest<{ rows: unknown[]; totals: { bottles: number; rv_confirmed: number; rv_estimated: number } }>(`/api/reports/market-view?${qs}`)
  },
  clientLeaderboard: (yearLabel?: string, limit = 25) => {
    const qs = new URLSearchParams()
    if (yearLabel) qs.set('year_label', yearLabel)
    qs.set('limit', String(limit))
    return apiRequest<{ leaderboard: Array<{ client_id: string; canonical_name: string; bottles: number; rv_confirmed: number; territory_name: string; outlet_type: string; periods_active: number }> }>(`/api/reports/client-leaderboard?${qs}`)
  },
  productMix: (yearLabel?: string) => {
    const qs = yearLabel ? `?year_label=${yearLabel}` : ''
    return apiRequest<{ rows: Array<{ product_name: string; sku_code: string; sku_name: string; bottle_size_ml: number; bottles: number; rv_confirmed: number }>; total_bottles: number; total_rv_confirmed: number }>(`/api/reports/product-mix${qs}`)
  },

  repPerformance: (actualYear = 'FY2026', targetYear = 'FY2027') =>
    apiRequest<{
      actual_year: string; target_year: string; note: string;
      actuals: Array<{
        rep_name: string; rep_code: string; period_name: string;
        calendar_month: number; calendar_year: number;
        bottles_actual: number; rv_confirmed: number;
        target_bottles: number | null; target_rv: number | null;
        bottles_gap: number | null; achievement_pct: number | null;
      }>;
      targets: Array<{
        rep_code: string; rep_name: string; period_name: string;
        calendar_month: number; calendar_year: number;
        target_bottles: number; target_rv: number;
      }>;
    }>(`/api/reports/rep-performance?actual_year=${actualYear}&target_year=${targetYear}`),
}

// ── Sprint 4 API methods ──────────────────────────────────────────────────────

export interface CommercialDashboard {
  actual_year: string
  compare_year: string
  ytd_label: string
  ytd_periods: Array<{ calendar_year: number; calendar_month: number; period_name: string }>
  totals: {
    fy27_bottles: number
    fy27_rv_confirmed: number
    fy26_bottles: number
    fy26_rv_confirmed: number
    yoy_pct: number | null
  }
  distributor_sell_in: {
    bottles: number
    rv_confirmed: number
    note: string
  }
  fy27_breakdown: Array<{
    transaction_type: string
    source_code: string
    territory_code: string
    territory_name: string
    transactions: number
    bottles: number
    rv_confirmed: number
  }>
  product_mix: Array<{
    product_name: string
    sku_code: string
    bottle_size_ml: number
    bottles: number
    rv_confirmed: number
  }>
  targets: Array<{ territory_code: string; territory_name: string; target_bottles: number; target_rv: number }>
  queue: { open_items: number; pending_bottles: number }
}

export interface CommercialDebtor {
  erp_debtor_code: string
  erp_debtor_name: string
  erp_debtor_group: string
  row_count: number
  total_bottles: number
  total_rv_confirmed: number
  first_period: string
  last_period: string
  period_count: number
  probable_match: string | null
}

export interface Client360 {
  client: Record<string, unknown>
  ownership: Array<{ full_name: string; rep_code: string; territory_name: string }>
  aliases: Array<{ source_code: string; source_name: string; source_type: string }>
  actual_year: string
  compare_year: string
  ytd_label: string | null
  performance: {
    fy27_bottles: number
    fy27_rv_confirmed: number
    fy27_rv_estimated: number
    fy26_bottles: number
    fy26_rv_confirmed: number
    yoy_pct: number | null
    last_transaction: string
  }
  monthly_trend: Array<{
    year_label: string
    calendar_year: number
    calendar_month: number
    period_name: string
    source_code: string
    bottles: number
    rv_confirmed: number
  }>
  product_mix: Array<{
    year_label: string
    product_name: string
    sku_code: string
    bottle_size_ml: number
    bottles: number
    rv_confirmed: number
  }>
  source_breakdown: Array<{
    year_label: string
    source_code: string
    source_name: string
    transaction_type: string
    bottles: number
    rv_confirmed: number
  }>
}

export interface DebtorResolveResult {
  erp_debtor_code: string
  client_id: string
  action: string
  items_found: number
  resolved: number
  skipped: number
  failed: number
}

export const commercialApi = {
  dashboard: (actualYear = 'FY2027', compareYear = 'FY2026') =>
    apiRequest<CommercialDashboard>(`/api/commercial/dashboard?actual_year=${actualYear}&compare_year=${compareYear}`),
  debtorQueue: (limit = 100) =>
    apiRequest<{ debtors: CommercialDebtor[]; total: number; note: string }>(`/api/commercial/queue/debtors?limit=${limit}`),
  client360: (clientId: string, actualYear = 'FY2027', compareYear = 'FY2026') =>
    apiRequest<Client360>(`/api/commercial/client360/${clientId}?actual_year=${actualYear}&compare_year=${compareYear}`),
  /** Debtor-based resolver — backend derives all applicable queue rows, no browser-side IDs */
  resolveDebtor: (erpDebtorCode: string, clientId: string, action: 'MAP' | 'EXCLUDE' = 'MAP') =>
    apiRequest<DebtorResolveResult>(`/api/commercial/queue/resolve-debtor`, {
      method: 'POST',
      body: JSON.stringify({ erp_debtor_code: erpDebtorCode, client_id: clientId, action }),
    }),
}

export const importsApi = {
  upload: async (file: File, importedBy = 'webapp', sourceOverride?: string): Promise<Record<string, unknown>> => {
    const form = new FormData()
    form.append('file', file)
    form.append('imported_by', importedBy)
    if (sourceOverride) form.append('source_override', sourceOverride)
    const clerkToken = await getClerkToken()
    const res = await fetch(`${API_BASE}/api/imports/upload`, {
      method: 'POST',
      headers: clerkToken ? { Authorization: `Bearer ${clerkToken}` } : {},
      body: form,
    })
    if (!res.ok) throw new Error(`Upload failed: HTTP ${res.status}`)
    return res.json()
  },
  batches: (limit = 20) =>
    apiRequest<{ batches: Array<Record<string, unknown>> }>(`/api/imports/batches?limit=${limit}`),
  coverage: () =>
    apiRequest<{ coverage: Array<Record<string, unknown>> }>('/api/imports/coverage'),
}


// ── Sprint 5 CRM ─────────────────────────────────────────────────────────────

export const FOLLOW_UP_TYPES = [
  "Call","Visit","Tasting","Training","Send Samples","Send Pricing",
  "Follow-up","Event Support","Stock / Allocation","Management Follow-up","Other"
]
export const SUPPORT_TYPES = [
  "Wine Training","Tasting","Samples","POS / Marketing Material","Event Support",
  "Pricing / Deal","Stock / Allocation","Winemaker Visit","Management Support","Other"
]
export const OPP_TYPES = [
  "New Listing","By The Glass","Additional Product","Increased Volume",
  "Event","Training / Activation","New Outlet / Group Expansion","Other"
]
export const SENTIMENTS = [
  {value:"POSITIVE",label:"Positive",colour:"emerald"},
  {value:"NEUTRAL",label:"Neutral",colour:"gray"},
  {value:"NEGATIVE",label:"Concern",colour:"amber"},
  {value:"AT_RISK",label:"At Risk",colour:"red"},
]

export interface Rep { id: string; rep_code: string; full_name: string; role: string }
export interface CRMTimeline {
  last_visit: { activity_date: string; overall_sentiment?: string; general_notes?: string; rep_name: string } | null
  activities: Array<Record<string, unknown>>
  follow_ups: Array<Record<string, unknown>>
  support_requests: Array<Record<string, unknown>>
  opportunities: Array<Record<string, unknown>>
}
export interface AccountHealth {
  client_id: string; last_visit: Record<string,unknown>|null
  last_order_date: string|null; fy27_ytd_bottles: number
  fy26_equiv_bottles: number; yoy_pct: number|null
  open_overdue_actions: number
  flags: Array<{flag:string;label:string;detail:string}>
}
export interface RangeGap {
  currently_buying: Array<{product_id:string;product_name:string;sku_code:string;bottle_size_ml:number;total_bottles:number}>
  not_currently_buying: Array<{id:string;product_name:string;sku_code:string;bottle_size_ml:number}>
  gap_count: number
}

export const crmApi = {
  reps: () => apiRequest<{reps:Rep[]}>(`/api/crm/reps`),
  createActivity: (body: Record<string,unknown>) =>
    apiRequest<{activity_id:string;follow_up_id:string|null;support_request_id:string|null}>(`/api/crm/activities`, {method:'POST', body:JSON.stringify(body)}),
  clientTimeline: (clientId: string) =>
    apiRequest<CRMTimeline>(`/api/crm/activities/client/${clientId}`),
  accountHealth: (clientId: string) =>
    apiRequest<AccountHealth>(`/api/crm/account-health/${clientId}`),
  rangeGap: (clientId: string) =>
    apiRequest<RangeGap>(`/api/crm/range-gap/${clientId}`),
  completeFollowUp: (fuId: string, notes?: string) =>
    apiRequest(`/api/crm/follow-ups/${fuId}`, {method:'PATCH', body:JSON.stringify({status:'COMPLETED',completed_notes:notes||''})}),
  createOpportunity: (body: Record<string,unknown>) =>
    apiRequest<{opportunity_id:string}>(`/api/crm/opportunities`, {method:'POST', body:JSON.stringify(body)}),
  myDay: () =>
    apiRequest<Record<string,unknown>>('/api/crm/my-day'),
  managerView: () =>
    apiRequest<Record<string,unknown>>('/api/crm/manager-view'),
  calendarEventUrl: (clientName: string, actionType: string, dueDate: string, notes: string, fuId?: string) => {
    const p = new URLSearchParams({client_name:clientName, action_type:actionType, due_date:dueDate, notes, follow_up_id:fuId||''})
    return `/api/crm/calendar-event.ics?${p}`
  },
}

// ── Ownership API ─────────────────────────────────────────────────────────────

export interface OwnershipRecord {
  id: string
  full_name: string
  rep_code: string
  role: string
  territory_name: string | null
  effective_from: string
  effective_to: string | null
  change_reason: string
  notes: string | null
  is_current: boolean
}

export const ownershipApi = {
  /** Full effective-dated ownership history for a client */
  history: (clientId: string) =>
    apiRequest<{ history: OwnershipRecord[] }>(`/api/clients/${clientId}/ownership`),

  /** Assign a new owner (manager/admin only) */
  change: (clientId: string, repId: string, effectiveFrom: string, notes = '') =>
    apiRequest<{ id: string; status: string }>(`/api/clients/${clientId}/ownership`, {
      method: 'POST',
      body: JSON.stringify({ rep_id: repId, effective_from: effectiveFrom, notes }),
    }),

  /** Bulk-transfer clients from one rep to another (manager/admin only) */
  bulkTransfer: (fromRepId: string, toRepId: string, effectiveFrom: string,
                 clientIds: string[] | 'all' = 'all', notes = '') =>
    apiRequest<{ transferred: number; effective_from: string; status: string }>(
      '/api/clients/transfers/bulk',
      {
        method: 'POST',
        body: JSON.stringify({ from_rep_id: fromRepId, to_rep_id: toRepId,
                               effective_from: effectiveFrom, client_ids: clientIds, notes }),
      }
    )
}