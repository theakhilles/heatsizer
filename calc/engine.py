"""
Core sizing & economics engine for HeatSizer.

Methods (planning-grade, based on standard engineering approaches):
- Heating design load: specific load (W/m2) scaled to actual climate delta-T
- Annual demand: degree-day method
- Gulf combined system: monthly energy balance (cooling + TES + DHW-HR + PV)
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from data.climate_data import CLIMATES, INSULATION_CLASSES, COOLING_LOAD_CLASSES, DAYS_PER_MONTH
from data.heat_pump_db import (
    HEATING_MODELS, DHW_MODELS, POOL_MODELS, REVERSIBLE_MODELS, select_model
)

REF_DELTA_T_HEATING = 30.0
REF_DELTA_T_COOLING = 18.0

DHW_DAILY_DEMAND_L_PER_PERSON = 50
WATER_SPECIFIC_HEAT_KJ_PER_KGK = 4.186
DHW_COLD_WATER_TEMP = 10
DHW_SETPOINT_TEMP = 55

POOL_SPECIFIC_LOSS_W_PER_M2 = {
    "Outdoor, uncovered": 350,
    "Outdoor, covered at night": 220,
    "Indoor pool": 150,
}

# EER polynomial for R290 reversible HP (cooling mode, T in degC)
_EER_A0, _EER_A1, _EER_A2 = 7.20, -0.082, 0.0003

def _eer_at_temp(t_amb):
    return max(1.5, _EER_A0 + _EER_A1 * t_amb + _EER_A2 * t_amb ** 2)


# ---------------------------------------------------------------------------
# SPACE HEATING
# ---------------------------------------------------------------------------
def size_space_heating(climate_key, floor_area_m2, insulation_class, flow_temp=35):
    climate = CLIMATES[climate_key]
    specific_load = INSULATION_CLASSES[insulation_class]
    delta_t_design = climate["indoor_set_heating"] - climate["design_temp_heating"]
    if delta_t_design <= 0:
        delta_t_design = 1

    q_design_w = specific_load * floor_area_m2 * (delta_t_design / REF_DELTA_T_HEATING)
    q_design_kw = q_design_w / 1000.0
    ua = q_design_kw / delta_t_design
    annual_demand_kwh = ua * climate["HDD"] * 24
    model = select_model(HEATING_MODELS, "capacity_kw", q_design_kw)

    cop_field = "cop_a7w35" if flow_temp <= 35 else "cop_a7w55"
    cop_design = model[cop_field]
    cop_cold = model["cop_a2w35"] if flow_temp <= 35 else model["cop_a2w35"] * (model["cop_a7w55"] / model["cop_a7w35"])
    scop = 0.7 * cop_design + 0.3 * cop_cold
    annual_electricity_kwh = annual_demand_kwh / scop
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
    q_design_kw = specific_loss * pool_area_m2 / 1000.0
    operating_hours = operating_months * 30 * 24
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
# SPACE COOLING (single mode)
# ---------------------------------------------------------------------------
def size_cooling(climate_key, floor_area_m2, cooling_class):
    climate = CLIMATES[climate_key]
    specific_load = COOLING_LOAD_CLASSES[cooling_class]
    delta_t_design = climate["design_temp_cooling"] - climate["indoor_set_cooling"]
    if delta_t_design <= 0:
        delta_t_design = 1

    q_design_kw = specific_load * floor_area_m2 * (delta_t_design / REF_DELTA_T_COOLING) / 1000.0
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
# GULF COMBINED SYSTEM
# Cooling HP + TES night-charging + DHW heat recovery + PV
# ---------------------------------------------------------------------------
def size_gulf_combined(
    climate_key,
    floor_area_m2,
    cooling_class,
    num_persons,
    pv_area_m2=20.0,
    tes_volume_l=500.0,
    tes_fraction=0.45,
    eta_hr=0.65,
    pv_eta=0.20,
    pv_pr=0.76,
    dhw_cold_temp=20.0,
):
    """
    Monthly energy balance for a Gulf combined system:
      Cooling HP (day) + TES night-charging + DHW heat recovery + PV
    Returns dict with monthly arrays and annual totals.
    Baseline comparison: split-AC + electric water heater.
    """
    climate = CLIMATES[climate_key]
    specific_load = COOLING_LOAD_CLASSES[cooling_class]

    # Design cooling load
    delta_t_design = max(climate["design_temp_cooling"] - climate["indoor_set_cooling"], 1.0)
    q_cool_design_kw = specific_load * floor_area_m2 * (delta_t_design / REF_DELTA_T_COOLING) / 1000.0
    ua_cool = q_cool_design_kw / delta_t_design

    # HP model
    model = select_model(REVERSIBLE_MODELS, "capacity_kw", q_cool_design_kw)
    eer_day   = _eer_at_temp(climate["design_temp_cooling"])
    eer_night = _eer_at_temp(climate["t_amb_night"])

    # DHW daily demand (Gulf: warmer cold water)
    dhw_delta_t = DHW_SETPOINT_TEMP - dhw_cold_temp
    dhw_daily_kwh = (DHW_DAILY_DEMAND_L_PER_PERSON * num_persons
                     * WATER_SPECIFIC_HEAT_KJ_PER_KGK * dhw_delta_t) / 3600.0

    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    cdd_m   = climate["cdd_monthly"]
    solar_m = climate["solar_monthly"]

    e_cool_m, e_dhw_m, e_pv_m = [], [], []
    e_hr_m = []
    w_cool_day_m, w_cool_night_m, w_dhw_m = [], [], []
    w_total_m, w_baseline_m = [], []

    for i in range(12):
        days = DAYS_PER_MONTH[i]

        # Demands
        e_cool = ua_cool * cdd_m[i] * 24.0
        e_dhw  = dhw_daily_kwh * days
        e_pv   = pv_area_m2 * pv_eta * solar_m[i] * pv_pr

        # TES night-charging
        e_cool_shifted = e_cool * tes_fraction
        e_cool_day_val = e_cool - e_cool_shifted
        w_day   = e_cool_day_val / eer_day   if eer_day   > 0 else 0.0
        w_night = e_cool_shifted / eer_night if eer_night > 0 else 0.0

        # DHW heat recovery from condenser
        q_cond = e_cool * (eer_day + 1) / eer_day if eer_day > 0 else 0.0
        q_hr   = min(eta_hr * q_cond, e_dhw)
        dhw_rem = max(e_dhw - q_hr, 0.0)
        w_dhw  = dhw_rem / 3.0   # HPWH COP

        # Net HP electricity after PV self-consumption
        w_hp_total = w_day + w_night + w_dhw
        pv_self    = min(e_pv, w_hp_total)
        w_net      = w_hp_total - pv_self

        # Baseline: split-AC (EER 2.8) + electric water heater (eff 1.0)
        w_base = e_cool / 2.8 + e_dhw / 1.0

        e_cool_m.append(round(e_cool))
        e_dhw_m.append(round(e_dhw))
        e_pv_m.append(round(e_pv))
        e_hr_m.append(round(q_hr))
        w_cool_day_m.append(round(w_day))
        w_cool_night_m.append(round(w_night))
        w_dhw_m.append(round(w_dhw))
        w_total_m.append(round(w_net))
        w_baseline_m.append(round(w_base))

    annual_cool    = sum(e_cool_m)
    annual_dhw     = sum(e_dhw_m)
    annual_pv      = sum(e_pv_m)
    annual_hr      = sum(e_hr_m)
    annual_w       = sum(w_total_m)
    annual_base    = sum(w_baseline_m)

    w_no_tes   = annual_cool / eer_day if eer_day > 0 else annual_cool
    w_with_tes = sum(w_cool_day_m) + sum(w_cool_night_m)
    tes_savings = max(w_no_tes - w_with_tes, 0.0)
    hr_frac     = annual_hr / annual_dhw if annual_dhw > 0 else 0.0

    return {
        "application": "Gulf Combined System",
        "climate_key":             climate_key,
        "design_cool_load_kw":     round(q_cool_design_kw, 2),
        "recommended_model":       model["model"],
        "recommended_capacity_kw": model["capacity_kw"],
        "eer_day":                 round(eer_day, 2),
        "eer_night":               round(eer_night, 2),
        "fob_eur":                 model["fob_eur"],
        "pv_area_m2":              pv_area_m2,
        "tes_volume_l":            tes_volume_l,
        "tes_fraction":            tes_fraction,
        "eta_hr":                  eta_hr,
        "annual_cool_demand_kwh":  annual_cool,
        "annual_dhw_demand_kwh":   annual_dhw,
        "annual_pv_yield_kwh":     annual_pv,
        "annual_hr_recovered_kwh": annual_hr,
        "hr_fraction":             round(hr_frac * 100, 1),
        "tes_savings_kwh":         round(tes_savings),
        "annual_electricity_kwh":  annual_w,
        "annual_baseline_kwh":     annual_base,
        "annual_savings_kwh":      max(annual_base - annual_w, 0),
        "months":                  months,
        "e_cool_monthly":          e_cool_m,
        "e_dhw_monthly":           e_dhw_m,
        "e_pv_monthly":            e_pv_m,
        "e_hr_monthly":            e_hr_m,
        "w_cool_day_monthly":      w_cool_day_m,
        "w_cool_night_monthly":    w_cool_night_m,
        "w_dhw_monthly":           w_dhw_m,
        "w_total_monthly":         w_total_m,
        "w_baseline_monthly":      w_baseline_m,
        "climate":                 climate,
    }


# ---------------------------------------------------------------------------
# ECONOMICS (for single-application modes)
# ---------------------------------------------------------------------------
def economics(result, climate, install_cost_eur, existing_system="Gas boiler",
              existing_efficiency=0.90):
    elec_price = climate["electricity_price"]
    annual_hp_cost = result["annual_electricity_kwh"] * elec_price
    hp_co2 = result["annual_electricity_kwh"] * climate["grid_co2_kg_per_kwh"]
    thermal_demand = result.get("annual_heat_demand_kwh") or result.get("annual_cool_demand_kwh", 0)

    if existing_system == "Electric resistance":
        existing_cost = (thermal_demand / 1.0) * elec_price
        existing_co2  = (thermal_demand / 1.0) * climate["grid_co2_kg_per_kwh"]
    elif existing_system == "None (new build)":
        existing_cost = 0
        existing_co2  = 0
    else:
        existing_cost = (thermal_demand / existing_efficiency) * climate["gas_price"]
        existing_co2  = (thermal_demand / existing_efficiency) * climate["gas_co2_kg_per_kwh"]

    annual_savings = existing_cost - annual_hp_cost
    co2_savings    = existing_co2  - hp_co2
    payback = (install_cost_eur / annual_savings
               if annual_savings > 0 and install_cost_eur > 0 else None)

    return {
        "annual_hp_running_cost_eur":  round(annual_hp_cost, 2),
        "annual_existing_cost_eur":    round(existing_cost, 2),
        "annual_savings_eur":          round(annual_savings, 2),
        "annual_co2_hp_kg":            round(hp_co2, 1),
        "annual_co2_existing_kg":      round(existing_co2, 1),
        "annual_co2_savings_kg":       round(co2_savings, 1),
        "payback_years":               round(payback, 1) if payback else None,
    }
