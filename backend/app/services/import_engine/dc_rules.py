"""
Double-Count (DC) Rules Engine.

DC rules are applied AT WRITE TIME during ingestion — not in reporting views.
This means the exclusion decision is made once and is permanently auditable.

Rules implemented:
DC-001: Sell-in and sell-through for same SKU/distributor/period never summed
        (handled by view filters — transaction_type enforces this)
DC-002: If DIRECT_SALE exists for client+period → DISTRIBUTOR_SELL_THROUGH excluded
DC-003: End-client market view deduplication (same as DC-002 applied to v_end_client_market)
DC-004: Big Five transition month (March 2026) — direct sale takes precedence over NGF
DC-005: Norman Goodfellows dual role — handled by separate client IDs (no runtime check needed)
DC-006: Query-level enforcement (handled by excluded_from_market_view filter in views)

TX-TYPE: Transaction type excluded from market view by design (DISTRIBUTOR_SELL_IN, EXPORT_SALE)
"""
from typing import Optional
from app.services.import_engine.db_ops import check_direct_sale_exists, check_sell_through_exists


def evaluate_dc_rules(
    conn,
    transaction_type: str,
    client_id: Optional[str],
    period_id: Optional[str],
    distributor_id: Optional[str],
) -> dict:
    """
    Evaluate whether this transaction should be excluded from the market view.

    Returns:
        {
            "excluded": bool,
            "exclusion_rule": str or None,
            "exclusion_context": dict or None,
        }
    """
    # TX-TYPE: transactions excluded from commercial market view by type.
    #
    # Commercial reporting universe (not excluded):
    #   DIRECT_SALE              — trade customers, restaurants, retail
    #   DISTRIBUTOR_SELL_THROUGH — end-client sell-through subject to DC rules
    #
    # Excluded by TX-TYPE (raw rows/revenue preserved for audit):
    #   DISTRIBUTOR_SELL_IN — Waterford → distributor; not end-client market
    #   EXPORT_SALE         — export accounts; outside domestic reporting
    #   DTC_SALE            — private clients, wine club, tasting room, CPRI;
    #                         out of scope for rep/territory commercial performance
    _TX_TYPE_EXCLUDED = {
        'DISTRIBUTOR_SELL_IN': "DISTRIBUTOR_SELL_IN never appears in end-client market view",
        'EXPORT_SALE':         "EXPORT_SALE excluded from all domestic commercial reporting",
        'DTC_SALE':            "DTC_SALE (private/CPRI/tasting-room) excluded from commercial market view",
    }

    if transaction_type in _TX_TYPE_EXCLUDED:
        return {
            "excluded": True,
            "exclusion_rule": "TX-TYPE",
            "exclusion_context": {
                "reason": _TX_TYPE_EXCLUDED[transaction_type],
                "transaction_type": transaction_type
            }
        }

    # DC-002 / DC-003: Check if DIRECT_SALE exists for same client+period
    # Only applies to DISTRIBUTOR_SELL_THROUGH
    if transaction_type == 'DISTRIBUTOR_SELL_THROUGH' and client_id and period_id:
        competing_id = check_direct_sale_exists(conn, client_id, period_id)
        if competing_id:
            return {
                "excluded": True,
                "exclusion_rule": "DC-002",
                "exclusion_context": {
                    "reason": "DIRECT_SALE_EXISTS_FOR_SAME_CLIENT_AND_PERIOD",
                    "competing_transaction_id": competing_id,
                    "period_id": period_id,
                    "client_id": client_id,
                    "message": "Direct sale takes precedence over distributor sell-through for this client in this period."
                }
            }

    # DC-004: Big Five transition month — handled by DC-002 (direct sale would already exist)
    # No separate check needed — DC-002 covers it.

    # Not excluded
    return {
        "excluded": False,
        "exclusion_rule": None,
        "exclusion_context": None,
    }


def apply_dc_rules_to_new_direct_sale(conn, client_id: str, period_id: str) -> int:
    """
    When a new DIRECT_SALE is created, retroactively exclude ALL active
    DISTRIBUTOR_SELL_THROUGH rows for the same client+period (DC-002).

    This handles the case where ERP data is loaded AFTER distributor data.

    Returns the number of sell-through rows excluded.

    IMPORTANT: This must update ALL matching rows — not just the first one.
    A distributor may deliver the same product multiple times in a period
    (e.g. one 6-pack per week), producing multiple sell-through rows.
    All of them must be excluded when a direct sale is confirmed.
    """
    from app.services.import_engine.db_ops import run, s
    count_active = check_sell_through_exists(conn, client_id, period_id)
    if count_active and count_active > 0:
        run(conn, """
            UPDATE sales_transactions
            SET excluded_from_market_view = TRUE,
                exclusion_rule = 'DC-002',
                exclusion_context = %s::jsonb,
                exclusion_evaluated_at = NOW()
            WHERE client_id = %s::uuid
              AND financial_period_id = %s::uuid
              AND transaction_type = 'DISTRIBUTOR_SELL_THROUGH'
              AND is_primary_record = TRUE
              AND excluded_from_market_view = FALSE
        """, (
            f'{{"reason":"DIRECT_SALE_LOADED_AFTER_SELL_THROUGH","direct_sale_period":"{period_id}"}}',
            client_id, period_id
        ))
        return count_active
    return 0
