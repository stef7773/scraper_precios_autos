# app_dashboard.py
"""
Dashboard UIO — Selector de fecha + duraciones + tarjetas verde/rojo.
Color principal: CELESTE ELÉCTRICO (#00D4FF) reemplaza al fucsia.
"""

import os
import sys
import time
import subprocess
from datetime import datetime, timedelta

import streamlit as st
import sqlite3
import pandas as pd

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

MI_EMPRESA = "Europcar"

COMPANIAS_VALIDAS = {
    "Europcar", "Alamo", "Localiza", "Keddy", "Goldcar", "Sixt",
    "Avis", "Budget", "Hertz", "National", "Enterprise", "Thrifty",
    "Dollar", "Fox", "Green Motion", "Payless",
}

COLORES_COMPANIA = {
    "Europcar": "#00A650", "Alamo": "#003DA5", "Localiza": "#00A94F",
    "Keddy": "#7B2C8E", "Goldcar": "#FFD700", "Sixt": "#FF6600",
    "Avis": "#D40000", "Budget": "#0066CC", "Hertz": "#FFCC00",
    "National": "#00573F", "Enterprise": "#007A33", "Thrifty": "#FF69B4",
    "Dollar": "#999999", "Fox": "#ADFF2F", "Green Motion": "#3CB371",
    "Payless": "#FF1493",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")

st.set_page_config(
    page_title="UIO Rental Monitor",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
# CSS — CELESTE ELÉCTRICO
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
    .stApp { background-color: #0a0e14; }
    section[data-testid="stSidebar"] { background-color: #0f1419; }

    /* CELESTE ELÉCTRICO reemplaza fucsia */
    h1, h2, h3 {
        color: #00D4FF !important;
        font-family: 'Courier New', monospace;
        text-shadow: 0 0 12px rgba(0,212,255,0.6);
    }

    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #16181f 0%, #1e222b 100%);
        border: 2px solid #00D4FF;
        border-radius: 8px;
        padding: 15px;
        box-shadow: 0 0 15px rgba(0,212,255,0.3);
    }
    div[data-testid="stMetric"] label {
        color: #00D4FF !important;
        font-family: 'Courier New', monospace;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-family: 'Courier New', monospace;
        font-weight: bold;
    }

    .context-box {
        background: linear-gradient(90deg, #1a1f2e 0%, #0f1419 100%);
        border-left: 4px solid #00D4FF;
        padding: 12px 18px;
        margin: 10px 0 20px 0;
        border-radius: 6px;
        font-family: 'Courier New', monospace;
        color: #E6EDF3;
        font-size: 14px;
    }
    .context-box b { color: #00D4FF; }

    /* TARJETAS DE POSICIÓN — verde/rojo/dorado */
    .result-card {
        padding: 24px 28px;
        margin: 16px 0;
        border-radius: 12px;
        font-family: 'Courier New', monospace;
        box-shadow: 0 6px 20px rgba(0,0,0,0.5);
        border-left: 10px solid;
    }
    .win { border-left-color: #00FF88; background: linear-gradient(90deg, #0e2a15 0%, #0a1a0e 100%); }
    .lose { border-left-color: #FF3B3B; background: linear-gradient(90deg, #2a0e0e 0%, #1a0808 100%); }
    .tie { border-left-color: #FFD700; background: linear-gradient(90deg, #2a2210 0%, #1a1508 100%); }

    .result-duration {
        font-size: 30px;
        font-weight: bold;
        color: #ffffff;
        letter-spacing: 2px;
        margin-bottom: 8px;
    }
    .result-dates { color: #8B949E; font-size: 13px; margin-bottom: 18px; }

    .big-message {
        font-size: 28px;
        font-weight: bold;
        margin: 16px 0;
        line-height: 1.3;
    }
    .msg-win { color: #00FF88; text-shadow: 0 0 15px rgba(0,255,136,0.5); }
    .msg-lose { color: #FF3B3B; text-shadow: 0 0 15px rgba(255,59,59,0.5); }
    .msg-tie { color: #FFD700; text-shadow: 0 0 15px rgba(255,215,0,0.5); }

    .sub-message { color: #E6EDF3; font-size: 16px; margin: 8px 0 18px 0; }

    .prices-row { display: flex; gap: 16px; margin-top: 16px; flex-wrap: wrap; }
    .price-box {
        background: #0a0e14;
        padding: 14px 20px;
        border-radius: 8px;
        flex: 1;
        min-width: 160px;
        border: 1px solid #2a2d36;
    }
    .price-label {
        color: #8B949E;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 6px;
    }
    .price-value { font-size: 26px; font-weight: bold; }

    /* Cambios */
    .change-card {
        padding: 0; margin: 12px 0; border-radius: 10px;
        background: linear-gradient(90deg, #16181f 0%, #1e222b 100%);
        overflow: hidden; font-family: 'Courier New', monospace;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        border-left: 8px solid;
    }
    .change-bajó { border-left-color: #00FF88; }
    .change-subió { border-left-color: #FF3B3B; }
    .change-header {
        padding: 14px 22px;
        background: linear-gradient(90deg, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.1) 100%);
        display: flex; align-items: center; justify-content: space-between;
        flex-wrap: wrap; gap: 10px;
    }
    .change-date-block { display: flex; align-items: center; gap: 14px; }
    .change-date-day { font-size: 40px; font-weight: bold; line-height: 1; }
    .change-date-month {
        font-size: 13px; text-transform: uppercase;
        letter-spacing: 2px; color: #8B949E;
    }
    .change-date-time { font-size: 12px; color: #8B949E; margin-top: 2px; }
    .change-badge {
        padding: 8px 18px; border-radius: 8px;
        font-size: 22px; font-weight: bold;
    }
    .badge-down { background: #00FF88; color: #000000; }
    .badge-up { background: #FF3B3B; color: #ffffff; }
    .change-body { padding: 14px 22px 18px 22px; }
    .change-company {
        font-size: 22px; font-weight: bold; letter-spacing: 1px; margin-bottom: 6px;
    }
    .change-details { color: #8B949E; font-size: 13px; margin-bottom: 12px; }
    .change-prices {
        font-size: 17px; color: #E6EDF3; display: flex;
        align-items: center; gap: 12px; flex-wrap: wrap;
    }
    .price-old { color: #8B949E; text-decoration: line-through; font-size: 15px; }
    .price-new { font-size: 24px; font-weight: bold; }

    .company-card {
        padding: 14px 18px; margin: 8px 0; border-radius: 8px;
        background: linear-gradient(90deg, #16181f 0%, #1e222b 100%);
        border-left: 6px solid; font-family: 'Courier New', monospace;
    }

    /* BOTONES EN CELESTE */
    button[kind="primary"] {
        background: linear-gradient(90deg, #00D4FF 0%, #00A0CC 100%) !important;
        color: #000000 !important;
        border: none !important;
        font-weight: bold !important;
    }
    button[kind="primary"]:hover {
        background: linear-gradient(90deg, #33DDFF 0%, #00B8E0 100%) !important;
    }

    /* TABS */
    button[data-baseweb="tab"] {
        font-family: 'Courier New', monospace !important;
        font-size: 14px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #00D4FF !important;
        border-bottom: 3px solid #00D4FF !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚡ UIO RENTAL MONITOR ⚡")


# ══════════════════════════════════════════════════════════════════════════════
# CARGA
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30)
def cargar_datos():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM historial_precios", conn)
    except Exception:
        conn.close()
        return pd.DataFrame()
    conn.close()
    if df.empty:
        return df
    df = df[df['compania'].isin(COMPANIAS_VALIDAS)]
    df['fecha_consulta'] = pd.to_datetime(df['fecha_consulta'])
    if 'fecha_recogida' in df.columns:
        df['fecha_recogida'] = pd.to_datetime(df['fecha_recogida'], errors='coerce')
    return df


def color_de(c):
    return COLORES_COMPANIA.get(c, "#808080")


def calcular_cambios(df):
    if df.empty:
        return pd.DataFrame()
    keys = ['plataforma', 'compania', 'dias', 'categoria', 'transmision']
    df_s = df.sort_values(keys + ['fecha_consulta']).copy()
    df_s['precio_anterior'] = df_s.groupby(keys)['precio_dia'].shift(1)
    df_s['fecha_anterior'] = df_s.groupby(keys)['fecha_consulta'].shift(1)
    df_s['variacion'] = df_s['precio_dia'] - df_s['precio_anterior']
    df_s['pct_variacion'] = ((df_s['variacion'] / df_s['precio_anterior']) * 100).round(1)
    cambios = df_s[df_s['variacion'].notnull() & (df_s['variacion'] != 0)].copy()
    return cambios.sort_values('fecha_consulta', ascending=False)


MESES_ES = {1:"ENE",2:"FEB",3:"MAR",4:"ABR",5:"MAY",6:"JUN",
            7:"JUL",8:"AGO",9:"SEP",10:"OCT",11:"NOV",12:"DIC"}


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

st.sidebar.markdown("## 🎛️ Panel de control")

# ─── Analizar nueva fecha ────────────────────────────────────────────────────
st.sidebar.markdown("### 🔍 Analizar nueva fecha")

nueva_fecha = st.sidebar.date_input(
    "Fecha a analizar",
    value=datetime.now().date() + timedelta(days=1),
    min_value=datetime.now().date(),
    max_value=datetime.now().date() + timedelta(days=365),
    format="DD/MM/YYYY",
    key="nueva_fecha_analisis",
)

duraciones_analisis = st.sidebar.multiselect(
    "Duraciones",
    options=[3, 5, 7, 15, 21, 30],
    default=[3, 5, 7, 15, 21, 30],
    key="durs_analisis",
)

plataformas_analisis = st.sidebar.multiselect(
    "Plataformas",
    options=["expedia", "booking"],
    default=["expedia", "booking"],
    key="plats_analisis",
)

if st.sidebar.button("🚀 Analizar esta fecha", type="primary", use_container_width=True):
    if not duraciones_analisis or not plataformas_analisis:
        st.sidebar.error("Selecciona duraciones y plataformas.")
    else:
        st.session_state["analisis_activo"] = True
        st.session_state["analisis_fecha"] = nueva_fecha.strftime("%Y-%m-%d")
        st.session_state["analisis_durs"] = ",".join(str(d) for d in duraciones_analisis)
        st.session_state["analisis_plats"] = ",".join(plataformas_analisis)
        st.rerun()

st.sidebar.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER DEL ANÁLISIS
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.get("analisis_activo"):
    fecha_iso = st.session_state["analisis_fecha"]
    durs_str = st.session_state["analisis_durs"]
    plats_str = st.session_state["analisis_plats"]

    st.markdown(f"## 🔄 Analizando {fecha_iso}")
    st.info(f"⏳ Consultando Expedia y Booking para {fecha_iso} ({durs_str} días). "
            f"Tarda 4-8 min. **Si aparece captcha, resuélvelo en el navegador.**")

    progress_bar = st.progress(0)
    status_text = st.empty()

    scraper_path = os.path.join(BASE_DIR, "scraper_precios.py")
    venv_python = os.path.join(BASE_DIR, "venv", "bin", "python3")
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable

    cmd = [python_exe, scraper_path,
           "--fecha", fecha_iso,
           "--duraciones", durs_str,
           "--plataformas", plats_str]

    status_text.text(f"Ejecutando: {' '.join(cmd)}")

    try:
        proceso = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=BASE_DIR,
        )
        log_lines = []
        i = 0
        with st.expander("📜 Log en vivo", expanded=True):
            log_placeholder = st.empty()
            for line in proceso.stdout:
                log_lines.append(line.rstrip())
                i += 1
                if i % 5 == 0:
                    progress_bar.progress(min(i / 200, 0.95))
                    log_placeholder.code("\n".join(log_lines[-30:]), language="bash")

        proceso.wait()
        progress_bar.progress(1.0)

        if proceso.returncode == 0:
            st.success(f"✅ ¡Listo! Datos de {fecha_iso} analizados.")
            st.cache_data.clear()
            for k in ("analisis_activo", "analisis_fecha", "analisis_durs", "analisis_plats"):
                st.session_state.pop(k, None)
            time.sleep(3)
            st.rerun()
        else:
            st.error(f"❌ Error (código {proceso.returncode}). Revisa `scraper.log`.")
            if st.button("Cerrar"):
                st.session_state.pop("analisis_activo", None)
                st.rerun()
    except Exception as e:
        st.error(f"❌ {e}")
        st.exception(e)
        if st.button("Cerrar"):
            st.session_state.pop("analisis_activo", None)
            st.rerun()

    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# DATOS CARGADOS
# ══════════════════════════════════════════════════════════════════════════════

df = cargar_datos()

if df.empty or 'fecha_recogida' not in df.columns or df['fecha_recogida'].isna().all():
    st.warning(
        "### 📭 No hay datos todavía\n\n"
        "**Paso 1:** En el sidebar, elige fecha + duraciones + plataformas.\n\n"
        "**Paso 2:** Pulsa **🚀 Analizar esta fecha**.\n\n"
        "**Paso 3:** Espera 4-8 minutos. Se recargará solo."
    )
    st.stop()

# Compañía en foco
st.sidebar.markdown("### 🎯 Compañía en foco")
companias_disp = sorted(df['compania'].unique().tolist())
if MI_EMPRESA in companias_disp:
    companias_disp.remove(MI_EMPRESA)
    companias_disp.insert(0, MI_EMPRESA)

compania_foco = st.sidebar.selectbox("Compañía", companias_disp, index=0,
                                     label_visibility="collapsed")

st.sidebar.markdown("---")

# Fecha de recogida (de las que hay en DB)
fechas_disp = sorted(df['fecha_recogida'].dropna().dt.date.unique().tolist())
if not fechas_disp:
    st.warning("No hay fechas en la DB.")
    st.stop()

st.sidebar.markdown("### 📅 Fecha de recogida")
fecha_sel = st.sidebar.selectbox(
    "Fecha",
    fechas_disp,
    format_func=lambda x: x.strftime("%d/%m/%Y"),
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⏱️ Duraciones a mostrar")

durs_disp = sorted(df[df['fecha_recogida'].dt.date == fecha_sel]['dias'].unique().tolist())
durs_sel = []
for d in durs_disp:
    if st.sidebar.checkbox(f"{d} días", value=True, key=f"chk_{d}"):
        durs_sel.append(d)

st.sidebar.markdown("---")
categorias = ["Todas"] + sorted(df['categoria'].unique().tolist())
cat_sel = st.sidebar.selectbox("🚙 Categoría", categorias)

# Filtrar
df_f = df[df['fecha_recogida'].dt.date == fecha_sel].copy()
if durs_sel:
    df_f = df_f[df_f['dias'].isin(durs_sel)]
if cat_sel != "Todas":
    df_f = df_f[df_f['categoria'] == cat_sel]

st.markdown(
    f"""
    <div class="context-box">
        🎯 <b>Analizando:</b> {compania_foco} &nbsp;│&nbsp;
        📅 <b>Fecha:</b> {fecha_sel.strftime('%d/%m/%Y')} &nbsp;│&nbsp;
        ⏱️ <b>Duraciones:</b> {', '.join(str(d)+'d' for d in durs_sel) if durs_sel else 'Ninguna'} &nbsp;│&nbsp;
        🚙 <b>Categoría:</b> {cat_sel} &nbsp;│&nbsp;
        📊 <b>Registros:</b> {len(df_f)}
    </div>
    """,
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════

tab1, tab2, tab3 = st.tabs([
    "🎯 QUÉ HACER",
    "📉 CAMBIOS DE PRECIOS",
    "📋 DATOS",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: QUÉ HACER (TARJETAS VERDE/ROJO)
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    st.markdown(f"## 🎯 Posición de {compania_foco} — ¿Qué hacer?")

    if df_f.empty:
        st.info("Sin datos.")
    else:
        for dias in sorted(df_f['dias'].unique()):
            sub = df_f[df_f['dias'] == dias]
            yo = sub[sub['compania'] == compania_foco]
            comp = sub[sub['compania'] != compania_foco]

            if yo.empty or comp.empty:
                continue

            idx_yo = yo['precio_dia'].idxmin()
            idx_rival = comp['precio_dia'].idxmin()
            mejor_yo = yo.loc[idx_yo]
            mejor_rival = comp.loc[idx_rival]

            precio_yo = mejor_yo['precio_dia']
            precio_rival = mejor_rival['precio_dia']
            total_yo = mejor_yo['precio_total']
            total_rival = mejor_rival['precio_total']
            rival = mejor_rival['compania']

            diff = precio_yo - precio_rival
            fecha_dev = fecha_sel + timedelta(days=int(dias))

            if compania_foco == MI_EMPRESA:
                if diff > 0:
                    estado = "lose"
                    msg = f"⚠️ BAJA ${diff + 0.5:.2f}/día"
                    sub_msg = (
                        f"<b style='color:#FF3B3B;'>{rival}</b> está más barato "
                        f"(${precio_rival:.2f}/día vs ${precio_yo:.2f} tuyo). "
                        f"Baja a <b style='color:#00FF88;'>${precio_rival - 0.5:.2f}</b> para ser el #1."
                    )
                elif diff < 0:
                    estado = "win"
                    msg = "✅ ERES EL MÁS BARATO"
                    margen = abs(diff) - 0.5
                    sub_msg = (
                        f"Estás <b style='color:#00FF88;'>${abs(diff):.2f}/día</b> "
                        f"por debajo de <b>{rival}</b>. "
                        f"Margen: <b>${margen:.2f}</b> antes de igualarlo."
                    )
                else:
                    estado = "tie"
                    msg = "🟰 EMPATE"
                    sub_msg = f"Baja <b>$1.00/día</b> para diferenciarte."
            else:
                if diff > 0:
                    estado = "lose"
                    msg = f"⚠️ {compania_foco} está ${diff:.2f}/día MÁS CARO"
                    sub_msg = f"<b>{rival}</b> es más barato (${precio_rival:.2f}/día)."
                elif diff < 0:
                    estado = "win"
                    msg = f"✅ {compania_foco} está ${abs(diff):.2f}/día MÁS BARATO"
                    sub_msg = f"Por debajo de <b>{rival}</b> (${precio_rival:.2f}/día)."
                else:
                    estado = "tie"
                    msg = "🟰 EMPATE"
                    sub_msg = f"Igual que <b>{rival}</b>."

            ranking = sub.groupby('compania')['precio_dia'].min().sort_values()
            posicion = list(ranking.index).index(compania_foco) + 1 if compania_foco in ranking.index else None
            total_rank = len(ranking)

            nota_euro = ""
            if compania_foco != MI_EMPRESA:
                euro = sub[sub['compania'] == MI_EMPRESA]
                if not euro.empty:
                    pe = euro['precio_dia'].min()
                    de = pe - precio_rival
                    if de > 0:
                        nota_euro = (
                            f"<div style='margin-top:14px; padding:12px; background:#2a0e0e; "
                            f"border-left:4px solid #FF3B3B; border-radius:6px;'>"
                            f"💡 <b>Para que Europcar gane:</b> poner "
                            f"<b style='color:#00FF88;'>${precio_rival - 0.5:.2f}/día</b> "
                            f"(ahora ${pe:.2f}, rival más barato ${precio_rival:.2f})</div>"
                        )
                    else:
                        nota_euro = (
                            f"<div style='margin-top:14px; padding:12px; background:#0e2a15; "
                            f"border-left:4px solid #00FF88; border-radius:6px;'>"
                            f"💡 <b>Europcar ya gana</b> por ${abs(de):.2f}/día</div>"
                        )

            msg_class = "msg-win" if estado == "win" else "msg-lose" if estado == "lose" else "msg-tie"

            st.markdown(
                f"""
                <div class="result-card {estado}">
                    <div class="result-duration">⏱️ {dias} Días</div>
                    <div class="result-dates">
                        📅 Recogida: {fecha_sel.strftime('%d/%m/%Y')} →
                        Devolución: {fecha_dev.strftime('%d/%m/%Y')}
                    </div>
                    <div class="big-message {msg_class}">{msg}</div>
                    <div class="sub-message">{sub_msg}</div>
                    <div class="prices-row">
                        <div class="price-box">
                            <div class="price-label">{compania_foco}</div>
                            <div class="price-value" style="color:{color_de(compania_foco)};">
                                ${precio_yo:.2f}/día
                            </div>
                            <div style="color:#8B949E; font-size:12px; margin-top:4px;">
                                Total: ${total_yo:.2f}
                            </div>
                        </div>
                        <div class="price-box">
                            <div class="price-label">Rival más barato</div>
                            <div class="price-value" style="color:{color_de(rival)};">
                                {rival}
                            </div>
                            <div style="color:#8B949E; font-size:12px; margin-top:4px;">
                                ${precio_rival:.2f}/día · total ${total_rival:.2f}
                            </div>
                        </div>
                        <div class="price-box">
                            <div class="price-label">Ranking</div>
                            <div class="price-value" style="color:#00D4FF;">
                                #{posicion} de {total_rank}
                            </div>
                        </div>
                    </div>
                    {nota_euro}
                </div>
                """,
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: CAMBIOS DE PRECIOS
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    st.markdown("## 📉 Cambios de precio detectados")
    st.caption("Comparación entre la última consulta y la anterior de cada compañía.")

    cambios = calcular_cambios(df[df['fecha_recogida'].dt.date == fecha_sel])

    if cambios.empty:
        st.info(
            "📭 **Aún no hay cambios detectados.**\n\n"
            "Necesitas analizar la **misma fecha** al menos 2 veces (en momentos distintos) "
            "para que el sistema detecte subidas o bajadas de precio."
        )
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            dir_f = st.radio("Dirección", ["🔻 Bajadas", "🔺 Subidas", "Todos"],
                             horizontal=True, key="dir_cambios")
        with col2:
            comp_f = st.selectbox("Compañía",
                                  ["Todas"] + sorted(cambios['compania'].unique().tolist()),
                                  key="comp_cambios")
        with col3:
            pct_f = st.slider("% mínimo", 0, 40, 0, 1, key="pct_cambios")

        cf = cambios.copy()
        if dir_f == "🔻 Bajadas": cf = cf[cf['variacion'] < 0]
        elif dir_f == "🔺 Subidas": cf = cf[cf['variacion'] > 0]
        if comp_f != "Todas": cf = cf[cf['compania'] == comp_f]
        cf = cf[cf['pct_variacion'].abs() >= pct_f]

        if cf.empty:
            st.info("Sin cambios con los filtros.")
        else:
            k1, k2, k3 = st.columns(3)
            bajadas = cf[cf['variacion'] < 0]
            subidas = cf[cf['variacion'] > 0]
            k1.metric("🔔 Total cambios", len(cf))
            k2.metric("🔻 Bajadas", len(bajadas))
            k3.metric("🔺 Subidas", len(subidas))

            st.markdown("---")
            cf = cf.sort_values('pct_variacion', key=abs, ascending=False)

            for _, r in cf.head(30).iterrows():
                color = color_de(r['compania'])
                es_bajada = r['variacion'] < 0
                clase = "change-bajó" if es_bajada else "change-subió"
                color_delta = "#00FF88" if es_bajada else "#FF3B3B"
                emoji = "▼" if es_bajada else "▲"
                signo = "-" if es_bajada else "+"

                dia = r['fecha_consulta'].strftime("%d")
                mes = MESES_ES.get(r['fecha_consulta'].month, "???")
                hora = r['fecha_consulta'].strftime("%H:%M")
                anio = r['fecha_consulta'].year

                fecha_ant_str = (r['fecha_anterior'].strftime("%d/%m/%Y %H:%M")
                                 if pd.notna(r['fecha_anterior']) else "—")

                st.markdown(
                    f"""
                    <div class="change-card {clase}">
                        <div class="change-header">
                            <div class="change-date-block">
                                <div class="change-date-day" style="color:{color_delta};">{dia}</div>
                                <div>
                                    <div class="change-date-month">{mes} {anio}</div>
                                    <div class="change-date-time">🕐 {hora}</div>
                                </div>
                            </div>
                            <div class="change-badge {'badge-down' if es_bajada else 'badge-up'}">
                                {emoji} {r['pct_variacion']:+.1f}%
                            </div>
                        </div>
                        <div class="change-body">
                            <div class="change-company" style="color:{color};">
                                {r['compania']}
                            </div>
                            <div class="change-details">
                                {r['categoria']} · {r['transmision']} · {r['dias']} días · {r['plataforma']}
                            </div>
                            <div class="change-prices">
                                <span class="price-old">${r['precio_anterior']:.2f}</span>
                                <span style="color:#8B949E;">→</span>
                                <span class="price-new" style="color:{color_delta};">
                                    ${r['precio_dia']:.2f}
                                </span>
                                <span style="color:{color_delta}; font-weight:bold; font-size:16px; margin-left:8px;">
                                    {signo}${abs(r['variacion']):.2f}
                                </span>
                            </div>
                            <div class="change-details" style="margin-top:8px;">
                                📆 Anterior: {fecha_ant_str}
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: DATOS
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.markdown("## 📋 Datos crudos")

    def _colorear(row):
        color = color_de(row['compania'])
        return [
            f'background-color: {color}22; color: {color}; font-weight: bold'
            if col == 'compania' else ''
            for col in row.index
        ]

    cols = ['fecha_recogida', 'compania', 'categoria', 'transmision', 'dias',
            'precio_total', 'precio_dia', 'plataforma', 'fechas_alquiler']
    cols_show = [c for c in cols if c in df_f.columns]

    st.dataframe(
        df_f[cols_show].style.apply(_colorear, axis=1),
        use_container_width=True,
        height=600,
    )

    csv = df_f.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Descargar (CSV)", csv,
                       file_name=f"datos_{fecha_sel.strftime('%Y%m%d')}.csv",
                       mime="text/csv")
