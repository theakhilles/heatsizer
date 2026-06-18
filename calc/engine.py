"""
Core sizing & economics engine.

Methods used (deliberately simplified for a fast interactive tool, but based
on standard engineering approaches):

- Heating design load: specific load (W/m2) at a reference delta-T of 30 K,
  scaled linearly to the actual design delta-T of the chosen location.
  (Linear scaling of UA is a reasonable first-order approximation.)

- Annual heating demand: degree-day method.
  Q_annual [kWh] = UA [kW/K] * HDD [Kday] * 24 [h/day] / 1000 ... using
  UA = Q_design / delta_T_design.

- Cooling: same approach using CDD and a reference delta-T of 18 K.

- DHW demand: standard daily hot water consumption (L/person/day) heated
  from cold-water inlet to setpoint.

- Pool heat demand: simplified surface heat loss model.

- COP/SCOP: interpolated from rating-point data in heat_pump_db, adjusted
  for climate severity via a simple bin-weighted approximation.

These are PLANNING-GRADE estimates intended for lead qualification and early
feasibility -- always validate with EN 12831 / detailed simulation (e.g. your
OpenModelica models) before final equipment selection.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from data.climate_data import CLIMATES, INSULATION_CLASSES, COOLING_LOAD_CLASSES
from data.heat_pump_db import (
    HEATING_MODELS, DHW_MODELS, POOL_MODELS, REVERSIBLE_MODELS, select_model
)

REF_DELTA_T_HEATING = 30.0  # K, reference for INSULATION_CLASSES specific loads
REF_DELTA_T_COOLING = 18.0  # K, reference for COOLING_LOAD_CLASSES specific loads

DHW_DAILY_DEMAND_L_PER_PERSON = 50  # L/person/day at delta-T ~35K
WATER_SPECIFIC_HEAT_KJ_PER_KGK = 4.186
DHW_COLD_WATER_TEMP = 10  # degC
DHW_SETPOINT_TEMP = 55  # degC (storage temp; tempered before use)

POOL_SPECIFIC_LOSS_W_PER_M2 = {
    "Outdoor, uncovered": 350,
    "Outdoor, covered at night": 220,
    "Indoor pool": 150,
}


# ---------------------------------------------------------------------------
# SPACE HEATING
# ---------------------------------------------------------------------------

def size_space_heating(climate_key, floor_area_m2, insulation_class, flow_temp=35):
    climate = CLIMATES[climate_key]
    specific_load = INSULATION_CLASSES[insulation_class]  # W/m2 at REF_DELTA_T_HEATING

    delta_t_design = climate["indoor_set_heating"] - climate["design_temp_heating"]
    if delta_t_design <= 0:
        delta_t_design = 1  # guard for very mild climates

    # Scale design load to actual climate delta-T
    q_design_w = specific_load * floor_area_m2 * (delta_t_design / REF_DELTA_T_HEATING)
    q_design_kw = q_design_w / 1000.0

    # UA in kW/K
    ua = q_design_kw / delta_t_design

    # Annual heating demand via degree-days (HDD base 18degC)
    annual_demand_kwh = ua * climate["HDD"] * 24

    # Pick heat pump model
    model = select_model(HEATING_MODELS, "capacity_kw", q_design_kw)

    # COP depends on flow temperature
    if flow_temp <= 35:
        cop_field = "cop_a7w35"
    else:
        cop_field = "cop_a7w55"
    cop_design = model[cop_field]

    # Approximate SCOP: average of design-point COP and a colder-bin COP,
    # weighted toward the milder bin (most operating hours are mild).
    cop_cold = model["cop_a2w35"] if flow_temp <= 35 else model["cop_a2w35"] * (model["cop_a7w55"] / model["cop_a7w35"])
    scop = 0.7 * cop_design + 0.3 * cop_cold

    annual_electricity_kwh = annual_demand_kwh / scop

    # Buffer tank recommendation: ~20 L per kW of heat pump capacity (rule of thumb)
    buffer_tank_l = round(model["capacity_kw"] * 20 / 10) * 10

    return {
        "application": "Space Heating",
        "design_load_kw": round(q_design_kw, 2),
        "delta_t_design_k": round(delta_t_design, 1),
        "annual_heat_demand_kwh": round(annual_demand_kwh),
        "recommended_model": model["model"],
        "recommended_capacity_kw": model["capacity_kw"],
        "scop_estimate": round(scop, 2),
        "annual_electricity_kwh": round(annual_electricity_kwh),
        "buffer_tank_l": buffer_tank_l,
        "fob_eur": model["fob_eur"],
        "climate": climate,
    }


# ---------------------------------------------------------------------------
# DOMESTIC HOT WATER
# ---------------------------------------------------------------------------

def size_dhw(climate_key, num_persons):
    climate = CLIMATES[climate_key]

    daily_demand_l = DHW_DAILY_DEMAND_L_PER_PERSON * num_persons
    delta_t = DHW_SETPOINT_TEMP - DHW_COLD_WATER_TEMP

    daily_energy_kwh = (daily_demand_l * WATER_SPECIFIC_HEAT_KJ_PER_KGK * delta_t) / 3600
    annual_demand_kwh = daily_energy_kwh * 365

    # pick a tank size with margin
    required_volume = daily_demand_l * 1.3
    model = select_model(DHW_MODELS, "volume_l", required_volume, safety_margin=1.0)

    annual_electricity_kwh = annual_demand_kwh / model["cop"]

    return {
        "application": "Domestic Hot Water",
        "daily_demand_l": round(daily_demand_l),
        "annual_heat_demand_kwh": round(annual_demand_kwh),
        "recommended_model": model["model"],
        "recommended_volume_l": model["volume_l"],
        "cop_estimate": model["cop"],
        "annual_electricity_kwh": round(annual_electricity_kwh),
        "fob_eur": model["fob_eur"],
        "climate": climate,
    }


# ---------------------------------------------------------------------------
# POOL HEATING
# ---------------------------------------------------------------------------

def size_pool(climate_key, pool_area_m2, pool_type, operating_months=6):
    climate = CLIMATES[climate_key]
    specific_loss = POOL_SPECIFIC_LOSS_W_PER_M2[pool_type]

    q_design_w = specific_loss * pool_area_m2
    q_design_kw = q_design_w / 1000.0

    operating_hours = operating_months * 30 * 24
    # Assume average load is ~50% of design (mild periods within season)
    annual_demand_kwh = q_design_kw * operating_hours * 0.5

    model = select_model(POOL_MODELS, "capacity_kw", q_design_kw, safety_margin=1.0)
    annual_electricity_kwh = annual_demand_kwh / model["cop"]

    return {
        "application": "Pool Heating",
        "design_load_kw": round(q_design_kw, 2),
        "annual_heat_demand_kwh": round(annual_demand_kwh),
        "recommended_model": model["model"],
        "recommended_capacity_kw": model["capacity_kw"],
        "cop_estimate": model["cop"],
        "annual_electricity_kwh": round(annual_electricity_kwh),
        "fob_eur": model["fob_eur"],
        "climate": climate,
    }


# ---------------------------------------------------------------------------
# COOLING (Gulf-style)
# ---------------------------------------------------------------------------

def size_cooling(climate_key, floor_area_m2, cooling_class):
    climate = CLIMATES[climate_key]
    specific_load = COOLING_LOAD_CLASSES[cooling_class]  # W/m2 at REF_DELTA_T_COOLING

    delta_t_design = climate["design_temp_cooling"] - climate["indoor_set_cooling"]
    if delta_t_design <= 0:
        delta_t_design = 1

    q_design_w = specific_load * floor_area_m2 * (delta_t_design / REF_DELTA_T_COOLING)
    q_design_kw = q_design_w / 1000.0

    ua = q_design_kw / delta_t_design
    annual_demand_kwh = ua * climate["CDD"] * 24

    model = select_model(REVERSIBLE_MODELS, "capacity_kw", q_design_kw)
    eer = model["eer_cool"]
    annual_electricity_kwh = annual_demand_kwh / eer

    return {
        "application": "Space Cooling",
        "design_load_kw": round(q_design_kw, 2),
        "delta_t_design_k": round(delta_t_design, 1),
        "annual_cool_demand_kwh": round(annual_demand_kwh),
        "recommended_model": model["model"],
        "recommended_capacity_kw": model["capacity_kw"],
        "eer_estimate": eer,
        "cop_heat_estimate": model["cop_heat"],
        "annual_electricity_kwh": round(annual_electricity_kwh),
        "fob_eur": model["fob_eur"],
        "climate": climate,
    }


# ---------------------------------------------------------------------------
# ECONOMICS
# ---------------------------------------------------------------------------

def economics(result, climate, install_cost_eur, existing_system="Gas boiler", existing_efficiency=0.90):
    """
    Compute running costs, savings vs existing system, simple payback, and
    CO2 impact.
    `result` must contain 'annual_electricity_kwh' and either
    'annual_heat_demand_kwh' or 'annual_cool_demand_kwh'.
    """
    elec_price = climate["electricity_price"]
    annual_hp_cost = result["annual_electricity_kwh"] * elec_price
    hp_co2 = result["annual_electricity_kwh"] * climate["grid_co2_kg_per_kwh"]

    thermal_demand = result.get("annual_heat_demand_kwh") or result.get("annual_cool_demand_kwh", 0)

    if existing_system == "Electric resistance":
        existing_annual_kwh = thermal_demand / 1.0
        existing_cost = existing_annual_kwh * elec_price
        existing_co2 = existing_annual_kwh * climate["grid_co2_kg_per_kwh"]
    elif existing_system == "None (new build)":
        existing_cost = 0
        existing_co2 = 0
    else:  # Gas/oil boiler
        existing_annual_kwh = thermal_demand / existing_efficiency
        existing_cost = existing_annual_kwh * climate["gas_price"]
        existing_co2 = existing_annual_kwh * climate["gas_co2_kg_per_kwh"]

    annual_savings = existing_cost - annual_hp_cost
    co2_savings = existing_co2 - hp_co2

    if annual_savings > 0 and install_cost_eur > 0:
        payback_years = install_cost_eur / annual_savings
    else:
        payback_years = None

    return {
        "annual_hp_running_cost_eur": round(annual_hp_cost, 2),
        "annual_existing_cost_eur": round(existing_cost, 2),
        "annual_savings_eur": round(annual_savings, 2),
        "annual_co2_hp_kg": round(hp_co2, 1),
        "annual_co2_existing_kg": round(existing_co2, 1),
        "annual_co2_savings_kg": round(co2_savings, 1),
        "payback_years": round(payback_years, 1) if payback_years else None,
    }
