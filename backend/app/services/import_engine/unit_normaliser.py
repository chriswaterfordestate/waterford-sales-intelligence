"""
Unit Normalisation — converts source quantities to bottles_actual, SBE, and litres.

Critical rules:
- NEVER assume case size. If unit=CASES and no case_size in source → case_size_required=TRUE
- Each SKU has its own bottle_size_ml and standard_bottle_equivalent — never assume 750ml
- Credits (negative quantities) are preserved as negative bottles
"""
from typing import Optional

# Unit strings that mean "individual bottles"
BOTTLE_UNITS = {'BOTTLES', 'BOTTLE', 'X1', 'EACH', 'EA', 'UNITS', 'UNIT', 'BTL', 'BTLS'}

# Unit strings that mean "cases"
CASE_UNITS = {'CASES', 'CASE', 'KARTONS', 'KARTON', 'CTN', 'CARTONS', 'CARTON', 'CS'}


def normalise_unit(unit_raw: str) -> str:
    """Normalise raw unit string to BOTTLES or CASES."""
    u = str(unit_raw).upper().strip().replace('.', '')
    if u in BOTTLE_UNITS:
        return 'BOTTLES'
    if u in CASE_UNITS:
        return 'CASES'
    # Default: treat as bottles
    return 'BOTTLES'


def normalise_quantity(
    quantity_raw,
    unit_raw: str,
    case_size_from_source: Optional[int],
    bottle_size_ml: int,
    sbe: float,
) -> dict:
    """
    Convert source quantity to normalised bottle measures.

    Returns:
        {
            "quantity_original": float,
            "unit_original": str,
            "unit_normalised": str,
            "case_size_actual": int or None,
            "case_size_required": bool,  # TRUE = CASES but no case size
            "bottles_actual": float or None,
            "standard_bottle_equiv": float or None,
            "litres": float or None,
            "conversion_error": str or None,
        }
    """
    try:
        qty = float(quantity_raw)
    except (TypeError, ValueError):
        return {
            "quantity_original": None, "unit_original": str(unit_raw),
            "unit_normalised": "UNKNOWN", "case_size_actual": None,
            "case_size_required": False, "bottles_actual": None,
            "standard_bottle_equiv": None, "litres": None,
            "conversion_error": f"Cannot parse quantity: {quantity_raw}"
        }

    unit_norm = normalise_unit(str(unit_raw))

    if unit_norm == 'BOTTLES':
        # Simple: quantity IS bottles
        bottles = qty
        return {
            "quantity_original": qty,
            "unit_original": str(unit_raw),
            "unit_normalised": "BOTTLES",
            "case_size_actual": None,
            "case_size_required": False,
            "bottles_actual": round(bottles, 3),
            "standard_bottle_equiv": round(bottles * sbe, 3),
            "litres": round(bottles * (bottle_size_ml / 1000), 3),
            "conversion_error": None,
        }

    elif unit_norm == 'CASES':
        if case_size_from_source and int(case_size_from_source) > 0:
            case_size = int(case_size_from_source)
            bottles = qty * case_size
            return {
                "quantity_original": qty,
                "unit_original": str(unit_raw),
                "unit_normalised": "CASES",
                "case_size_actual": case_size,
                "case_size_required": False,
                "bottles_actual": round(bottles, 3),
                "standard_bottle_equiv": round(bottles * sbe, 3),
                "litres": round(bottles * (bottle_size_ml / 1000), 3),
                "conversion_error": None,
            }
        else:
            # Case size not in source — cannot convert. Flag for review.
            return {
                "quantity_original": qty,
                "unit_original": str(unit_raw),
                "unit_normalised": "CASES",
                "case_size_actual": None,
                "case_size_required": True,  # AMBER item 3
                "bottles_actual": None,
                "standard_bottle_equiv": None,
                "litres": None,
                "conversion_error": "Unit is CASES but case size not in source document. Human confirmation required."
            }

    else:
        # Unknown unit — treat as bottles with a warning
        return {
            "quantity_original": qty,
            "unit_original": str(unit_raw),
            "unit_normalised": "UNKNOWN_TREATED_AS_BOTTLES",
            "case_size_actual": None,
            "case_size_required": False,
            "bottles_actual": round(qty, 3),
            "standard_bottle_equiv": round(qty * sbe, 3),
            "litres": round(qty * (bottle_size_ml / 1000), 3),
            "conversion_error": f"Unknown unit '{unit_raw}' — treated as bottles"
        }
