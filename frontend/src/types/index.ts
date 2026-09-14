// ── Core types matching DB schema ─────────────────────────────────────────────

export type TransactionType =
  | 'DIRECT_SALE'
  | 'DISTRIBUTOR_SELL_IN'
  | 'DISTRIBUTOR_SELL_THROUGH'
  | 'DTC_SALE'
  | 'EXPORT_SALE'

export type RValueStatus = 'CONFIRMED' | 'ESTIMATED' | 'MISSING'

export type CoverageStatus = 'COVERED' | 'PARTIAL' | 'MISSING' | 'NOT_APPLICABLE'

export type MatchConfidence = 'CONFIRMED' | 'PROBABLE' | 'UNRESOLVED' | 'DO_NOT_MATCH'

export type ClientTier = 'KAM' | 'ON_TRADE' | 'RETAIL' | 'WHOLESALE' | 'DISTRIBUTOR' | 'DTC' | 'PRIVATE' | 'KEY_ACCOUNT'

export interface Client {
  id: string
  canonical_name: string
  trading_name?: string
  outlet_type: string
  tier: ClientTier
  territory_id: string
  is_active: boolean
  last_order_date?: string
  last_visit_date?: string
}

export interface ImportBatch {
  id: string
  file_name: string
  source_code: string
  period_from?: string
  period_to?: string
  status: string
  rows_total?: number
  rows_imported?: number
  rows_pending_mapping?: number
  created_at: string
}

export interface CoverageRecord {
  source_code: string
  region: string
  period_name: string
  coverage_status: CoverageStatus
  notes?: string
}
