"""
Climate reference data for heat pump sizing.

design_temp_heating: outdoor design temperature (degC) per EN 12831 / local norms
design_temp_cooling: outdoor design temperature (degC) for cooling sizing
HDD: heating degree days, base 18degC (annual)
CDD: cooling degree days, base 24degC (annual)
cdd_monthly: monthly CDD values (list of 12), Jan-Dec, summing to CDD
solar_monthly: monthly in-plane solar irradiation kWh/(m2*month) at optimal tilt
t_amb_night: representative night ambient temperature (degC) for TES night-charging
electricity_price: EUR or local-currency-equivalent per kWh (default, editable in UI)
grid_co2_kg_per_kwh: grid emission factor (kg CO2 / kWh electricity)
gas_price / gas_co2: for comparison with existing fossil systems
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
        "cdd_monthly": [0, 0, 0, 0, 2, 12, 28, 24, 10, 4, 0, 0],
        "solar_monthly": [45, 65, 110, 145, 170, 180, 190, 175, 130, 85, 45, 35],
        "t_amb_night": 12,
        "electricity_price": 0.32,
        "gas_price": 0.10,
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
        "cdd_monthly": [0, 0, 0, 0, 3, 14, 32, 27, 10, 4, 0, 0],
        "solar_monthly": [38, 58, 105, 140, 170, 175, 185, 165, 120, 78, 40, 30],
        "t_amb_night": 11,
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
        "cdd_monthly": [0, 0, 0, 0, 4, 16, 38, 30, 10, 2, 0, 0],
        "solar_monthly": [48, 68, 115, 148, 175, 182, 195, 178, 132, 88, 48, 38],
        "t_amb_night": 13,
        "electricity_price": 0.28,
        "gas_price": 0.11,
        "grid_co2_kg_per_kwh": 0.16,
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
        "cdd_monthly": [0, 0, 0, 0, 1, 8, 20, 16, 5, 0, 0, 0],
        "solar_monthly": [35, 52, 98, 135, 165, 168, 178, 158, 112, 72, 36, 26],
        "t_amb_night": 10,
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
        "cdd_monthly": [0, 0, 42, 180, 462, 600, 672, 630, 420, 147, 42, 5],
        "solar_monthly": [155, 160, 185, 195, 220, 220, 215, 210, 195, 180, 155, 140],
        "t_amb_night": 30,
        "electricity_price": 0.048,
        "gas_price": 0.04,
        "grid_co2_kg_per_kwh": 0.60,
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
        "cdd_monthly": [120, 145, 215, 270, 450, 570, 630, 620, 510, 360, 210, 130],
        "solar_monthly": [165, 170, 195, 200, 225, 210, 195, 190, 195, 185, 160, 150],
        "t_amb_night": 28,
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
        "cdd_monthly": [0, 10, 66, 210, 484, 600, 660, 638, 462, 198, 55, 17],
        "solar_monthly": [148, 155, 178, 192, 215, 218, 210, 205, 188, 172, 148, 132],
        "t_amb_night": 29,
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
        "cdd_monthly": [0, 0, 36, 150, 396, 540, 612, 594, 396, 162, 36, 0],
        "solar_monthly": [168, 175, 200, 210, 230, 225, 218, 212, 200, 190, 165, 152],
        "t_amb_night": 26,
        "electricity_price": 0.045,
        "gas_price": 0.04,
        "grid_co2_kg_per_kwh": 0.10,
        "gas_co2_kg_per_kwh": 0.20,
    },
}

# Specific design heat load (W/m2) at building reference design delta-T of 30 K
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

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS_PER_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
