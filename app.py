"""
HeatSizer -- Heat Pump Sizing & Feasibility Tool
ThermaCore EU  |  eng.akasem@gmail.com

Run with:
    streamlit run app.py

Features:
- Lead capture (name + email before results)
- Planning-grade sizing for Space Heating, DHW, Pool, Space Cooling
- Branded PDF report download
- Model names hidden from customer output
"""

import csv
import io
import os
from datetime import datetime

import streamlit as st
import plotly.graph_objects as go
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

from data.climate_data import CLIMATES, INSULATION_CLASSES, COOLING_LOAD_CLASSES
from calc.engine import (
    size_space_heating, size_dhw, size_pool, size_cooling,
    size_gulf_combined, economics,
    POOL_SPECIFIC_LOSS_W_PER_M2,
)

# ── Brand colours ────────────────────────────────────────────
BRAND_BLUE   = colors.HexColor("#1F3864")
BRAND_LIGHT  = colors.HexColor("#2E75B6")
BRAND_GRAY   = colors.HexColor("#595959")
BRAND_BG     = colors.HexColor("#EBF2FA")

LEADS_FILE = "leads.csv"

# ────────────────────────────────────────────────────────────
st.set_page_config(page_title="HeatSizer | ThermaCore EU", page_icon="🌡️", layout="wide")

# ── Header ───────────────────────────────────────────────────
st.title("🌡️ HeatSizer")
st.caption("Heat pump sizing & feasibility — Europe & Gulf  |  ThermaCore EU · eng.akasem@gmail.com")
st.markdown(
    "Enter your building details to get an instant heat pump recommendation, "
    "expected energy performance, running costs, and CO₂ impact. "
    "*Planning-grade estimate — for binding designs, a full EN 12831 calculation is recommended.*"
)
st.divider()

# ── Lead capture (session state) ─────────────────────────────
if "lead_captured" not in st.session_state:
    st.session_state.lead_captured = False
if "lead_name" not in st.session_state:
    st.session_state.lead_name = ""
if "run_calculation" not in st.session_state:
    st.session_state.run_calculation = False

def save_lead(name, email, location, application):
    """Append lead to CSV. Fails silently so tool still works."""
    try:
        file_exists = os.path.isfile(LEADS_FILE)
        with open(LEADS_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "name", "email", "location", "application"])
            writer.writerow([datetime.utcnow().isoformat(), name, email, location, application])
    except Exception:
        pass

# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.header("📍 Location & Application")
    location = st.selectbox("Location", list(CLIMATES.keys()), index=0)
    climate   = CLIMATES[location]

    application = st.selectbox(
        "Application",
        ["Space Heating", "Domestic Hot Water (DHW)", "Pool Heating", "Space Cooling",
         "🌍 Gulf Combined System (Cooling + TES + DHW-HR + PV)"],
    )

    st.divider()
    st.header("🏠 Building / System Details")

    if application == "Space Heating":
        floor_area = st.number_input("Heated floor area (m²)", min_value=20, max_value=2000, value=150, step=10)
        insulation  = st.selectbox("Insulation level", list(INSULATION_CLASSES.keys()), index=1)
        flow_temp   = st.radio(
            "Heat distribution", [35, 55], index=0,
            format_func=lambda x: "Underfloor / low-temp (35°C)" if x == 35 else "Radiators (55°C)"
        )
    elif application == "Domestic Hot Water (DHW)":
        num_persons = st.number_input("Number of occupants", min_value=1, max_value=20, value=4, step=1)
    elif application == "Pool Heating":
        pool_area        = st.number_input("Pool surface area (m²)", min_value=5, max_value=500, value=32, step=1)
        pool_type        = st.selectbox("Pool type", list(POOL_SPECIFIC_LOSS_W_PER_M2.keys()))
        operating_months = st.slider("Operating months per year", 1, 12, 6)
    elif application == "Space Cooling":
        floor_area    = st.number_input("Cooled floor area (m²)", min_value=20, max_value=2000, value=200, step=10)
        cooling_class = st.selectbox("Building envelope quality", list(COOLING_LOAD_CLASSES.keys()), index=1)

    elif application == "🌍 Gulf Combined System (Cooling + TES + DHW-HR + PV)":
        st.markdown("##### 🏢 Building")
        floor_area    = st.number_input("Cooled floor area (m²)", min_value=20, max_value=5000, value=300, step=10)
        cooling_class = st.selectbox("Building envelope quality", list(COOLING_LOAD_CLASSES.keys()), index=1)
        num_persons   = st.number_input("Occupants (for DHW)", min_value=1, max_value=100, value=6, step=1)
        st.markdown("##### ☀️ PV System")
        pv_area       = st.number_input("PV panel area (m²)", min_value=0, max_value=2000, value=40, step=5,
                                         help="Roof or ground-mounted. ~5 m² per kWp for standard panels.")
        st.markdown("##### 🧊 Thermal Energy Storage (TES)")
        tes_volume    = st.number_input("TES tank volume (L)", min_value=0, max_value=50000, value=1000, step=100,
                                         help="Chilled water tank. Rule of thumb: 20–40 L per kW of cooling capacity.")
        tes_fraction  = st.slider("Night-charge fraction of cooling load", 0.1, 0.8, 0.45, 0.05,
                                   help="Fraction of daily cooling stored at night (lower ambient → higher EER).")
        st.markdown("##### ♻️ DHW Heat Recovery")
        eta_hr        = st.slider("Heat recovery effectiveness", 0.3, 0.9, 0.65, 0.05,
                                   help="Fraction of condenser heat rejection recovered for DHW. 0.65 = dedicated HX.")

    st.divider()
    st.header("💰 Economics")
    existing_system = st.selectbox(
        "Current / alternative system",
        ["Gas boiler", "Electric resistance", "None (new build)"],
    )
    elec_price_override = st.number_input(
        "Electricity price (EUR/kWh)", min_value=0.01, max_value=1.0,
        value=float(climate["electricity_price"]), step=0.01, format="%.3f"
    )
    install_cost = st.number_input(
        "Estimated installed cost (EUR, equipment + install)",
        min_value=0, max_value=50000, value=8000, step=500
    )

    run = st.button("Calculate", type="primary", use_container_width=True)
    if run:
        st.session_state.run_calculation = True

climate = dict(climate)
climate["electricity_price"] = elec_price_override

# ── Lead capture gate ────────────────────────────────────────
def lead_gate(location, application):
    """Show lead form if not yet captured. Returns True when ready."""
    if st.session_state.lead_captured:
        return True

    st.subheader("📬 Get your free sizing report")
    st.markdown(
        "Enter your name and email to see the full recommendation and download a PDF report. "
        "We'll also follow up with a personalised quote — no obligation."
    )
    with st.form("lead_form"):
        name  = st.text_input("Your name *")
        email = st.text_input("Email address *")
        submit = st.form_submit_button("Show my results →", type="primary")

    if submit:
        if not name.strip() or "@" not in email:
            st.error("Please enter a valid name and email address.")
            return False
        save_lead(name.strip(), email.strip(), location, application)
        st.session_state.lead_captured = True
        st.session_state.lead_name = name.strip()
        st.rerun()

    return False

# ── PDF report builder ───────────────────────────────────────
def build_pdf(result, econ, climate_key, application, existing_system, install_cost, lead_name):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"],
        textColor=BRAND_BLUE, fontSize=20, spaceAfter=4
    )
    sub_style = ParagraphStyle(
        "Sub", parent=styles["Normal"],
        textColor=BRAND_LIGHT, fontSize=12, spaceAfter=12
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=10, leading=14, spaceAfter=6
    )
    label_style = ParagraphStyle(
        "Label", parent=styles["Normal"],
        fontSize=9, textColor=BRAND_GRAY
    )
    disclaimer_style = ParagraphStyle(
        "Disc", parent=styles["Normal"],
        fontSize=8, textColor=BRAND_GRAY, leading=11
    )

    story = []

    # Header
    story.append(Paragraph("🌡 HeatSizer — Sizing Report", title_style))
    story.append(Paragraph("ThermaCore EU  ·  eng.akasem@gmail.com", sub_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=BRAND_BLUE, spaceAfter=10))

    # Meta
    date_str = datetime.utcnow().strftime("%d %B %Y")
    story.append(Paragraph(f"<b>Prepared for:</b> {lead_name or 'Customer'}", body_style))
    story.append(Paragraph(f"<b>Date:</b> {date_str}", body_style))
    story.append(Paragraph(f"<b>Location:</b> {climate_key}", body_style))
    story.append(Paragraph(f"<b>Application:</b> {application}", body_style))
    story.append(Spacer(1, 0.4*cm))

    # System recommendation (no model name)
    story.append(Paragraph("Recommended System", sub_style))
    cap_key  = "recommended_capacity_kw" if "recommended_capacity_kw" in result else "recommended_volume_l"
    cap_unit = "kW" if cap_key == "recommended_capacity_kw" else "L"
    cap_val  = result[cap_key]

    perf_label = ""
    perf_val   = ""
    if "scop_estimate" in result:
        perf_label, perf_val = "Estimated SCOP", str(result["scop_estimate"])
    elif "cop_estimate" in result:
        perf_label, perf_val = "Estimated COP", str(result["cop_estimate"])
    elif "eer_estimate" in result:
        perf_label, perf_val = "Estimated EER (cooling)", str(result["eer_estimate"])

    rec_data = [
        ["R290 Air-to-Water Heat Pump", f"{cap_val} {cap_unit} capacity"],
        [perf_label, perf_val],
        ["Indicative equipment price (FOB)", f"€{result['fob_eur']:,}"],
    ]
    if "buffer_tank_l" in result:
        rec_data.append(["Recommended buffer tank", f"{result['buffer_tank_l']} L"])

    rec_table = Table(rec_data, colWidths=[9*cm, 8*cm])
    rec_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BG),
        ("BACKGROUND", (0, 1), (-1, 1), colors.white),
        ("BACKGROUND", (0, 2), (-1, 2), BRAND_BG),
        ("BACKGROUND", (0, 3), (-1, 3), colors.white),
        ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("ROWBACKGROUND", (0, 0), (-1, -1), [BRAND_BG, colors.white]),
        ("GRID",       (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(rec_table)
    story.append(Spacer(1, 0.4*cm))

    # Energy section
    story.append(Paragraph("Energy Summary", sub_style))
    thermal = result.get("annual_heat_demand_kwh") or result.get("annual_cool_demand_kwh", 0)
    energy_data = [
        ["Annual thermal demand",    f"{thermal:,.0f} kWh"],
        ["Annual electricity use",   f"{result['annual_electricity_kwh']:,.0f} kWh"],
    ]
    if "design_load_kw" in result:
        energy_data.insert(0, ["Design load", f"{result['design_load_kw']} kW"])

    e_table = Table(energy_data, colWidths=[9*cm, 8*cm])
    e_table.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ROWBACKGROUND", (0, 0), (-1, -1), [BRAND_BG, colors.white]),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    story.append(e_table)
    story.append(Spacer(1, 0.4*cm))

    # Economics section
    story.append(Paragraph("Economic Analysis", sub_style))
    savings     = econ["annual_savings_eur"]
    savings_str = f"€{savings:,.0f} / yr saved" if savings >= 0 else f"€{abs(savings):,.0f} / yr extra cost"
    payback     = f"{econ['payback_years']} years" if econ["payback_years"] else "n/a"
    co2_sav     = econ["annual_co2_savings_kg"]
    co2_str     = f"{co2_sav:,.0f} kg/yr reduction" if co2_sav >= 0 else f"{abs(co2_sav):,.0f} kg/yr increase"

    econ_data = [
        ["Heat pump running cost",       f"€{econ['annual_hp_running_cost_eur']:,.0f} / yr"],
        [f"{existing_system} cost",      f"€{econ['annual_existing_cost_eur']:,.0f} / yr"],
        ["Annual savings vs. existing",  savings_str],
        ["Simple payback period",        payback],
        ["Installed cost (estimate)",    f"€{install_cost:,}"],
        ["CO₂ impact vs. existing",      co2_str],
    ]
    eco_table = Table(econ_data, colWidths=[9*cm, 8*cm])
    eco_table.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ROWBACKGROUND", (0, 0), (-1, -1), [BRAND_BG, colors.white]),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    story.append(eco_table)
    story.append(Spacer(1, 0.5*cm))

    # Next steps
    story.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_LIGHT, spaceAfter=8))
    story.append(Paragraph("Next Steps", sub_style))
    story.append(Paragraph(
        "This report is a planning-grade estimate suitable for budgeting and feasibility. "
        "To proceed, contact ThermaCore EU for:",
        body_style
    ))
    for item in [
        "Full EN 12831 heat load calculation",
        "Hydraulic design and equipment specification",
        "Sourcing, supply, and commissioning quote",
        "OpenModelica system simulation for complex projects",
    ]:
        story.append(Paragraph(f"• {item}", body_style))

    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "<b>Contact:</b> Ahmed Abouelkasem  ·  eng.akasem@gmail.com  ·  Bregenz, Austria",
        body_style
    ))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Paragraph(
        f"Generated by HeatSizer on {date_str}. All results are planning-grade estimates based on "
        "degree-day methods and representative equipment data. Not a substitute for a full engineering "
        "calculation per EN 12831 or a detailed simulation. ThermaCore EU accepts no liability for "
        "decisions made solely on the basis of this report.",
        disclaimer_style
    ))

    doc.build(story)
    buf.seek(0)
    return buf

# ── Gulf Combined System results ─────────────────────────────
def _show_gulf_results(result, climate, install_cost, existing_system, lead_name):
    name_greeting = f", {lead_name}" if lead_name else ""
    st.success(f"✅ Gulf Combined System results{name_greeting}!")

    # ── Key metrics row ──────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cooling HP capacity", f"{result['recommended_capacity_kw']} kW")
    c2.metric("EER day / night", f"{result['eer_day']} / {result['eer_night']}")
    c3.metric("DHW heat recovery", f"{result['hr_fraction']}% of demand")
    c4.metric("Annual PV yield", f"{result['annual_pv_yield_kwh']:,} kWh")

    st.divider()

    # ── System savings breakdown ─────────────────────────────────────────────
    st.subheader("Annual Energy & Savings Summary")
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown("**🧊 Cooling + TES**")
        st.write(f"Annual cooling demand: **{result['annual_cool_demand_kwh']:,} kWh**")
        st.write(f"TES night-charge savings: **{result['tes_savings_kwh']:,} kWh**")
        st.write(f"EER improvement (night vs day): **{result['eer_night']} vs {result['eer_day']}**")

    with col_b:
        st.markdown("**♻️ DHW Heat Recovery**")
        st.write(f"Annual DHW demand: **{result['annual_dhw_demand_kwh']:,} kWh**")
        st.write(f"Recovered from condenser: **{result['annual_hr_recovered_kwh']:,} kWh**")
        st.write(f"DHW coverage by recovery: **{result['hr_fraction']}%**")

    with col_c:
        st.markdown("**☀️ PV Self-Consumption**")
        st.write(f"PV area: **{result['pv_area_m2']} m²**")
        st.write(f"Annual PV yield: **{result['annual_pv_yield_kwh']:,} kWh**")
        st.write(f"Net HP electricity: **{result['annual_electricity_kwh']:,} kWh**")

    st.divider()

    # ── vs Baseline comparison ───────────────────────────────────────────────
    st.subheader("Combined System vs. Baseline (Split-AC + Electric Water Heater)")
    elec_price = climate["electricity_price"]
    cost_combined = result['annual_electricity_kwh'] * elec_price
    cost_baseline = result['annual_baseline_kwh'] * elec_price
    savings_eur   = cost_baseline - cost_combined
    co2_combined  = result['annual_electricity_kwh'] * climate["grid_co2_kg_per_kwh"]
    co2_baseline  = result['annual_baseline_kwh'] * climate["grid_co2_kg_per_kwh"]
    co2_savings   = co2_baseline - co2_combined
    payback       = round(install_cost / savings_eur, 1) if savings_eur > 0 and install_cost > 0 else None

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Combined system cost", f"€{cost_combined:,.0f}/yr")
    m2.metric("Baseline cost", f"€{cost_baseline:,.0f}/yr")
    m3.metric("Annual savings", f"€{savings_eur:,.0f}/yr", delta=f"€{savings_eur:,.0f}")
    m4.metric("Simple payback", f"{payback} yrs" if payback else "n/a")

    st.write(f"CO₂ reduction vs baseline: **:green[{co2_savings:,.0f} kg/yr]**")

    st.divider()

    # ── Monthly electricity chart ────────────────────────────────────────────
    st.subheader("Monthly Electricity: Combined System vs. Baseline")
    months = result["months"]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Cooling – day operation",
        x=months, y=result["w_cool_day_monthly"],
        marker_color="#2E75B6"
    ))
    fig.add_trace(go.Bar(
        name="Cooling – night TES charge",
        x=months, y=result["w_cool_night_monthly"],
        marker_color="#70A9D6"
    ))
    fig.add_trace(go.Bar(
        name="DHW (after heat recovery)",
        x=months, y=result["w_dhw_monthly"],
        marker_color="#ED7D31"
    ))
    fig.add_trace(go.Scatter(
        name="Baseline (split-AC + elec. DHW)",
        x=months, y=result["w_baseline_monthly"],
        line=dict(color="#FF0000", width=2),
        marker=dict(symbol="x", size=8),
    ))
    fig.update_layout(
        barmode="stack",
        xaxis_title="Month",
        yaxis_title="Electricity (kWh)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=380,
        margin=dict(t=40, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Monthly energy flows chart ───────────────────────────────────────────
    st.subheader("Monthly Energy Flows")
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        name="Cooling demand",
        x=months, y=result["e_cool_monthly"],
        marker_color="#2E75B6"
    ))
    fig2.add_trace(go.Bar(
        name="DHW demand",
        x=months, y=result["e_dhw_monthly"],
        marker_color="#ED7D31"
    ))
    fig2.add_trace(go.Bar(
        name="DHW via heat recovery",
        x=months, y=result["e_hr_monthly"],
        marker_color="#70AD47"
    ))
    fig2.add_trace(go.Scatter(
        name="PV yield",
        x=months, y=result["e_pv_monthly"],
        mode="lines+markers",
        line=dict(color="#FFD700", width=2),
        marker=dict(symbol="diamond", size=7),
    ))
    fig2.update_layout(
        barmode="group",
        xaxis_title="Month",
        yaxis_title="Energy (kWh)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=380,
        margin=dict(t=40, b=40),
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── PDF download ──────────────────────────────────────────────────────────
    st.divider()
    pdf_bytes = build_gulf_pdf(result, climate, cost_combined, cost_baseline,
                               savings_eur, co2_savings, payback,
                               lead_name=lead_name)
    st.download_button(
        label="📄 Download Report (PDF)",
        data=pdf_bytes,
        file_name="ThermaCore_Gulf_Combined_Report.pdf",
        mime="application/pdf",
    )


# ────────────────────────────────────────────────────────────────────────────
# PDF builder for Gulf Combined System
# ────────────────────────────────────────────────────────────────────────────
def build_gulf_pdf(result, climate, cost_combined, cost_baseline,
                   savings_eur, co2_savings, payback, lead_name=""):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"],
                                 textColor=BRAND_BLUE, fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"],
                        textColor=BRAND_LIGHT, fontSize=12, spaceAfter=4)
    normal = styles["Normal"]

    story = []
    story.append(Paragraph("ThermaCore EU — Gulf Combined System Report", title_style))
    story.append(Paragraph("Confidential sizing report — planning grade only", normal))
    if lead_name:
        story.append(Paragraph(f"Prepared for: {lead_name}", normal))
    story.append(Paragraph(f"Location: {result['climate_key']}", normal))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", normal))
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_LIGHT))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("System Overview", h2))
    overview = [
        ["Parameter", "Value"],
        ["HP cooling capacity", f"{result['recommended_capacity_kw']} kW"],
        ["EER (day / night operation)", f"{result['eer_day']} / {result['eer_night']}"],
        ["TES volume", f"{result['tes_volume_l']} L"],
        ["TES night-charge fraction", f"{int(result['tes_fraction']*100)}%"],
        ["PV area", f"{result['pv_area_m2']} m²"],
        ["DHW heat recovery efficiency", f"{int(result['eta_hr']*100)}%"],
    ]
    t = Table(overview, colWidths=[9*cm, 7*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, -1), BRAND_BG),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.white),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_BG]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("Annual Energy & Financial Summary", h2))
    summary = [
        ["Metric", "Combined System", "Baseline"],
        ["Annual electricity (kWh)", f"{result['annual_electricity_kwh']:,}", f"{result['annual_baseline_kwh']:,}"],
        ["Annual running cost (EUR)", f"€{cost_combined:,.0f}", f"€{cost_baseline:,.0f}"],
        ["Annual savings (EUR)", f"€{savings_eur:,.0f}", "—"],
        ["CO2 reduction (kg/yr)", f"{co2_savings:,.0f}", "—"],
        ["Simple payback (yrs)", f"{payback}" if payback else "n/a", "—"],
    ]
    t2 = Table(summary, colWidths=[9*cm, 4.5*cm, 4.5*cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.white),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_BG]),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph(
        "Disclaimer: Planning-grade estimates only. Final design requires a full "
        "EN 12831 / ASHRAE load calculation and site survey.",
        ParagraphStyle("disc", parent=normal, textColor=BRAND_GRAY, fontSize=8)
    ))

    doc.build(story)
    return buf.getvalue()


# ────────────────────────────────────────────────────────────────────────────
# Leads
# ────────────────────────────────────────────────────────────────────────────
def save_lead(name, email):
    file_exists = os.path.isfile(LEADS_FILE)
    with open(LEADS_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["timestamp", "name", "email"])
        w.writerow([datetime.now().isoformat(), name, email])


def lead_gate():
    if st.session_state.get("lead_captured"):
        return True
    st.subheader("Please enter your details to access the sizing results.")
    with st.form("lead_form"):
        name  = st.text_input("Your name")
        email = st.text_input("Your email")
        submitted = st.form_submit_button("Get Results →")
        if submitted:
            if not name or not email:
                st.error("Please fill in both fields.")
                return False
            save_lead(name, email)
            st.session_state.lead_captured = True
            st.session_state.lead_name     = name
            st.rerun()
    return False


# ────────────────────────────────────────────────────────────────────────────
# PDF builder for standard modes
# ────────────────────────────────────────────────────────────────────────────
def build_pdf(result, econ, climate_key, application):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"],
                                 textColor=BRAND_BLUE, fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"],
                        textColor=BRAND_LIGHT, fontSize=12, spaceAfter=4)
    normal = styles["Normal"]

    story = []
    story.append(Paragraph("ThermaCore EU — Heat Pump Sizing Report", title_style))
    story.append(Paragraph("Confidential sizing report — planning grade only", normal))
    story.append(Paragraph(f"Location: {climate_key}   |   Application: {application}", normal))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", normal))
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_LIGHT))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Sizing Results", h2))
    rows = [["Parameter", "Value"]]
    skip = {"application", "climate", "recommended_model"}
    for k, v in result.items():
        if k in skip:
            continue
        label = k.replace("_", " ").capitalize()
        if isinstance(v, float):
            rows.append([label, f"{v:,.2f}"])
        elif isinstance(v, int):
            rows.append([label, f"{v:,}"])
        else:
            rows.append([label, str(v)])

    t = Table(rows, colWidths=[9*cm, 7*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.white),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_BG]),
    ]))
    story.append(t)

    if econ:
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("Financial Summary", h2))
        erows = [["Metric", "Value"]]
        for k, v in econ.items():
            label = k.replace("_", " ").capitalize()
            if v is None:
                erows.append([label, "n/a"])
            elif isinstance(v, float):
                erows.append([label, f"{v:,.2f}"])
            else:
                erows.append([label, str(v)])
        t2 = Table(erows, colWidths=[9*cm, 7*cm])
        t2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.white),
            ("FONTSIZE",   (0, 0), (-1, -1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_BG]),
        ]))
        story.append(t2)

    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph(
        "Disclaimer: Planning-grade estimates only. Final design requires a full "
        "EN 12831 load calculation and site survey.",
        ParagraphStyle("disc", parent=normal, textColor=BRAND_GRAY, fontSize=8)
    ))
    doc.build(story)
    return buf.getvalue()


# ────────────────────────────────────────────────────────────────────────────
# Sidebar
# ────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Inputs")

    climate_key = st.selectbox("📍 Location / Climate", list(CLIMATES.keys()))
    climate     = CLIMATES[climate_key]

    application = st.selectbox("🔧 Application", [
        "🏠 Space Heating",
        "🚿 Domestic Hot Water",
        "🏊 Pool Heating",
        "❄️ Space Cooling",
        "🌍 Gulf Combined System (Cooling + TES + DHW-HR + PV)",
    ])

    st.divider()

    if application == "🏠 Space Heating":
        floor_area       = st.number_input("Floor area (m²)", 50, 2000, 150, step=10)
        insulation_class = st.selectbox("Insulation class", list(INSULATION_CLASSES.keys()))
        flow_temp        = st.selectbox("Flow temperature (°C)", [35, 45, 55], index=0)
        install_cost     = st.number_input("Installation cost (€)", 0, 50000, 8000, step=500)
        existing_system  = st.selectbox("Existing system", ["Gas boiler", "Oil boiler", "Electric resistance", "None (new build)"])

    elif application == "🚿 Domestic Hot Water":
        num_persons  = st.number_input("Number of persons", 1, 20, 4)
        install_cost = st.number_input("Installation cost (€)", 0, 20000, 3000, step=500)
        existing_system = st.selectbox("Existing system", ["Gas boiler", "Electric resistance", "None (new build)"])

    elif application == "🏊 Pool Heating":
        pool_area        = st.number_input("Pool area (m²)", 10, 500, 40, step=5)
        pool_type        = st.selectbox("Pool type", list(POOL_SPECIFIC_LOSS_W_PER_M2.keys()))
        operating_months = st.slider("Operating months / year", 1, 12, 6)
        install_cost     = st.number_input("Installation cost (€)", 0, 30000, 6000, step=500)
        existing_system  = "Electric resistance"

    elif application == "❄️ Space Cooling":
        floor_area      = st.number_input("Floor area (m²)", 50, 2000, 150, step=10)
        cooling_class   = st.selectbox("Building envelope", list(COOLING_LOAD_CLASSES.keys()))
        install_cost    = st.number_input("Installation cost (€)", 0, 30000, 5000, step=500)
        existing_system = st.selectbox("Existing system", ["Gas boiler", "Electric resistance", "None (new build)"])

    elif application == "🌍 Gulf Combined System (Cooling + TES + DHW-HR + PV)":
        floor_area    = st.number_input("Floor area (m²)", 50, 2000, 200, step=10)
        cooling_class = st.selectbox("Building envelope", list(COOLING_LOAD_CLASSES.keys()))
        num_persons   = st.number_input("Number of persons (DHW)", 1, 20, 4)
        pv_area       = st.number_input("PV area (m²)", 5, 200, 25, step=5)
        tes_volume    = st.number_input("TES volume (L)", 200, 3000, 500, step=100)
        tes_fraction  = st.slider("TES night-charge fraction", 0.10, 0.80, 0.45, step=0.05,
                                  help="Fraction of daily cooling load shifted to night operation")
        eta_hr        = st.slider("DHW heat recovery efficiency", 0.30, 0.90, 0.65, step=0.05)
        install_cost  = st.number_input("System installation cost (€)", 0, 100000, 18000, step=1000)
        existing_system = "Electric resistance"

    st.divider()
    run = st.button("⚡ Calculate", type="primary", use_container_width=True)
    if run:
        st.session_state.run_calculation = True


# ────────────────────────────────────────────────────────────────────────────
# Main panel
# ────────────────────────────────────────────────────────────────────────────
if not lead_gate():
    st.stop()

lead_name = st.session_state.get("lead_name", "")

if st.session_state.get("run_calculation"):
    st.session_state.run_calculation = False   # reset for next run

    if application == "🏠 Space Heating":
        result = size_space_heating(climate_key, floor_area, insulation_class, flow_temp)
        econ   = economics(result, climate, install_cost, existing_system)
        name_greeting = f", {lead_name}" if lead_name else ""
        st.success(f"✅ Space Heating results{name_greeting}!")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Design load",     f"{result['design_load_kw']} kW")
        c2.metric("SCOP estimate",   f"{result['scop_estimate']}")
        c3.metric("Annual demand",   f"{result['annual_heat_demand_kwh']:,} kWh")
        c4.metric("Annual electricity", f"{result['annual_electricity_kwh']:,} kWh")
        st.divider()
        ca, cb = st.columns(2)
        ca.metric("Annual running cost", f"€{econ['annual_hp_running_cost_eur']:,.0f}")
        cb.metric("Annual savings vs existing", f"€{econ['annual_savings_eur']:,.0f}")
        c1b, c2b = st.columns(2)
        c1b.metric("CO₂ savings", f"{econ['annual_co2_savings_kg']:,.0f} kg/yr")
        c2b.metric("Payback", f"{econ['payback_years']} yrs" if econ['payback_years'] else "n/a")
        st.divider()
        st.info(f"Recommended buffer tank: **{result['buffer_tank_l']} L**")
        pdf_bytes = build_pdf(result, econ, climate_key, "Space Heating")
        st.download_button("📄 Download Report (PDF)", pdf_bytes,
                           "ThermaCore_SpaceHeating_Report.pdf", "application/pdf")

    elif application == "🚿 Domestic Hot Water":
        result = size_dhw(climate_key, num_persons)
        econ   = economics(result, climate, install_cost, existing_system)
        name_greeting = f", {lead_name}" if lead_name else ""
        st.success(f"✅ DHW results{name_greeting}!")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Daily demand",  f"{result['daily_demand_l']} L/day")
        c2.metric("COP estimate",  f"{result['cop_estimate']}")
        c3.metric("Annual demand", f"{result['annual_heat_demand_kwh']:,} kWh")
        c4.metric("Annual electricity", f"{result['annual_electricity_kwh']:,} kWh")
        st.divider()
        ca, cb = st.columns(2)
        ca.metric("Annual running cost", f"€{econ['annual_hp_running_cost_eur']:,.0f}")
        cb.metric("Annual savings", f"€{econ['annual_savings_eur']:,.0f}")
        st.divider()
        pdf_bytes = build_pdf(result, econ, climate_key, "Domestic Hot Water")
        st.download_button("📄 Download Report (PDF)", pdf_bytes,
                           "ThermaCore_DHW_Report.pdf", "application/pdf")

    elif application == "🏊 Pool Heating":
        result = size_pool(climate_key, pool_area, pool_type, operating_months)
        econ   = economics(result, climate, install_cost, existing_system)
        name_greeting = f", {lead_name}" if lead_name else ""
        st.success(f"✅ Pool Heating results{name_greeting}!")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Design load",   f"{result['design_load_kw']} kW")
        c2.metric("COP estimate",  f"{result['cop_estimate']}")
        c3.metric("Annual demand", f"{result['annual_heat_demand_kwh']:,} kWh")
        c4.metric("Annual electricity", f"{result['annual_electricity_kwh']:,} kWh")
        st.divider()
        ca, cb = st.columns(2)
        ca.metric("Annual running cost", f"€{econ['annual_hp_running_cost_eur']:,.0f}")
        cb.metric("Annual savings", f"€{econ['annual_savings_eur']:,.0f}")
        st.divider()
        pdf_bytes = build_pdf(result, econ, climate_key, "Pool Heating")
        st.download_button("📄 Download Report (PDF)", pdf_bytes,
                           "ThermaCore_Pool_Report.pdf", "application/pdf")

    elif application == "❄️ Space Cooling":
        result = size_cooling(climate_key, floor_area, cooling_class)
        econ   = economics(result, climate, install_cost, existing_system)
        name_greeting = f", {lead_name}" if lead_name else ""
        st.success(f"✅ Space Cooling results{name_greeting}!")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Design load",      f"{result['design_load_kw']} kW")
        c2.metric("EER estimate",     f"{result['eer_estimate']}")
        c3.metric("Annual demand",    f"{result['annual_cool_demand_kwh']:,} kWh")
        c4.metric("Annual electricity", f"{result['annual_electricity_kwh']:,} kWh")
        st.divider()
        ca, cb = st.columns(2)
        ca.metric("Annual running cost", f"€{econ['annual_hp_running_cost_eur']:,.0f}")
        cb.metric("Annual savings", f"€{econ['annual_savings_eur']:,.0f}")
        st.divider()
        pdf_bytes = build_pdf(result, econ, climate_key, "Space Cooling")
        st.download_button("📄 Download Report (PDF)", pdf_bytes,
                           "ThermaCore_Cooling_Report.pdf", "application/pdf")

    elif application == "🌍 Gulf Combined System (Cooling + TES + DHW-HR + PV)":
        result = size_gulf_combined(
            climate_key, floor_area, cooling_class, num_persons,
            pv_area_m2=pv_area, tes_volume_l=tes_volume,
            tes_fraction=tes_fraction, eta_hr=eta_hr,
        )
        _show_gulf_results(result, climate, install_cost, existing_system, lead_name)

else:
    st.info("👈 Configure your system in the sidebar, then click **Calculate**.")
