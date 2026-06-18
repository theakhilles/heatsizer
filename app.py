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
    size_space_heating, size_dhw, size_pool, size_cooling, economics,
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
        ["Space Heating", "Domestic Hot Water (DHW)", "Pool Heating", "Space Cooling"],
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

# ── Main panel ───────────────────────────────────────────────
if run:
    if not lead_gate(location, application):
        st.stop()

    # Run calculations
    if application == "Space Heating":
        result = size_space_heating(location, floor_area, insulation, flow_temp)
    elif application == "Domestic Hot Water (DHW)":
        result = size_dhw(location, num_persons)
    elif application == "Pool Heating":
        result = size_pool(location, pool_area, pool_type, operating_months)
    elif application == "Space Cooling":
        result = size_cooling(location, floor_area, cooling_class)

    econ = economics(result, climate, install_cost, existing_system)

    name_greeting = f", {st.session_state.lead_name}" if st.session_state.lead_name else ""
    st.success(f"✅ Here are your results{name_greeting}!")

    # ── Top metrics (model name hidden — show capacity class instead) ──
    col1, col2, col3, col4 = st.columns(4)
    cap_key  = "recommended_capacity_kw" if "recommended_capacity_kw" in result else "recommended_volume_l"
    cap_unit = "kW" if cap_key == "recommended_capacity_kw" else "L"

    # Derive a friendly capacity class label instead of internal model code
    cap_val = result[cap_key]
    if cap_unit == "kW":
        unit_label = f"R290 heat pump · {cap_val} kW"
    else:
        unit_label = f"R290 HP water heater · {cap_val} L"

    col1.metric("Recommended system", unit_label)
    col2.metric("Capacity", f"{cap_val} {cap_unit}")

    if "scop_estimate" in result:
        col3.metric("Estimated SCOP", result["scop_estimate"])
    elif "cop_estimate" in result:
        col3.metric("Estimated COP", result["cop_estimate"])
    elif "eer_estimate" in result:
        col3.metric("Estimated EER (cooling)", result["eer_estimate"])

    col4.metric("Indicative FOB price", f"€{result['fob_eur']:,}")

    st.divider()

    # ── Energy / Cost / CO₂ ──
    col_a, col_b, col_c = st.columns(3)
    thermal_demand = result.get("annual_heat_demand_kwh") or result.get("annual_cool_demand_kwh", 0)

    with col_a:
        st.subheader("⚡ Energy")
        st.write(f"**Annual thermal demand:** {thermal_demand:,.0f} kWh")
        st.write(f"**Annual electricity use:** {result['annual_electricity_kwh']:,.0f} kWh")
        if "design_load_kw" in result:
            st.write(f"**Design load:** {result['design_load_kw']} kW")
        if "buffer_tank_l" in result:
            st.write(f"**Recommended buffer tank:** {result['buffer_tank_l']} L")

    with col_b:
        st.subheader("💶 Running Costs")
        st.write(f"**Heat pump running cost:** €{econ['annual_hp_running_cost_eur']:,.0f} / yr")
        st.write(f"**{existing_system} running cost:** €{econ['annual_existing_cost_eur']:,.0f} / yr")
        savings = econ["annual_savings_eur"]
        if savings >= 0:
            st.write(f"**Annual savings:** :green[€{savings:,.0f} / yr]")
        else:
            st.write(f"**Annual extra cost:** :red[€{abs(savings):,.0f} / yr]")
        if econ["payback_years"]:
            st.write(f"**Simple payback:** {econ['payback_years']} years")
        else:
            st.write("**Simple payback:** n/a")

    with col_c:
        st.subheader("🌍 CO₂ Impact")
        st.write(f"**Heat pump emissions:** {econ['annual_co2_hp_kg']:,.0f} kg/yr")
        st.write(f"**{existing_system} emissions:** {econ['annual_co2_existing_kg']:,.0f} kg/yr")
        co2_savings = econ["annual_co2_savings_kg"]
        if co2_savings >= 0:
            st.write(f"**CO₂ reduction:** :green[{co2_savings:,.0f} kg/yr]")
        else:
            st.write(f"**CO₂ increase:** :red[{abs(co2_savings):,.0f} kg/yr]")

    st.divider()

    # ── Cost comparison chart ──
    st.subheader("Annual Cost Comparison")
    fig = go.Figure(data=[
        go.Bar(name="Heat pump",    x=["Annual running cost"], y=[econ["annual_hp_running_cost_eur"]],   marker_color="#2E75B6"),
        go.Bar(name=existing_system, x=["Annual running cost"], y=[econ["annual_existing_cost_eur"]], marker_color="#A6A6A6"),
    ])
    fig.update_layout(barmode="group", yaxis_title="EUR / year", height=350)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── PDF download ──
    pdf_buf = build_pdf(
        result, econ, location, application,
        existing_system, install_cost,
        st.session_state.lead_name
    )
    st.download_button(
        label="📄 Download PDF Report",
        data=pdf_buf,
        file_name=f"HeatSizer_Report_{location.replace(', ', '_').replace(' ', '_')}.pdf",
        mime="application/pdf",
        type="primary",
    )

    st.info(
        "💡 **Next step:** Contact ThermaCore EU for a full engineering quote — "
        "load calculation, hydraulic design, sourcing and commissioning. "
        "**eng.akasem@gmail.com**"
    )

else:
    if not st.session_state.lead_captured:
        st.info("👈 Enter your building details in the sidebar and click **Calculate** to get a recommendation.")
    else:
        st.info(f"👈 Adjust your inputs and click **Calculate** again.")

    st.markdown("### How this tool works")
    st.markdown(
        """
        1. **Climate data** for your location (heating/cooling degree-days, design temperatures, energy prices, CO₂ factor)
        2. **Building inputs** (floor area, insulation level, occupancy, pool size)
        3. **Sizing engine** calculates the design load and annual energy demand (degree-day method, EN 12831 methodology)
        4. **Equipment matching** selects the right R290 unit with 10% safety margin
        5. **Economics** compares running costs and CO₂ vs. your current system
        6. **PDF report** download with ThermaCore EU branding
        """
    )
    st.markdown("---")
    st.markdown(
        "**ThermaCore EU** — R290 heat pump supply, configuration & commissioning for Europe and the Gulf.  \n"
        "📧 eng.akasem@gmail.com"
    )
