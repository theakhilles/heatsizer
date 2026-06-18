"""
Representative R290 (propane) heat pump product line for sizing recommendations.

This is a GENERIC reference catalog representing typical specs you'd find from
Chinese OEM manufacturers (PHNIX, Solareast, Midea OEM, Zealux, JDL, etc.) for
R290 monoblock units. Replace with actual supplier datasheets once suppliers
are selected -- the tool architecture (lookup by capacity step) stays the same.

COP_REF values are at standard rating point A7/W35 (7 degC ambient / 35 degC
flow) for heating, and a generic EER for cooling-capable (reversible) units.
"""

# Standard capacity steps (kW) offered across the line
HEATING_MODELS = [
    {"model": "RX-06", "capacity_kw": 6,  "cop_a7w35": 4.6, "cop_a7w55": 3.1, "cop_a2w35": 3.6, "fob_eur": 750},
    {"model": "RX-08", "capacity_kw": 8,  "cop_a7w35": 4.6, "cop_a7w55": 3.1, "cop_a2w35": 3.6, "fob_eur": 950},
    {"model": "RX-12", "capacity_kw": 12, "cop_a7w35": 4.5, "cop_a7w55": 3.0, "cop_a2w35": 3.5, "fob_eur": 1250},
    {"model": "RX-16", "capacity_kw": 16, "cop_a7w35": 4.4, "cop_a7w55": 3.0, "cop_a2w35": 3.4, "fob_eur": 1650},
    {"model": "RX-20", "capacity_kw": 20, "cop_a7w35": 4.3, "cop_a7w55": 2.9, "cop_a2w35": 3.3, "fob_eur": 2100},
    {"model": "RX-30", "capacity_kw": 30, "cop_a7w35": 4.2, "cop_a7w55": 2.9, "cop_a2w35": 3.2, "fob_eur": 3200},
]

# DHW heat pump water heaters (tank-integrated or split)
DHW_MODELS = [
    {"model": "WH-200", "volume_l": 200, "heat_capacity_kw": 1.5, "cop": 3.2, "fob_eur": 450},
    {"model": "WH-300", "volume_l": 300, "heat_capacity_kw": 2.0, "cop": 3.3, "fob_eur": 620},
    {"model": "WH-500", "volume_l": 500, "heat_capacity_kw": 3.0, "cop": 3.3, "fob_eur": 980},
]

# Pool heat pumps
POOL_MODELS = [
    {"model": "PL-09", "capacity_kw": 9,  "cop": 6.5, "fob_eur": 700},
    {"model": "PL-15", "capacity_kw": 15, "cop": 6.0, "fob_eur": 1050},
    {"model": "PL-22", "capacity_kw": 22, "cop": 5.5, "fob_eur": 1450},
    {"model": "PL-30", "capacity_kw": 30, "cop": 5.2, "fob_eur": 1900},
]

# Reversible (heating + cooling) units for Gulf-style applications
REVERSIBLE_MODELS = [
    {"model": "RV-08", "capacity_kw": 8,  "cop_heat": 4.3, "eer_cool": 3.4, "fob_eur": 1100},
    {"model": "RV-12", "capacity_kw": 12, "cop_heat": 4.2, "eer_cool": 3.4, "fob_eur": 1450},
    {"model": "RV-16", "capacity_kw": 16, "cop_heat": 4.1, "eer_cool": 3.3, "fob_eur": 1900},
    {"model": "RV-24", "capacity_kw": 24, "cop_heat": 4.0, "eer_cool": 3.2, "fob_eur": 2700},
    {"model": "RV-35", "capacity_kw": 35, "cop_heat": 3.9, "eer_cool": 3.1, "fob_eur": 3900},
    {"model": "RV-50", "capacity_kw": 50, "cop_heat": 3.8, "eer_cool": 3.0, "fob_eur": 5400},
]


def select_model(catalog, capacity_field, required_kw, safety_margin=1.10):
    """Pick the smallest model whose capacity >= required_kw * safety_margin."""
    target = required_kw * safety_margin
    candidates = sorted(catalog, key=lambda m: m[capacity_field])
    for m in candidates:
        if m[capacity_field] >= target:
            return m
    # If nothing big enough, return the largest and flag for multiple units
    return candidates[-1]
