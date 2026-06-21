"""
Thotec Sizer — Heat Pump Sizing & Feasibility Tool
Thotec  |  eng.akasem@gmail.com

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
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
)

from data.climate_data import CLIMATES, INSULATION_CLASSES, COOLING_LOAD_CLASSES
from calc.engine import (
    size_space_heating, size_dhw, size_pool, size_cooling,
    size_gulf_combined, economics,
    POOL_SPECIFIC_LOSS_W_PER_M2,
)

# ── Brand colours ────────────────────────────────────────────
BRAND_BLUE   = colors.HexColor("#1A2744")
BRAND_GOLD   = colors.HexColor("#C49A2A")
BRAND_LIGHT  = colors.HexColor("#2E75B6")
BRAND_GRAY   = colors.HexColor("#595959")
BRAND_BG     = colors.HexColor("#F5F0E8")

LEADS_FILE = "leads.csv"

# ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Thotec Sizer", page_icon="🌡️", layout="wide")

# ── Header ───────────────────────────────────────────────────
_col_logo, _col_title = st.columns([1, 5])
with _col_logo:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=140)
with _col_title:
    st.title("Thotec Sizer")
    st.caption("Heat pump sizing & feasibility — Europe & Gulf")
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

def _save_to_gsheets(row):
    """Write a row to Google Sheets using gspread v6 service_account_from_dict."""
    try:
        import gspread
        creds_dict = st.secrets.get("gcp_service_account", None)
        sheet_id   = st.secrets.get("LEADS_SHEET_ID", None)
        if not creds_dict or not sheet_id:
            return False, "Secrets not configured"
        # gspread v6: service_account_from_dict handles auth automatically
        creds_info = dict(creds_dict)
        # Rebuild PEM key robustly — handles all copy-paste variants
        key = creds_info.get("private_key", "")
        # Convert literal \n to real newline (common TOML paste issue)
        key = key.replace("\\n", "\n").replace("\r", "")
        # Rebuild proper PEM structure
        if "-----BEGIN" in key:
            lines = [l.strip() for l in key.replace("\\n", "\n").split("\n") if l.strip()]
            if lines and lines[0].startswith("-----BEGIN") and lines[-1].startswith("-----END"):
                header = lines[0]
                footer = lines[-1]
                body = "".join(lines[1:-1])
                wrapped = "\n".join(body[i:i+64] for i in range(0, len(body), 64))
                key = header + "\n" + wrapped + "\n" + footer + "\n"
        creds_info["private_key"] = key
        client = gspread.service_account_from_dict(creds_info)
        sheet  = client.open_by_key(sheet_id).sheet1
        # Add header row if sheet is empty
        if not sheet.get_all_values():
            sheet.append_row(["timestamp", "name", "email", "location", "application"])
        sheet.append_row(row)
        return True, None
    except Exception as e:
        return False, str(e)


def save_lead(name, email, location, application):
    """Save lead to Google Sheets (primary) and local CSV (fallback)."""
    row = [datetime.utcnow().isoformat(), name, email, location, application]
    ok, err = _save_to_gsheets(row)
    if not ok:
        st.session_state["_gsheets_err"] = err or "Unknown error"
    else:
        st.session_state.pop("_gsheets_err", None)
    # Always write local CSV as backup
    try:
        file_exists = os.path.isfile(LEADS_FILE)
        with open(LEADS_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "name", "email", "location", "application"])
            writer.writerow(row)
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
    hero_style = ParagraphStyle(
        "Hero", parent=styles["Normal"],
        textColor=BRAND_BLUE, fontSize=22, leading=26, spaceAfter=2, alignment=1
    )
    hero_label = ParagraphStyle(
        "HeroLabel", parent=styles["Normal"],
        textColor=BRAND_GRAY, fontSize=9, spaceAfter=10, alignment=1
    )
    disclaimer_style = ParagraphStyle(
        "Disc", parent=styles["Normal"],
        fontSize=8, textColor=BRAND_GRAY, leading=11
    )

    story = []
    date_str = datetime.utcnow().strftime("%d %B %Y")

    # ── Header ───────────────────────────────────────────────
    if os.path.exists("logo.png"):
        story.append(RLImage("logo.png", width=5*cm, height=2.5*cm))
        story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("Thotec — Heat Pump Savings Report", title_style))
    story.append(Paragraph("Thotec  ·  eng.akasem@gmail.com", sub_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=BRAND_BLUE, spaceAfter=10))
    story.append(Paragraph(f"<b>Prepared for:</b> {lead_name or 'Customer'}  ·  <b>Location:</b> {climate_key}  ·  <b>Date:</b> {date_str}", body_style))
    story.append(Spacer(1, 0.4*cm))

    # ── Hero savings numbers ──────────────────────────────────
    savings   = econ["annual_savings_eur"]
    co2_sav   = econ["annual_co2_savings_kg"]
    payback   = econ["payback_years"]

    hero_data = [
        [
            Paragraph(f"<b>€{savings:,.0f}</b>", hero_style),
            Paragraph(f"<b>{co2_sav:,.0f} kg</b>", hero_style),
            Paragraph(f"<b>{payback} yrs</b>" if payback else "<b>n/a</b>", hero_style),
        ],
        [
            Paragraph("Annual savings", hero_label),
            Paragraph("CO₂ reduction / yr", hero_label),
            Paragraph("Payback period", hero_label),
        ],
    ]
    hero_table = Table(hero_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    hero_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_BG),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEAFTER",     (0, 0), (1, -1), 0.5, colors.lightgrey),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(hero_table)
    story.append(Spacer(1, 0.5*cm))

    # ── Cost comparison bar (visual table) ───────────────────
    story.append(Paragraph("Annual Running Cost Comparison", sub_style))
    cur_cost = econ["annual_existing_cost_eur"]
    hp_cost  = econ["annual_hp_running_cost_eur"]
    max_cost = max(cur_cost, hp_cost, 1)
    bar_w    = 8*cm
    cur_bar  = max(cur_cost / max_cost * bar_w, 0.2*cm)
    hp_bar   = max(hp_cost  / max_cost * bar_w, 0.2*cm)

    bar_data = [
        [Paragraph(f"<b>{existing_system}</b>", body_style),
         Table([[""]], colWidths=[cur_bar], rowHeights=[0.6*cm],
               style=[("BACKGROUND",(0,0),(-1,-1),BRAND_GOLD)]),
         Paragraph(f"<b>€{cur_cost:,.0f}/yr</b>", body_style)],
        [Paragraph("<b>Heat pump</b>", body_style),
         Table([[""]], colWidths=[hp_bar], rowHeights=[0.6*cm],
               style=[("BACKGROUND",(0,0),(-1,-1),BRAND_BLUE)]),
         Paragraph(f"<b>€{hp_cost:,.0f}/yr</b>", body_style)],
    ]
    bar_table = Table(bar_data, colWidths=[4*cm, bar_w + 0.5*cm, 3*cm])
    bar_table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (0, -1), 0),
    ]))
    story.append(bar_table)
    story.append(Spacer(1, 0.5*cm))

    # ── System info (brief) ───────────────────────────────────
    story.append(Paragraph("Recommended System", sub_style))
    cap_key  = "recommended_capacity_kw" if "recommended_capacity_kw" in result else "recommended_volume_l"
    cap_unit = "kW" if cap_key == "recommended_capacity_kw" else "L"
    cap_val  = result[cap_key]
    story.append(Paragraph(
        f"R290 air-source heat pump · <b>{cap_val} {cap_unit}</b> capacity · "
        f"Application: {application}",
        body_style
    ))
    if install_cost:
        story.append(Paragraph(f"Estimated installed cost: <b>€{install_cost:,}</b>", body_style))
    story.append(Spacer(1, 0.5*cm))

    # ── Next steps ────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_LIGHT, spaceAfter=8))
    story.append(Paragraph("Get a Detailed Quote", sub_style))
    story.append(Paragraph(
        "This is a planning-grade estimate. Contact Thotec for a full engineering proposal:",
        body_style
    ))
    for item in [
        "Detailed EN 12831 heat load calculation",
        "Equipment sourcing & supply from certified manufacturers",
        "Installation coordination and commissioning",
        "Project simulation and performance guarantee",
    ]:
        story.append(Paragraph(f"• {item}", body_style))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        "<b>Ahmed Abouelkasem  ·  Thotec  ·  eng.akasem@gmail.com</b>",
        body_style
    ))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Paragraph(
        f"Generated by Thotec Sizer on {date_str}. Planning-grade estimates based on degree-day "
        "methods and representative equipment data. Not a substitute for a full EN 12831 calculation.",
        disclaimer_style
    ))

    doc.build(story)
    buf.seek(0)
    return buf

# ── Standard results display (savings-first) ────────────────
def _show_standard_results(result, econ, application, existing_system,
                           install_cost, lead_name, climate, location):
    name_tag = f", {lead_name}" if lead_name else ""
    st.success(f"✅ Your results are ready{name_tag}!")

    # System line
    if "recommended_capacity_kw" in result:
        sys_desc = f"Air-source heat pump · **{result['recommended_capacity_kw']} kW** capacity"
    else:
        sys_desc = f"Heat pump water heater · **{result['recommended_volume_l']} L** tank"
    st.markdown(f"🔧 **Recommended system:** {sys_desc}")
    st.divider()

    # Hero savings metrics
    savings = econ["annual_savings_eur"]
    co2_sav = econ["annual_co2_savings_kg"]
    payback = econ["payback_years"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Annual savings",  f"€{savings:,.0f}/yr")
    c2.metric("⚡ HP electricity",  f"{result['annual_electricity_kwh']:,} kWh/yr")
    c3.metric("🌱 CO₂ reduction",   f"{co2_sav:,.0f} kg/yr")
    c4.metric("📅 Payback period",  f"{payback} yrs" if payback else "n/a")

    # Cost comparison chart
    cur = econ["annual_existing_cost_eur"]
    hp  = econ["annual_hp_running_cost_eur"]
    fig = go.Figure(data=[go.Bar(
        x=[f"Current ({existing_system})", "With Heat Pump"],
        y=[cur, hp],
        marker_color=[BRAND_GOLD.hexval() if hasattr(BRAND_GOLD, "hexval") else "#C49A2A", "#1A2744"],
        text=[f"€{cur:,.0f}/yr", f"€{hp:,.0f}/yr"],
        textposition="outside",
        width=0.4,
    )])
    fig.update_layout(
        title="Annual running cost",
        yaxis_title="€ / year",
        height=300,
        margin=dict(t=40, b=20, l=20, r=20),
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_traces(marker_color=["#C49A2A", "#1A2744"])
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    pdf = build_pdf(result, econ, location, application, existing_system, install_cost, lead_name)
    fname = application.split("(")[0].strip().replace(" ", "_")
    st.download_button("📄 Download Report (PDF)", pdf,
                       f"Thotec_{fname}_Report.pdf", "application/pdf")


# ── Gulf Combined System results ─────────────────────────────
def _show_gulf_results(result, climate, install_cost, existing_system, lead_name):
    name_greeting = f", {lead_name}" if lead_name else ""

    # ── Compute savings ──────────────────────────────────────────────────────
    elec_price    = climate["electricity_price"]
    cost_combined = result["annual_electricity_kwh"] * elec_price
    cost_baseline = result["annual_baseline_kwh"] * elec_price
    savings_eur   = cost_baseline - cost_combined
    co2_combined  = result["annual_electricity_kwh"] * climate["grid_co2_kg_per_kwh"]
    co2_baseline  = result["annual_baseline_kwh"] * climate["grid_co2_kg_per_kwh"]
    co2_savings   = co2_baseline - co2_combined
    payback       = round(install_cost / savings_eur, 1) if savings_eur > 0 and install_cost > 0 else None

    st.success(f"✅ Your Gulf Combined System results{name_greeting}!")
    st.markdown(f"🔧 **Recommended system:** Air-source cooling HP · **{result['recommended_capacity_kw']} kW** · TES {result['tes_volume_l']} L · PV {result['pv_area_m2']} m²")
    st.divider()

    # ── Hero savings metrics ─────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 Annual savings",   f"€{savings_eur:,.0f}/yr")
    m2.metric("⚡ Energy saved",     f"{result['annual_savings_kwh']:,} kWh/yr")
    m3.metric("🌱 CO₂ reduction",    f"{co2_savings:,.0f} kg/yr")
    m4.metric("📅 Payback period",   f"{payback} yrs" if payback else "n/a")

    # ── Cost comparison chart ────────────────────────────────────────────────
    fig_cmp = go.Figure(data=[go.Bar(
        x=["Current (Split-AC + Elec. DHW)", "Thotec Combined System"],
        y=[cost_baseline, cost_combined],
        marker_color=["#C49A2A", "#1A2744"],
        text=[f"€{cost_baseline:,.0f}/yr", f"€{cost_combined:,.0f}/yr"],
        textposition="outside",
        width=0.4,
    )])
    fig_cmp.update_layout(
        title="Annual running cost",
        yaxis_title="€ / year",
        height=300,
        margin=dict(t=40, b=20, l=20, r=20),
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_cmp, use_container_width=True)
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
        file_name="Thotec_Gulf_Combined_Report.pdf",
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
                            topMargin=2.5*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("gtitle", parent=styles["Title"],
                                 textColor=BRAND_BLUE, fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle("gh2", parent=styles["Heading2"],
                        textColor=BRAND_LIGHT, fontSize=12, spaceAfter=4)
    body_style = ParagraphStyle("gbody", parent=styles["Normal"],
                                fontSize=10, leading=14, spaceAfter=6)
    disc_style = ParagraphStyle("gdisc", parent=styles["Normal"],
                                textColor=BRAND_GRAY, fontSize=8)

    story = []
    if os.path.exists("logo.png"):
        story.append(RLImage("logo.png", width=5*cm, height=2.5*cm))
        story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("Thotec — Gulf Combined System Report", title_style))
    story.append(Paragraph("Thotec · eng.akasem@gmail.com", body_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=BRAND_BLUE, spaceAfter=10))
    if lead_name:
        story.append(Paragraph(f"<b>Prepared for:</b> {lead_name}", body_style))
    story.append(Paragraph(f"<b>Location:</b> {result['climate_key']}", body_style))
    story.append(Paragraph(f"<b>Generated:</b> {datetime.utcnow().strftime('%d %B %Y')}", body_style))
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("System Configuration", h2))
    overview = [
        ["Parameter", "Value"],
        ["HP cooling capacity",          f"{result['recommended_capacity_kw']} kW"],
        ["EER (day / night operation)",  f"{result['eer_day']} / {result['eer_night']}"],
        ["TES tank volume",              f"{result['tes_volume_l']} L"],
        ["TES night-charge fraction",    f"{int(result['tes_fraction']*100)}%"],
        ["PV area",                      f"{result['pv_area_m2']} m2"],
        ["DHW heat recovery",            f"{int(result['eta_hr']*100)}%"],
    ]
    t = Table(overview, colWidths=[9*cm, 8*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR",      (0, 0), (-1, 0), colors.white),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_BG]),
        ("GRID",           (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("TOPPADDING",     (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 6),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    story.append(Paragraph("Annual Energy & Financial Summary", h2))
    summary = [
        ["Metric",                   "Combined System",                       "Baseline"],
        ["Annual electricity (kWh)", f"{result['annual_electricity_kwh']:,}", f"{result['annual_baseline_kwh']:,}"],
        ["Annual running cost",      f"EUR {cost_combined:,.0f}",             f"EUR {cost_baseline:,.0f}"],
        ["Annual savings",           f"EUR {savings_eur:,.0f}",               "n/a"],
        ["CO2 reduction (kg/yr)",    f"{co2_savings:,.0f}",                   "n/a"],
        ["Simple payback (yrs)",     f"{payback}" if payback else "n/a",      "n/a"],
    ]
    t2 = Table(summary, colWidths=[8*cm, 4.5*cm, 4.5*cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR",      (0, 0), (-1, 0), colors.white),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_BG]),
        ("GRID",           (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("TOPPADDING",     (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 6),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Paragraph(
        "Planning-grade estimates only. Not a substitute for a full EN 12831 / ASHRAE calculation.",
        disc_style
    ))
    doc.build(story)
    buf.seek(0)
    return buf


# ────────────────────────────────────────────────────────────────────────────
# Main panel
# ────────────────────────────────────────────────────────────────────────────
if not lead_gate(location, application):
    st.stop()

lead_name = st.session_state.get("lead_name", "")

# Show Google Sheets error if any (persists across rerun)
if "_gsheets_err" in st.session_state:
    st.warning(f"⚠️ Google Sheets error: {st.session_state['_gsheets_err']}")

if st.session_state.get("run_calculation"):
    st.session_state.run_calculation = False

    if application == "Space Heating":
        result = size_space_heating(location, floor_area, insulation, flow_temp)
        econ   = economics(result, climate, install_cost, existing_system)
        _show_standard_results(result, econ, application, existing_system,
                               install_cost, lead_name, climate, location)

    elif application == "Domestic Hot Water (DHW)":
        result = size_dhw(location, num_persons)
        econ   = economics(result, climate, install_cost, existing_system)
        _show_standard_results(result, econ, application, existing_system,
                               install_cost, lead_name, climate, location)

    elif application == "Pool Heating":
        result = size_pool(location, pool_area, pool_type, operating_months)
        econ   = economics(result, climate, install_cost, existing_system)
        _show_standard_results(result, econ, application, existing_system,
                               install_cost, lead_name, climate, location)

    elif application == "Space Cooling":
        result = size_cooling(location, floor_area, cooling_class)
        econ   = economics(result, climate, install_cost, existing_system)
        _show_standard_results(result, econ, application, existing_system,
                               install_cost, lead_name, climate, location)

    elif application == "\U0001f30d Gulf Combined System (Cooling + TES + DHW-HR + PV)":
        result = size_gulf_combined(
            location, floor_area, cooling_class, num_persons,
            pv_area_m2=pv_area, tes_volume_l=tes_volume,
            tes_fraction=tes_fraction, eta_hr=eta_hr,
        )
        _show_gulf_results(result, climate, install_cost, existing_system, lead_name)

else:
    st.info("\U0001f448 Configure your system in the sidebar, then click **Calculate**.")
