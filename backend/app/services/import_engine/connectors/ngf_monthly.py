"""
NGF Monthly connector — WaterfordMonthlyReport Excel format.

The actual NGF file uses a flat "Data" sheet (not JHB/KZN tabs).
Columns: TrnDate, StockCode, StockDescription, Invoice, UnitQuantity,
         LongDesc, Litres, Customer, CustomerName, Supplier, SupplierName,
         Month, Year, SalesPerson, TrnMonth, TrnYear, Warehouse, Region, RetailWholesaler

Key fields:
  TrnDate   → calendar date → financial period (authoritative)
  LongDesc  → readable product description (used for product matching)
  StockDescription → short product code description
  CustomerName → client name for MCR matching
  Customer  → NGF customer code
  UnitQuantity → bottles
  Region    → CPT / KZN (territory)

Yields DISTRIBUTOR_SELL_THROUGH rows through the standard pipeline.
"""
from __future__ import annotations
import os
import re
from typing import Iterator
from datetime import datetime
import pandas as pd


SOURCE_CODE = 'NGF_MONTHLY'


def detect(file_path: str) -> bool:
    """True if this looks like an NGF Monthly Waterford report."""
    if not file_path.lower().endswith(('.xlsx', '.xls')):
        return False
    try:
        xl = pd.ExcelFile(file_path, engine='openpyxl')
        if 'Data' not in xl.sheet_names:
            return False
        df = xl.parse('Data', nrows=1)
        cols = set(df.columns)
        return {'TrnDate', 'CustomerName', 'UnitQuantity', 'Region'}.issubset(cols)
    except Exception:
        return False


def _parse_trndate(value) -> tuple[int, int] | None:
    """Return (calendar_year, calendar_month) from TrnDate."""
    if pd.isna(value):
        return None
    try:
        dt = pd.to_datetime(value)
        return dt.year, dt.month
    except Exception:
        return None


def iter_rows(file_path: str) -> Iterator[dict]:
    """
    Yield one row dict per non-zero NGF sell-through transaction.
    Uses TrnDate for period — NOT TrnMonth/TrnYear (different FY convention).
    """
    xl = pd.ExcelFile(file_path, engine='openpyxl')
    if 'Data' not in xl.sheet_names:
        return

    df = xl.parse('Data')
    if df.empty:
        return

    for _, row in df.iterrows():
        trndate = row.get('TrnDate')
        ym = _parse_trndate(trndate)
        if not ym:
            continue

        cal_year, cal_month = ym
        qty = float(row.get('UnitQuantity', 0) or 0)
        if qty <= 0:
            continue

        customer_name = str(row.get('CustomerName', '') or '').strip()
        customer_code = str(row.get('Customer', '') or '').strip()
        region = str(row.get('Region', '') or '').strip()       # CPT / KZN
        product_desc = str(row.get('LongDesc', '') or '').strip() or \
                       str(row.get('StockDescription', '') or '').strip()
        stock_code = str(row.get('StockCode', '') or '').strip()
        litres = float(row.get('Litres', 0) or 0)
        salesperson = str(row.get('SalesPerson', '') or '').strip()
        invoice = str(row.get('Invoice', '') or '').strip()

        raw_data = {
            'drname':       customer_name,
            'debtor':       customer_code,
            'salgrpname':   product_desc,
            'stockitem':    stock_code,
            'bottles':      qty,
            'net':          0,             # no invoice value in sell-through report
            'litres_row':   litres,
            'region':       region,
            'sareaname':    region,
            'drgrpname':    'NGF Sell-Through',
            'srepname':     salesperson,
            'invnum':       invoice,
            'cal_year':     cal_year,
            'cal_month':    cal_month,
        }

        yield {
            # ── Standardized connector contract ───────────────────────────
            'client_name':       customer_name,   # NGF CustomerName → matcher
            'client_code':       customer_code,   # NGF Customer code → alias lookup
            'product_desc':      product_desc,    # LongDesc/StockDescription → product matcher
            # ── NGF Monthly-specific fields ───────────────────────────────
            'drname':            customer_name,
            'debtor':            customer_code,
            'salgrp':            product_desc,
            'stockitem':         stock_code,
            'bottles':           qty,
            'net_val':           0.0,
            'calendar_year':     cal_year,
            'calendar_month':    cal_month,
            'transaction_type':  'DISTRIBUTOR_SELL_THROUGH',
            'distributor_id':    None,  # resolved by pipeline from NGF dist record
            'unit':              'BOTTLES',
            'case_size':         None,
            'stockunit':         None,
            'region':            region,
            'raw_data':          raw_data,
            'exclude':           False,
            'exclusion_reason':  None,
        }
