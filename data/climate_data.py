"""
Climate reference data for heat pump sizing.

design_temp_heating: outdoor design temperature (degC) per EN 12831 / local norms
design_temp_cooling: outdoor design temperature (degC) for cooling sizing
HDD: heating degree days, base 18degC (annual)
CDD: cooling degree days, base 24degC (annual)
indoor_set_heating / indoor_set_cooling: assumed indoor design setpoints (degC)
electricity_price: EUR or local-currency-equivalent per kWh (default, editable in UI)
grid_co2_kg_per_kwh: grid emission factor (kg CO2 / kWh electricity)
gas_price / gas_co2: for comparison with existing fossil systems

NOTE: These are representative planning values for a sizing TOOL, not a substitute
for a full EN 12831 calculation or local climate data. Refine with local weather
station data before final engineering decisions.
"""

CLIMATES = {
    "Munich, DE": {
        "country": "Germany",
        "design_temp_heating": -12,
        "design_temp_cooling": 32,
        "indoor_set_heating": 20,
        "indoor_set_cooling": 26,
        "HDD": 3450,
        "CDD": 80,
        "electricity_price": 0.32,   # EUR/kWh
        "gas_price": 0.10,           # EUR/kWh
        "grid_co2_kg_per_kwh": 0.38,
        "gas_co2_kg_per_kwh": 0.20,
    },
    "Berlin, DE": {
        "country": "Germany",
        "design_temp_heating": -14,
        "design_temp_cooling": 31,
        "indoor_set_heating": 20,
        "indoor_set_cooling": 26,
        "HDD": 3150,
        "CDD": 90,
        "electricity_price": 0.32,
        "gas_price": 0.10,
        "grid_co2_kg_per_kwh": 0.38,
        "gas_co2_kg_per_kwh": 0.20,
    },
    "Vienna, AT": {
        "country": "Austria",
        "design_temp_heating": -12,
        "design_temp_cooling": 32,
        "indoor_set_heating": 20,
        "indoor_set_cooling": 26,
        "HDD": 3050,
        "CDD": 100,
        "electricity_price": 0.28,
        "gas_price": 0.11,
        "grid_co2_kg_per_kwh": 0.16,   # AT grid is mostly hydro/renewables
        "gas_co2_kg_per_kwh": 0.20,
    },
    "Hamburg, DE": {
        "country": "Germany",
        "design_temp_heating": -11,
        "design_temp_cooling": 29,
        "indoor_set_heating": 20,
        "indoor_set_cooling": 26,
        "HDD": 3300,
        "CDD": 50,
        "electricity_price": 0.32,
        "gas_price": 0.10,
        "grid_co2_kg_per_kwh": 0.38,
        "gas_co2_kg_per_kwh": 0.20,
    },
    "Riyadh, SA": {
        "country": "Saudi Arabia",
        "design_temp_heating": 5,
        "design_temp_cooling": 45,
        "indoor_set_heating": 21,
        "indoor_set_cooling": 24,
        "HDD": 250,
        "CDD": 4200,
        "electricity_price": 0.048,   # SAR ~0.18/kWh converted approx to EUR
        "gas_price": 0.04,
        "grid_co2_kg_per_kwh": 0.60,  # gas/oil-heavy generation mix
        "gas_co2_kg_per_kwh": 0.20,
    },
    "Jeddah, SA": {
        "country": "Saudi Arabia",
        "design_temp_heating": 12,
        "design_temp_cooling": 42,
        "indoor_set_heating": 21,
        "indoor_set_cooling": 24,
        "HDD": 50,
        "CDD": 4800,
        "electricity_price": 0.048,
        "gas_price": 0.04,
        "grid_co2_kg_per_kwh": 0.65,
        "gas_co2_kg_per_kwh": 0.20,
    },
    "Dammam, SA": {
        "country": "Saudi Arabia",
        "design_temp_heating": 8,
        "design_temp_cooling": 45,
        "indoor_set_heating": 21,
        "indoor_set_cooling": 24,
        "HDD": 150,
        "CDD": 4400,
        "electricity_price": 0.048,
        "gas_price": 0.04,
        "grid_co2_kg_per_kwh": 0.62,
        "gas_co2_kg_per_kwh": 0.20,
    },
    "NEOM region, SA": {
        "country": "Saudi Arabia",
        "design_temp_heating": 6,
        "design_temp_cooling": 40,
        "indoor_set_heating": 21,
        "indoor_set_cooling": 24,
        "HDD": 300,
        "CDD": 3600,
        "electricity_price": 0.045,
        "gas_price": 0.04,
        "grid_co2_kg_per_kwh": 0.10,  # planned renewable-heavy supply
        "gas_co2_kg_per_kwh": 0.20,
    },
}

# Specific design heat load (W/m2) at the building's reference design delta-T
# (assumes reference delta-T of 30 K, i.e. 20 degC indoor vs -10 degC outdoor;
# scaled to the actual location design delta-T in calculations)
INSULATION_CLASSES = {
    "Old / unrenovated (pre-1980)": 100,
    "Partially renovated": 70,
    "Modern standard (post-2010)": 50,
    "New build / KfW55 / Passive-style": 30,
}

# Specific cooling load (W/m2) at reference delta-T of 18 K (24 degC indoor vs 42 degC outdoor)
COOLING_LOAD_CLASSES = {
    "Old / unrenovated (pre-1980)": 130,
    "Partially renovated / standard glazing": 100,
    "Modern standard (double glazing, shading)": 75,
    "New build / high-performance envelope": 55,
}
