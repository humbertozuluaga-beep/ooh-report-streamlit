import streamlit as st
import pandas as pd
import datetime
import os
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy.orm import Session
from database import (
    init_db, get_db_session, save_campaign_to_db, save_performance_to_db,
    Campaign, OOHInventory, Performance, clean_numeric
)

# Set page configuration with a premium icon and layouts
st.set_page_config(
    page_title="OOH Campaign & Performance Hub",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling (modern colors, polished tables, interactive borders, glassmorphism)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Header Gradient styling */
    .header-container {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 2.5rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
    }
    
    .header-title {
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.5px;
    }
    
    .header-subtitle {
        font-size: 1.1rem;
        opacity: 0.85;
        margin-top: 0.5rem;
    }
    
    /* Elegant metric card styling */
    .metric-card {
        background-color: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        border: 1px solid #f0f2f6;
        transition: all 0.3s ease;
        text-align: center;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1);
        border-color: #2a5298;
    }
    
    .metric-value {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1e3c72;
        margin-bottom: 0.2rem;
    }
    
    .metric-label {
        font-size: 0.9rem;
        color: #64748b;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Active Connection status pill */
    .conn-status {
        display: inline-flex;
        align-items: center;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    
    .status-connected {
        background-color: #d1fae5;
        color: #065f46;
    }
    
    .status-disconnected {
        background-color: #fee2e2;
        color: #991b1b;
    }
    
    .status-dot {
        width: 8px;
        height: 8px;
        background-color: currentColor;
        border-radius: 50%;
        margin-right: 0.5rem;
        display: inline-block;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { opacity: 0.5; }
        50% { opacity: 1; }
        100% { opacity: 0.5; }
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# DATABASE INITIALIZATION
# -------------------------------------------------------------
db_connected = False
try:
    init_db()
    db_connected = True
except Exception as e:
    st.sidebar.error(f"⚠️ Database Connection Error: {e}")

# -------------------------------------------------------------
# PARSING UTILITIES
# -------------------------------------------------------------
def parse_date(date_val):
    if pd.isna(date_val) or date_val is None:
        return None
    if isinstance(date_val, (int, float)):
        return pd.to_datetime(date_val, unit='D', origin='1899-12-30').date()
    if isinstance(date_val, datetime.datetime):
        return date_val.date()
    if hasattr(date_val, 'date'):
        return date_val.date()
    try:
        return pd.to_datetime(str(date_val).strip()).date()
    except Exception:
        return None

def find_header_row(df, keyword="Reference ID"):
    for idx, row in df.iterrows():
        # Match if the keyword is inside any cell of the row (case-insensitive)
        if any(isinstance(val, str) and keyword.lower() in val.lower() for val in row):
            return idx
    return None

def extract_campaign_metadata(df):
    """
    Extrae todos los campos de Campaign Details, Buyer Details y Estimation (OOH only)
    de la hoja 'Campaign Plan'. Los campos están distribuidos en 3 grupos de columnas:
      col0→col1 (Campaign Details), col2→col3 (Buyer Details), col4→col5 (Estimation).
    """
    # (label_parcial, col_label, col_valor, clave_en_meta)
    # Layout real del Excel (verificado): col vacía entre cada sección
    #   col0→col1  = Campaign Details
    #   col3→col4  = Buyer Details
    #   col6→col7  = Estimation (OOH only)
    FIELD_MAP = [
        # --- Campaign Details (col 0 → col 1) ---
        ("Campaign Name",                   0, 1, "name"),
        ("Deal ID",                         0, 1, "id"),
        ("Created On",                      0, 1, "created_on"),
        ("Start Date",                      0, 1, "start_date"),
        ("End Date",                        0, 1, "end_date"),
        ("Media Type",                      0, 1, "media_type"),
        ("Total Cost (OOH)",                0, 1, "total_cost_ooh"),
        ("MENOS BENEFICIO",                 0, 1, "net_cost"),
        # --- Buyer Details (col 3 → col 4) ---
        ("Created By",                      3, 4, "created_by"),
        ("Company",                         3, 4, "company"),
        ("Email Address",                   3, 4, "email"),
        ("DSP",                             3, 4, "dsp"),
        ("Seat ID",                         3, 4, "seat_id"),
        ("Brand",                           3, 4, "brand"),
        ("Product",                         3, 4, "product"),
        # --- Estimation OOH only (col 6 → col 7) ---
        ("Audience Segment",                6, 7, "audience_segment"),
        ("Total OOH Impressions",           6, 7, "total_ooh_impressions_planned"),
        ("Unique Reach",                    6, 7, "unique_reach_planned"),
        ("Average Frequency",               6, 7, "average_frequency"),
        ("eCPM (MXN)",                      6, 7, "ecpm_mxn_planned"),
        ("Campaign Audience Concentration", 6, 7, "campaign_audience_concentration"),
        ("Share of Time",                   6, 7, "share_of_time"),
        ("Ad Plays",                        6, 7, "ad_plays_planned"),
    ]

    meta = {key: None for _, _, _, key in FIELD_MAP}
    found = set()

    for _, row in df.iterrows():
        row_vals = list(row)
        for label, col_lbl, col_val, key in FIELD_MAP:
            if key in found:
                continue
            cell = row_vals[col_lbl] if col_lbl < len(row_vals) else None
            if isinstance(cell, str) and label.lower() in cell.lower():
                val = row_vals[col_val] if col_val < len(row_vals) else None
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    meta[key] = val
                    found.add(key)

    # Convertir fechas
    for k in ("start_date", "end_date", "created_on"):
        if meta[k] is not None:
            meta[k] = parse_date(meta[k])

    # Convertir numéricos
    for k in ("total_cost_ooh", "net_cost", "total_ooh_impressions_planned",
              "unique_reach_planned", "average_frequency", "ecpm_mxn_planned",
              "campaign_audience_concentration"):
        if meta[k] is not None:
            meta[k] = clean_numeric(meta[k])

    # Fallback: si Campaign Name está vacío usar Deal ID
    name = meta.get("name")
    if name is None or (isinstance(name, float) and pd.isna(name)) or str(name).strip() == "":
        meta["name"] = meta.get("id")

    return meta

def _parse_sheet_by_ref_id(xl, sheet_name):
    """
    Parsea una hoja buscando la fila con 'Reference ID' como header.
    Retorna DataFrame limpio o None si la hoja no existe / no tiene Reference ID.
    """
    if sheet_name not in xl.sheet_names:
        return None
    df_raw = xl.parse(sheet_name, header=None)
    hdr_idx = find_header_row(df_raw, "Reference ID")
    if hdr_idx is None:
        return None
    df = xl.parse(sheet_name, skiprows=hdr_idx)
    df = df.dropna(subset=["Reference ID"])
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    return df


def parse_campaign_excel(file):
    """
    Parsea el archivo de campaña aprobada.
    Hace un triple merge por Reference ID entre:
      1. Campaign Plan  → Inventory Planning (datos base del inventario)
      2. Inventory Details → enriquece con formato, ubicación, técnicos, etc.
      3. Costing         → agrega Media Cost y Total Cost por pantalla
    Retorna (metadata_dict, df_merged_inventory).
    """
    xl = pd.ExcelFile(file)

    # 1. Metadatos de la campaña
    df_plan_raw = xl.parse("Campaign Plan", header=None)
    metadata = extract_campaign_metadata(df_plan_raw)

    if not metadata["id"]:
        raise ValueError("No se encontró Campaign ID / Deal ID en la hoja 'Campaign Plan'.")

    # 2. Inventario base desde Campaign Plan
    header_idx = find_header_row(df_plan_raw, "Reference ID")
    if header_idx is None:
        raise ValueError("No se encontró la columna 'Reference ID' en la hoja 'Campaign Plan'.")

    df_base = xl.parse("Campaign Plan", skiprows=header_idx)
    df_base = df_base.dropna(subset=["Reference ID"])
    df_base.columns = [str(c).strip() for c in df_base.columns]
    df_base = df_base.loc[:, ~df_base.columns.str.contains('^Unnamed')]

    # 3. Inventory Details — todas las columnas nuevas
    df_inv_details = _parse_sheet_by_ref_id(xl, "Inventory Details")

    # 4. Costing — Media Cost y Total Cost por Reference ID
    df_costing = _parse_sheet_by_ref_id(xl, "Costing")

    # 5. Triple merge izquierdo sobre Reference ID
    merged = df_base.copy()

    if df_inv_details is not None:
        # Excluir Billboard Name (puede diferir) y columnas ya presentes
        extra_inv_cols = ['Reference ID'] + [
            c for c in df_inv_details.columns
            if c not in merged.columns and c != 'Billboard Name'
        ]
        merged = pd.merge(merged, df_inv_details[extra_inv_cols], on="Reference ID", how="left")

    if df_costing is not None:
        extra_cost_cols = ['Reference ID'] + [
            c for c in df_costing.columns
            if c not in merged.columns and c != 'Billboard Name'
        ]
        merged = pd.merge(merged, df_costing[extra_cost_cols], on="Reference ID", how="left")

    return metadata, merged

# -------------------------------------------------------------
# STREAMLIT SIDEBAR SECTION
# -------------------------------------------------------------
st.sidebar.markdown("<h2 style='text-align: center; color: #1e3c72; font-weight: 700;'>🎯 Navigation & Config</h2>", unsafe_allow_html=True)

# Connection indicator
if db_connected:
    st.sidebar.markdown(
        '<div class="conn-status status-connected"><span class="status-dot"></span>Connected to Postgres</div>',
        unsafe_allow_html=True
    )
else:
    st.sidebar.markdown(
        '<div class="conn-status status-disconnected"><span class="status-dot"></span>Postgres Disconnected</div>',
        unsafe_allow_html=True
    )

st.sidebar.markdown("---")

# Query general stats for the sidebar
total_campaigns = 0
total_locations = 0
total_perf_records = 0
active_campaign_list = []

if db_connected:
    try:
        db = get_db_session()
        total_campaigns = db.query(Campaign).count()
        total_locations = db.query(OOHInventory).count()
        total_perf_records = db.query(Performance).count()
        
        # Load campaigns for selectbox selection
        active_campaign_list = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
        db.close()
    except Exception as e:
        pass

st.sidebar.markdown("### 📊 Platform Statistics")
col_side1, col_side2 = st.sidebar.columns(2)
with col_side1:
    st.markdown(f"""
    <div style='background: #f8fafc; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;'>
        <span style='font-size: 1.2rem; font-weight: 700; color: #1e3c72;'>{total_campaigns}</span><br>
        <span style='font-size: 0.75rem; color: #64748b;'>Campaigns</span>
    </div>
    """, unsafe_allow_html=True)
with col_side2:
    st.markdown(f"""
    <div style='background: #f8fafc; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;'>
        <span style='font-size: 1.2rem; font-weight: 700; color: #1e3c72;'>{total_locations}</span><br>
        <span style='font-size: 0.75rem; color: #64748b;'>Inventories</span>
    </div>
    """, unsafe_allow_html=True)

st.sidebar.markdown(f"""
<div style='background: #f8fafc; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center; margin-top: 10px;'>
    <span style='font-size: 1.4rem; font-weight: 700; color: #1e3c72;'>{total_perf_records:,}</span><br>
    <span style='font-size: 0.8rem; color: #64748b;'>Performance Metric Rows</span>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **Upload Workflow:**\n\n"
    "1. Go to **📥 Process Campaign Details** tab, upload an approved campaign sheet (`.xlsx`) to set up/refresh the campaign and OOH inventory details in the database.\n\n"
    "2. Go to **📊 Process Performance Data** tab, select the active campaign, and upload multiple performance sheets (`.xlsx`) to append daily metrics."
)

# -------------------------------------------------------------
# MAIN APP HEADER
# -------------------------------------------------------------
st.markdown(
    '<div class="header-container">'
    '<h1 class="header-title">OOH Campaign Management & Reporting Hub</h1>'
    '<div class="header-subtitle">Ingest, parse, and analyze Out-Of-Home programmatic campaign details and performance sheets in a centralized dashboard.</div>'
    '</div>',
    unsafe_allow_html=True
)

# Tabs definitions
tab_upload_camp, tab_upload_perf, tab_dashboard = st.tabs([
    "📥 Ingest Campaign Details",
    "📊 Ingest Performance Metrics",
    "📈 Performance Reporting Dashboard"
])

# -------------------------------------------------------------
# TAB 1: UPLOAD & PROCESS CAMPAIGN DETAILS
# -------------------------------------------------------------
with tab_upload_camp:
    st.markdown("### 📝 Upload Approved Campaign Sheet")
    st.write(
        "Upload a single approved campaign `.xlsx` file. This script will extract campaign "
        "metadata (Deal ID, Name, Start & End dates) and write its list of OOH inventories into the database."
    )
    
    campaign_file = st.file_uploader(
        "Choose Approved Campaign Details Excel File",
        type=["xlsx"],
        key="camp_uploader_box"
    )
    
    if campaign_file is not None:
        try:
            with st.spinner("Analyzing spreadsheet..."):
                metadata, df_inventory = parse_campaign_excel(campaign_file)
            
            st.success("✅ Excel file successfully parsed!")

            def _val(v, fmt=None):
                """Formatea un valor para display, retorna '—' si es None."""
                if v is None:
                    return "—"
                if fmt == "currency" and isinstance(v, (int, float)):
                    return f"MXN ${v:,.2f}"
                if fmt == "number" and isinstance(v, (int, float)):
                    return f"{v:,.0f}"
                return str(v)

            # --- Sección 1: Campaign Details ---
            st.markdown("#### 📋 Campaign Details")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(f"<div class='metric-card'><div class='metric-value' style='font-size:1rem;word-break:break-all'>{_val(metadata['id'])}</div><div class='metric-label'>Deal ID</div></div>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<div class='metric-card'><div class='metric-value' style='font-size:1.1rem'>{_val(metadata['name'])}</div><div class='metric-label'>Campaign Name</div></div>", unsafe_allow_html=True)
            with c3:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['start_date'])}</div><div class='metric-label'>Start Date</div></div>", unsafe_allow_html=True)
            with c4:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['end_date'])}</div><div class='metric-label'>End Date</div></div>", unsafe_allow_html=True)

            c5, c6, c7, c8 = st.columns(4)
            with c5:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['created_on'])}</div><div class='metric-label'>Created On</div></div>", unsafe_allow_html=True)
            with c6:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['media_type'])}</div><div class='metric-label'>Media Type</div></div>", unsafe_allow_html=True)
            with c7:
                st.markdown(f"<div class='metric-card'><div class='metric-value' style='font-size:1.1rem'>{_val(metadata['total_cost_ooh'], 'currency')}</div><div class='metric-label'>Total Cost (OOH)</div></div>", unsafe_allow_html=True)
            with c8:
                st.markdown(f"<div class='metric-card'><div class='metric-value' style='font-size:1.1rem'>{_val(metadata['net_cost'], 'currency')}</div><div class='metric-label'>Net Cost (–8%)</div></div>", unsafe_allow_html=True)

            st.markdown("---")

            # --- Sección 2: Buyer Details ---
            st.markdown("#### 🧑‍💼 Buyer Details")
            b1, b2, b3, b4 = st.columns(4)
            with b1:
                st.markdown(f"<div class='metric-card'><div class='metric-value' style='font-size:1.1rem'>{_val(metadata['created_by'])}</div><div class='metric-label'>Created By</div></div>", unsafe_allow_html=True)
            with b2:
                st.markdown(f"<div class='metric-card'><div class='metric-value' style='font-size:1.1rem'>{_val(metadata['company'])}</div><div class='metric-label'>Company</div></div>", unsafe_allow_html=True)
            with b3:
                st.markdown(f"<div class='metric-card'><div class='metric-value' style='font-size:0.9rem;word-break:break-all'>{_val(metadata['email'])}</div><div class='metric-label'>Email</div></div>", unsafe_allow_html=True)
            with b4:
                st.markdown(f"<div class='metric-card'><div class='metric-value' style='font-size:1.1rem'>{_val(metadata['dsp'])}</div><div class='metric-label'>DSP</div></div>", unsafe_allow_html=True)

            b5, b6, b7, b8 = st.columns(4)
            with b5:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['seat_id'])}</div><div class='metric-label'>Seat ID</div></div>", unsafe_allow_html=True)
            with b6:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['brand'])}</div><div class='metric-label'>Brand</div></div>", unsafe_allow_html=True)
            with b7:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['product'])}</div><div class='metric-label'>Product</div></div>", unsafe_allow_html=True)
            with b8:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['ad_plays_planned'])}</div><div class='metric-label'>Ad Plays (Planned)</div></div>", unsafe_allow_html=True)

            st.markdown("---")

            # --- Sección 3: Estimation (OOH only) ---
            st.markdown("#### 📊 Estimation (OOH only)")
            e1, e2, e3, e4 = st.columns(4)
            with e1:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['audience_segment'])}</div><div class='metric-label'>Audience Segment</div></div>", unsafe_allow_html=True)
            with e2:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['total_ooh_impressions_planned'], 'number')}</div><div class='metric-label'>Total OOH Impressions</div></div>", unsafe_allow_html=True)
            with e3:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['unique_reach_planned'], 'number')}</div><div class='metric-label'>Unique Reach</div></div>", unsafe_allow_html=True)
            with e4:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['average_frequency'])}</div><div class='metric-label'>Avg Frequency</div></div>", unsafe_allow_html=True)

            e5, e6, e7, _ = st.columns(4)
            with e5:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['ecpm_mxn_planned'], 'currency')}</div><div class='metric-label'>eCPM (MXN)</div></div>", unsafe_allow_html=True)
            with e6:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['campaign_audience_concentration'])}</div><div class='metric-label'>Audience Concentration</div></div>", unsafe_allow_html=True)
            with e7:
                st.markdown(f"<div class='metric-card'><div class='metric-value'>{_val(metadata['share_of_time'])}</div><div class='metric-label'>Share of Time (SOT)</div></div>", unsafe_allow_html=True)

            st.markdown("---")
            
            # Display inventory preview
            st.markdown(f"#### 📋 Parsed Inventory Locations ({len(df_inventory)} found)")
            st.dataframe(df_inventory.head(10), use_container_width=True)
            
            if len(df_inventory) > 10:
                st.info(f"Showing first 10 of {len(df_inventory)} inventory records. Click header cells to sort.")
                
            # Submit to DB button
            if not db_connected:
                st.warning("⚠️ Database is not connected. Fix the Postgres connection to save data.")
            else:
                if st.button("🚀 Write Campaign & Inventory to Database", type="primary", use_container_width=True):
                    with st.spinner("Connecting and writing transaction to database..."):
                        db = get_db_session()
                        try:
                            inventory_records = df_inventory.to_dict(orient='records')

                            save_campaign_to_db(
                                db=db,
                                metadata=metadata,
                                inventory_records=inventory_records
                            )
                            st.balloons()
                            st.success(f"🎉 Campaña '{metadata['name']}' y sus {len(inventory_records)} inventarios guardados/actualizados.")
                            
                            # Cache the uploaded Campaign ID in session state for ease of use in Tab 2
                            st.session_state["last_uploaded_campaign_id"] = metadata["id"]
                            st.session_state["campaign_just_uploaded"] = True
                            
                            # Rerun to update sidebar statistics
                            st.rerun()
                        except Exception as ex:
                            db.rollback()
                            st.error(f"❌ Database Write Error: {ex}")
                        finally:
                            db.close()
                            
        except Exception as e:
            st.error(f"❌ Failed to parse Campaign details: {e}")

# -------------------------------------------------------------
# TAB 2: UPLOAD & PROCESS PERFORMANCE DATA
# -------------------------------------------------------------
with tab_upload_perf:
    st.markdown("### 📊 Ingest Performance Sheets")
    st.write(
        "Upload one or multiple performance sheet excel files (representing impressions and ad play reports) "
        "corresponding to your campaigns. They will be written into the `performance` table."
    )
    
    if not db_connected:
        st.warning("⚠️ Database connection required to process performance reports.")
    elif len(active_campaign_list) == 0:
        st.warning("⚠️ No active campaigns found in the database. Please upload and save a Campaign file first under the first tab.")
    else:
        # Determine default index
        default_index = 0
        last_uploaded_id = st.session_state.get("last_uploaded_campaign_id")
        
        campaign_ids = [c.id for c in active_campaign_list]
        campaign_labels = [f"{c.name} ({c.id})" for c in active_campaign_list]
        
        if last_uploaded_id in campaign_ids:
            default_index = campaign_ids.index(last_uploaded_id)
            
        selected_campaign_index = st.selectbox(
            "Select Campaign to associate with these performance files:",
            options=range(len(campaign_labels)),
            format_func=lambda idx: campaign_labels[idx],
            index=default_index
        )
        
        target_campaign_id = campaign_ids[selected_campaign_index]
        target_campaign_name = active_campaign_list[selected_campaign_index].name
        
        st.markdown(f"**Target Linkage:** Performance files will be mapped to Campaign: `{target_campaign_name}` (`{target_campaign_id}`).")
        
        performance_files = st.file_uploader(
            "Choose Performance / Impressions Excel Sheets (Multiple Allowed)",
            type=["xlsx"],
            accept_multiple_files=True,
            key="perf_uploader_box"
        )
        
        if performance_files and len(performance_files) > 0:
            st.markdown(f"#### 🔍 Validation & Import Queue ({len(performance_files)} files)")
            
            # Start dynamic ingestion
            if st.button("📥 Parse and Import Performance Files", type="primary", use_container_width=True):
                db = get_db_session()
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                success_count = 0
                total_rows_inserted = 0
                
                try:
                    for idx, pf in enumerate(performance_files):
                        status_text.text(f"Processing ({idx+1}/{len(performance_files)}): {pf.name}...")
                        
                        # Read file
                        xl = pd.ExcelFile(pf)
                        if "MAX Line Item Report" not in xl.sheet_names:
                            st.error(f"❌ '{pf.name}' is missing the required sheet name 'MAX Line Item Report'. Skipped.")
                            continue
                            
                        # Load data
                        df_perf = xl.parse("MAX Line Item Report")

                        # Solo se requiere una columna Date para anclar los datos
                        if 'Date' not in df_perf.columns:
                            st.error(f"❌ '{pf.name}' no tiene columna 'Date'. Omitido.")
                            continue
                        
                        # Save to database (retorna 0 si el archivo ya fue importado)
                        rows_saved = save_performance_to_db(db, target_campaign_id, df_perf, pf.name)
                        if rows_saved == 0:
                            st.warning(f"⚠️ '{pf.name}' ya fue importado anteriormente para esta campaña. Omitido.")
                            continue
                        total_rows_inserted += rows_saved
                        success_count += 1
                        
                        # Update progress
                        progress_bar.progress((idx + 1) / len(performance_files))
                    
                    status_text.text("Import completed!")
                    
                    if success_count > 0:
                        st.balloons()
                        st.success(f"🎉 Success! Ingested {success_count} files successfully, writing {total_rows_inserted:,} metric rows associated with campaign '{target_campaign_name}'.")
                        
                        # Rerun to update counts
                        st.rerun()
                    else:
                        st.error("No files could be parsed or imported. Check validation messages above.")
                        
                except Exception as db_ex:
                    db.rollback()
                    st.error(f"❌ Database error encountered during batch insert: {db_ex}")
                finally:
                    db.close()

# -------------------------------------------------------------
# TAB 3: REPORTS & ANALYTICS DASHBOARD
# -------------------------------------------------------------
with tab_dashboard:
    st.markdown("### 📈 Interactive Reports & Campaign Performance Dashboard")
    
    if not db_connected:
        st.warning("⚠️ Please connect to PostgreSQL to load reports.")
    elif len(active_campaign_list) == 0:
        st.info("💡 There are currently no campaigns in the database. Ingest and save campaigns to generate analytics!")
    else:
        # Load and select campaign
        campaign_ids = [c.id for c in active_campaign_list]
        campaign_labels = [f"{c.name} ({c.id})" for c in active_campaign_list]
        
        selected_rep_idx = st.selectbox(
            "Filter Reports by Campaign:",
            options=range(len(campaign_labels)),
            format_func=lambda idx: campaign_labels[idx],
            key="dashboard_campaign_filter"
        )
        
        camp_id = campaign_ids[selected_rep_idx]
        
        # Pull database records for the selected campaign
        db = get_db_session()
        try:
            camp_obj = db.query(Campaign).filter(Campaign.id == camp_id).first()
            invs = db.query(OOHInventory).filter(OOHInventory.campaign_id == camp_id).all()
            perfs = db.query(Performance).filter(Performance.campaign_id == camp_id).all()
        finally:
            db.close()
            
        # Convert inventories to DataFrame
        inv_data = []
        for iv in invs:
            inv_data.append({
                "Reference ID": iv.reference_id,
                "Billboard Name": iv.billboard_name,
                "Name": iv.name,
                "OOH Impressions": float(iv.ooh_impressions) if iv.ooh_impressions is not None else 0,
                "Unique Reach": iv.unique_reach,
                "Frequency": float(iv.frequency) if iv.frequency is not None else 0,
                "eCPM (MXN)": float(iv.ecpm_mxn) if iv.ecpm_mxn is not None else 0,
                "Audience Concentration": float(iv.audience_concentration) if iv.audience_concentration is not None else 0,
                "Media Owner": iv.media_owner,
                "Format": iv.format,
                "Location": iv.location
            })
        df_inv = pd.DataFrame(inv_data)
        
        # Convert performances to DataFrame
        perf_data = []
        for pf in perfs:
            perf_data.append({
                "Date": pf.date,
                "Ad Plays": float(pf.ad_plays) if pf.ad_plays is not None else 0,
                "Billed Ad Play": float(pf.billed_ad_play) if pf.billed_ad_play is not None else 0,
                "Billed Impressions": float(pf.billed_impressions) if pf.billed_impressions is not None else 0,
                "OOH Impressions": float(pf.ooh_impressions) if pf.ooh_impressions is not None else 0,
                "Media Cost": float(pf.media_cost) if pf.media_cost is not None else 0,
                "Spent": float(pf.spent) if pf.spent is not None else 0,
                "Publisher": pf.publisher,
                "Inventory": pf.inventory,
                "File Name": pf.file_name
            })
        df_perf = pd.DataFrame(perf_data)
        
        # ---------------------------------------------------------
        # DISPLAY PERFORMANCE PLOTS
        # ---------------------------------------------------------
        st.markdown(f"#### 📊 Ingestion Overview for '{camp_obj.name}'")
        
        # General details
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{len(df_inv)}</div>
                <div class="metric-label">Locations Booked</div>
            </div>
            """, unsafe_allow_html=True)
        with col_m2:
            est_impr = int(df_inv["OOH Impressions"].sum())
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{est_impr:,}</div>
                <div class="metric-label">Planned Impressions</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_m3:
            actual_impr = int(df_perf["OOH Impressions"].sum()) if not df_perf.empty else 0
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{actual_impr:,}</div>
                <div class="metric-label">Actual Ingested Impressions</div>
            </div>
            """, unsafe_allow_html=True)
            
        with col_m4:
            actual_cost = df_perf["Spent"].sum() if not df_perf.empty else 0.0
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">${actual_cost:,.2f}</div>
                <div class="metric-label">Actual Spent (MXN)</div>
            </div>
            """, unsafe_allow_html=True)
            
        st.markdown("---")
        
        if df_perf.empty:
            st.info("💡 Campaign details are successfully loaded, but no performance metrics have been uploaded yet. Go to the second tab to upload impressions files.")
        else:
            # Grouping by Date for timeline analysis
            df_timeline = df_perf.groupby("Date").agg({
                "OOH Impressions": "sum",
                "Spent": "sum",
                "Ad Plays": "sum"
            }).reset_index().sort_values("Date")
            
            # Grouping by Publisher
            df_pub = df_perf.groupby("Publisher").agg({
                "OOH Impressions": "sum",
                "Spent": "sum"
            }).reset_index()
            
            # Interactive Timeline Plot
            st.markdown("#### 📈 Timeline: Ingested Impressions & Daily Budget Execution")
            fig_timeline = go.Figure()
            fig_timeline.add_trace(go.Scatter(
                x=df_timeline["Date"],
                y=df_timeline["OOH Impressions"],
                name="Impressions",
                mode="lines+markers",
                line=dict(color="#1e3c72", width=3),
                yaxis="y"
            ))
            fig_timeline.add_trace(go.Bar(
                x=df_timeline["Date"],
                y=df_timeline["Spent"],
                name="Daily Spent (MXN)",
                marker_color="#2a5298",
                opacity=0.6,
                yaxis="y2"
            ))
            
            fig_timeline.update_layout(
                yaxis=dict(title=dict(text="OOH Impressions", font=dict(color="#1e3c72")), tickfont=dict(color="#1e3c72")),
                yaxis2=dict(title=dict(text="Daily Spent (MXN)", font=dict(color="#2a5298")), tickfont=dict(color="#2a5298"), anchor="x", overlaying="y", side="right"),
                legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.7)"),
                margin=dict(l=40, r=40, t=20, b=40),
                plot_bgcolor="white",
                xaxis=dict(showgrid=True, gridcolor="#e2e8f0"),
                height=400
            )
            st.plotly_chart(fig_timeline, use_container_width=True)
            
            # Side-by-side: Publisher Share and Top Booked spots
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.markdown("#### 🎯 Impressions Contribution by Publisher")
                fig_pie = px.pie(
                    df_pub,
                    values="OOH Impressions",
                    names="Publisher",
                    color_discrete_sequence=px.colors.qualitative.Prism,
                    hole=0.4
                )
                fig_pie.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=350)
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with col_chart2:
                st.markdown("#### 📣 Top Performing Ad Play Locations")
                # Group by inventory item in performance records
                df_top_inv = df_perf.groupby("Inventory").agg({
                    "Ad Plays": "sum",
                    "OOH Impressions": "sum"
                }).reset_index().sort_values("OOH Impressions", ascending=False).head(10)
                
                fig_bar = px.bar(
                    df_top_inv,
                    y="Inventory",
                    x="OOH Impressions",
                    orientation="h",
                    color="Ad Plays",
                    color_continuous_scale="blues",
                    labels={"OOH Impressions": "Total Ingested Impressions"}
                )
                fig_bar.update_layout(
                    margin=dict(l=20, r=20, t=20, b=20),
                    height=350,
                    yaxis=dict(autorange="reversed")
                )
                st.plotly_chart(fig_bar, use_container_width=True)
                
            st.markdown("---")
            
        # Display Database table view
        st.markdown("#### 📋 Raw Database Query View")
        tbl_view = st.radio("Choose Table to query:", ["Campaign's OOH Inventory", "Campaign's Performance Records"], horizontal=True)
        
        if tbl_view == "Campaign's OOH Inventory":
            if not df_inv.empty:
                st.dataframe(df_inv, use_container_width=True)
            else:
                st.info("No OOH Inventory found.")
        else:
            if not df_perf.empty:
                st.dataframe(df_perf, use_container_width=True)
            else:
                st.info("No performance records found.")
