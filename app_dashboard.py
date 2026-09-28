# app_dashboard.py
"""
Dashboard UIO — Optimizado para MÓVIL.
Títulos compactos, tarjetas legibles, colores celeste eléctrico + verde/rojo.
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


def _es_entorno_cloud():
    if os.getenv("STREAMLIT_SHARING_MODE") == "streamlit":
        return True
    if not os.path.exists(os.path.join(BASE_DIR, "venv")):
        return True
    return False


EN_CLOUD = _es_entorno_cloud()


st.set_page_config(
    page_title="UIO Monitor",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="collapsed",  # Colapsado en móvil
)

# ══════════════════════════════════════════════════════════════════════════════
# CSS — OPTIMIZADO PARA MÓVIL
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
    /* ─── Base ─── */
    .stApp { background-color: #0a0e14; }
    section[data-testid="stSidebar"] { background-color: #0f1419; }

    /* ─── Títulos compactos (móvil) ─── */
    h1 {
        color: #00D4FF !important;
        font-family: 'Courier New', monospace;
        font-size: 22px !important;
        text-align: center;
        margin-bottom: 5px !important;
    }
    h2 {
        color: #00D4FF !important;
        font-family: 'Courier New', monospace;
        font-size: 18px !important;
        margin-top: 10px !important;
        margin-bottom: 8px !important;
    }
    h3 {
        color: #00D4FF !important;
        font-family: 'Courier New', monospace;
        font-size: 15px !important;
        margin-top: 8px !important;
        margin-bottom: 6px !important;
    }
    p, label, span { font-size: 13px !important; }

    /* ─── Métricas compactas ─── */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #16181f 0%, #1e222b 100%);
        border: 1px solid #00D4FF;
        border-radius: 6px;
        padding: 8px 10px !important;
        box-shadow: 0 0 8px rgba(0,212,255,0.2);
    }
    div[data-testid="stMetric"] label {
        color: #00D4FF !important;
        font-size: 10px !important;
        font-family: 'Courier New', monospace;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 16px !important;
        font-family: 'Courier New', monospace;
        font-weight: bold;
    }

    /* ─── Contexto compacto ─── */
    .context-box {
        background: linear-gradient(90deg, #1a1f2e 0%, #0f1419 100%);
        border-left: 3px solid #00D4FF;
        padding: 8px 12px;
        margin: 8px 0 12px 0;
        border-radius: 4px;
        font-family: 'Courier New', monospace;
        color: #E6EDF3;
        font-size: 11px;
        line-height: 1.6;
    }
    .context-box b { color: #00D4FF; }

    /* ─── Tarjeta de posición (grande y clara) ─── */
    .result-card {
        padding: 16px 18px;
        margin: 10px 0;
        border-radius: 10px;
        font-family: 'Courier New', monospace;
        box-shadow: 0 4px 15px rgba(0,0,0,0.5);
        border-left: 8px solid;
    }
    .win { border-left-color: #00FF88; background: linear-gradient(90deg, #0e2a15 0%, #0a1a0e 100%); }
    .lose { border-left-color: #FF3B3B; background: linear-gradient(90deg, #2a0e0e 0%, #1a0808 100%); }
    .tie { border-left-color: #FFD700; background: linear-gradient(90deg, #2a2210 0%, #1a1508 100%); }

    .result-duration {
        font-size: 20px;
        font-weight: bold;
        color: #ffffff;
        letter-spacing: 1px;
        margin-bottom: 4px;
    }
    .result-dates {
        color: #8B949E;
        font-size: 11px;
        margin-bottom: 10px;
    }
    .big-message {
        font-size: 18px;
        font-weight: bold;
        margin: 10px 0;
        line-height: 1.3;
    }
    .msg-win { color: #00FF88; text-shadow: 0 0 8px rgba(0,255,136,0.4); }
    .msg-lose { color: #FF3B3B; text-shadow: 0 0 8px rgba(255,59,59,0.4); }
    .msg-tie { color: #FFD700; text-shadow: 0 0 8px rgba(255,215,0,0.4); }

    .sub-message { color: #E6EDF3; font-size: 12px; margin: 6px 0 12px 0; line-height: 1.5; }

    /* ─── Grid de precios (2 columnas en móvil) ─── */
    .prices-row {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        margin-top: 10px;
    }
    .price-box {
        background: #0a0e14;
        padding: 8px 10px;
        border-radius: 6px;
        border: 1px solid #2a2d36;
    }
    .price-label {
        color: #8B949E;
        font-size: 9px;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 3px;
    }
    .price-value { font-size: 16px; font-weight: bold; }
    .price-sub { color: #8B949E; font-size: 10px; margin-top: 2px; }

    /* ─── Cambios ─── */
    .change-card {
        padding: 0;
        margin: 8px 0;
        border-radius: 8px;
        background: #16181f;
        overflow: hidden;
        font-family: 'Courier New', monospace;
        border-left: 6px solid;
    }
    .change-bajó { border-left-color: #00FF88; }
    .change-subió { border-left-color: #FF3B3B; }
    .change-header {
        padding: 10px 14px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
    }
    .change-date-block { display: flex; align-items: center; gap: 10px; }
    .change-date-day { font-size: 26px; font-weight: bold; line-height: 1; }
    .change-date-month {
        font-size: 10px; text-transform: uppercase;
        letter-spacing: 1px; color: #8B949E;
    }
    .change-badge {
        padding: 4px 12px; border-radius: 6px;
        font-size: 15px; font-weight: bold;
    }
    .badge-down { background: #00FF88; color: #000000; }
    .badge-up { background: #FF3B3B; color: #ffffff; }
    .change-body { padding: 8px 14px 12px 14px; }
    .change-company { font-size: 16px; font-weight: bold; margin-bottom: 4px; }
    .change-details { color: #8B949E; font-size: 11px; margin-bottom: 8px; }

    /* ─── Empresa en ranking ─── */
    .company-card {
        padding: 8px 12px;
        margin: 5px 0;
        border-radius: 6px;
        background: #16181f;
        border-left: 4px solid;
        font-family: 'Courier New', monospace;
        font-size: 13px;
    }

    /* ─── Botones ─── */
    button[kind="primary"] {
        background: linear-gradient(90deg, #00D4FF 0%, #00A0CC 100%) !important;
        color: #000000 !important;
        border: none !important;
        font-weight: bold !important;
        font-size: 14px !important;
    }

    /* ─── Tabs compactos ─── */
    button[data-baseweb="tab"] {
        font-family: 'Courier New', monospace !important;
        font-size: 11px !important;
        padding: 6px 4px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #00D4FF !important;
        border-bottom: 2px solid #00D4FF !important;
    }

    /* ─── Ocultar "Deploy" y menú en móvil ─── */
    [data-testid="stToolbar"] { visibility: hidden; }
    #MainMenu { visibility: hidden; }

    /* ─── Ajustes responsivos ─── */
    @media (max-width: 480px) {
        h1 { font-size: 18px !important; }
        h2 { font-size: 15px !important; }
        .result-duration { font-size: 17px; }
        .big-message { font-size: 15px; }
        .price-value { font-size: 14px; }
        .change-date-day { font-size: 22px; }
    }
</style>
""", unsafe_allow_html=True)

st.title("⚡ UIO RENTAL MONITOR")


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

st.sidebar.markdown("### 🎛️ Panel")

if EN_CLOUD:
    st.sidebar.success(
        "🌐 **Modo nube**\n\n"
        "Los datos se actualizan desde la PC. "
        "Cambia de fecha abajo para ver otras opciones."
    )
else:
    st.sidebar.markdown("**🔍 Analizar nueva fecha**")
    nueva_fecha = st.sidebar.date_input(
        "Fecha",
        value=datetime.now().date() + timedelta(days=1),
        min_value=datetime.now().date(),
        max_value=datetime.now().date() + timedelta(days=365),
        format="DD/MM/YYYY",
    )
    duraciones_analisis = st.sidebar.multiselect(
        "Duraciones",
        options=[3, 5, 7, 15, 21, 30],
        default=[3, 5, 7, 15, 21, 30],
    )
    plataformas_analisis = st.sidebar.multiselect(
        "Plataformas",
        options=["expedia", "booking"],
        default=["expedia", "booking"],
    )
    if st.sidebar.button("🚀 Analizar", type="primary", use_container_width=True):
        if duraciones_analisis and plataformas_analisis:
            st.session_state["analisis_activo"] = True
            st.session_state["analisis_fecha"] = nueva_fecha.strftime("%Y-%m-%d")
            st.session_state["analisis_durs"] = ",".join(str(d) for d in duraciones_analisis)
            st.session_state["analisis_plats"] = ",".join(plataformas_analisis)
            st.rerun()

st.sidebar.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER (solo local)
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.get("analisis_activo") and not EN_CLOUD:
    fecha_iso = st.session_state["analisis_fecha"]
    durs_str = st.session_state["analisis_durs"]
    plats_str = st.session_state["analisis_plats"]

    st.markdown(f"### 🔄 Analizando {fecha_iso}")
    st.info(f"Consultando para {fecha_iso} ({durs_str} días). 4-8 min.")

    progress_bar = st.progress(0)
    status_text = st.empty()

    scraper_path = os.path.join(BASE_DIR, "scraper_precios.py")
    venv_python = os.path.join(BASE_DIR, "venv", "bin", "python3")
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable

    cmd = [python_exe, scraper_path, "--fecha", fecha_iso,
           "--duraciones", durs_str, "--plataformas", plats_str]

    try:
        proceso = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    bufsize=1, cwd=BASE_DIR)
        log_lines = []
        i = 0
        with st.expander("📜 Log", expanded=False):
            lp = st.empty()
            for line in proceso.stdout:
                log_lines.append(line.rstrip())
                i += 1
                if i % 5 == 0:
                    progress_bar.progress(min(i / 200, 0.95))
                    lp.code("\n".join(log_lines[-20:]), language="bash")
        proceso.wait()
        progress_bar.progress(1.0)

        if proceso.returncode == 0:
            st.success(f"✅ Listo.")
            st.cache_data.clear()
            for k in ("analisis_activo", "analisis_fecha", "analisis_durs", "analisis_plats"):
                st.session_state.pop(k, None)
            time.sleep(2)
            st.rerun()
        else:
            st.error("❌ Error. Revisa scraper.log.")
            if st.button("Cerrar"):
                st.session_state.pop("analisis_activo", None)
                st.rerun()
    except Exception as e:
        st.error(f"❌ {e}")
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
        "### 📭 Sin datos\n\n"
        "**Desde la PC:** corre el scraper.\n\n"
        "**Comando:**\n"
        "```\n"
        "./venv/bin/python3 scraper_precios.py --fecha 2026-12-24\n"
        "```"
    )
    st.stop()

# ─── Selector de compañía ───
companias_disp = sorted(df['compania'].unique().tolist())
if MI_EMPRESA in companias_disp:
    companias_disp.remove(MI_EMPRESA)
    companias_disp.insert(0, MI_EMPRESA)

compania_foco = st.sidebar.selectbox("🎯 Compañía", companias_disp, index=0)

# ─── Selector de fecha ───
fechas_disp = sorted(df['fecha_recogida'].dropna().dt.date.unique().tolist())
if not fechas_disp:
    st.warning("No hay fechas.")
    st.stop()

fecha_sel = st.sidebar.selectbox(
    "📅 Fecha de recogida",
    fechas_disp,
    format_func=lambda x: x.strftime("%d/%m/%Y"),
)

# ─── Selector de duraciones ───
durs_disp = sorted(df[df['fecha_recogida'].dt.date == fecha_sel]['dias'].unique().tolist())
durs_sel = []
st.sidebar.markdown("**⏱️ Duraciones**")
for d in durs_disp:
    if st.sidebar.checkbox(f"{d} días", value=True, key=f"chk_{d}"):
        durs_sel.append(d)

# ─── Categoría ───
categorias = ["Todas"] + sorted(df['categoria'].unique().tolist())
cat_sel = st.sidebar.selectbox("🚙 Categoría", categorias)

# ─── Filtrar ───
df_f = df[df['fecha_recogida'].dt.date == fecha_sel].copy()
if durs_sel:
    df_f = df_f[df_f['dias'].isin(durs_sel)]
if cat_sel != "Todas":
    df_f = df_f[df_f['categoria'] == cat_sel]

st.markdown(
    f"""
    <div class="context-box">
        🎯 <b>{compania_foco}</b> · 📅 <b>{fecha_sel.strftime('%d/%m/%Y')}</b> · 
        ⏱️ {', '.join(str(d)+'d' for d in durs_sel) if durs_sel else '—'} · 
        🚙 {cat_sel} · 📊 {len(df_f)} registros
    </div>
    """,
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════

tab1, tab2, tab3 = st.tabs(["🎯 POSICIÓN", "📉 CAMBIOS", "📋 DATOS"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    if df_f.empty:
        st.info("Sin datos con los filtros actuales.")
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
                    estado, msg = "lose", f"⚠️ BAJA ${diff + 0.5:.2f}/día"
                    sub_msg = f"<b style='color:#FF3B3B;'>{rival}</b> está más barato (${precio_rival:.2f}/día)."
                elif diff < 0:
                    estado, msg = "win", "✅ ERES EL MÁS BARATO"
                    sub_msg = f"Estás ${abs(diff):.2f}/día por debajo de <b>{rival}</b>."
                else:
                    estado, msg = "tie", "🟰 EMPATE"
                    sub_msg = f"Baja $1 para diferenciarte."
            else:
                if diff > 0:
                    estado, msg = "lose", f"⚠️ {compania_foco} +${diff:.2f}/día"
                    sub_msg = f"<b>{rival}</b> es más barato (${precio_rival:.2f}/día)."
                elif diff < 0:
                    estado, msg = "win", f"✅ {compania_foco} -${abs(diff):.2f}/día"
                    sub_msg = f"Por debajo de <b>{rival}</b>."
                else:
                    estado, msg = "tie", "🟰 EMPATE"
                    sub_msg = f"Igual que <b>{rival}</b>."

            ranking = sub.groupby('compania')['precio_dia'].min().sort_values()
            posicion = list(ranking.index).index(compania_foco) + 1 if compania_foco in ranking.index else None
            total_rank = len(ranking)

            msg_class = "msg-win" if estado == "win" else "msg-lose" if estado == "lose" else "msg-tie"

            st.markdown(
                f"""
                <div class="result-card {estado}">
                    <div class="result-duration">⏱️ {dias} Días</div>
                    <div class="result-dates">
                        {fecha_sel.strftime('%d/%m/%Y')} → {fecha_dev.strftime('%d/%m/%Y')}
                    </div>
                    <div class="big-message {msg_class}">{msg}</div>
                    <div class="sub-message">{sub_msg}</div>
                    <div class="prices-row">
                        <div class="price-box">
                            <div class="price-label">{compania_foco[:10]}</div>
                            <div class="price-value" style="color:{color_de(compania_foco)};">
                                ${precio_yo:.2f}
                            </div>
                            <div class="price-sub">Total ${total_yo:.0f}</div>
                        </div>
                        <div class="price-box">
                            <div class="price-label">Rival</div>
                            <div class="price-value" style="color:{color_de(rival)};">
                                {rival[:10]}
                            </div>
                            <div class="price-sub">${precio_rival:.2f} · #{posicion}/{total_rank}</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    st.markdown("### 📉 Cambios de precio")

    cambios = calcular_cambios(df[df['fecha_recogida'].dt.date == fecha_sel])

    if cambios.empty:
        st.info(
            "📭 Aún no hay cambios.\n\n"
            "Analiza la misma fecha 2+ veces para detectar subidas/bajadas."
        )
    else:
        col1, col2 = st.columns(2)
        with col1:
            dir_f = st.selectbox("Filtro", ["Todos", "🔻 Bajadas", "🔺 Subidas"])
        with col2:
            comp_f = st.selectbox("Compañía",
                                  ["Todas"] + sorted(cambios['compania'].unique().tolist()))

        cf = cambios.copy()
        if dir_f == "🔻 Bajadas": cf = cf[cf['variacion'] < 0]
        elif dir_f == "🔺 Subidas": cf = cf[cf['variacion'] > 0]
        if comp_f != "Todas": cf = cf[cf['compania'] == comp_f]

        if cf.empty:
            st.info("Sin cambios con estos filtros.")
        else:
            cf = cf.sort_values('pct_variacion', key=abs, ascending=False)

            for _, r in cf.head(20).iterrows():
                color = color_de(r['compania'])
                es_bajada = r['variacion'] < 0
                color_delta = "#00FF88" if es_bajada else "#FF3B3B"
                emoji = "▼" if es_bajada else "▲"
                signo = "-" if es_bajada else "+"
                dia = r['fecha_consulta'].strftime("%d")
                mes = MESES_ES.get(r['fecha_consulta'].month, "?")

                st.markdown(
                    f"""
                    <div class="change-card {'change-bajó' if es_bajada else 'change-subió'}">
                        <div class="change-header">
                            <div class="change-date-block">
                                <div class="change-date-day" style="color:{color_delta};">{dia}</div>
                                <div>
                                    <div class="change-date-month">{mes}</div>
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
                                {r['categoria']} · {r['transmision']} · {r['dias']}d
                            </div>
                            <div style="color:#E6EDF3; font-size:14px;">
                                <span style="color:#8B949E; text-decoration:line-through;">
                                    ${r['precio_anterior']:.0f}
                                </span>
                                →
                                <b style="color:{color_delta};">${r['precio_dia']:.0f}</b>
                                <span style="color:{color_delta};">({signo}${abs(r['variacion']):.0f})</span>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.markdown("### 📋 Datos")

    cols = ['compania', 'categoria', 'transmision', 'dias',
            'precio_total', 'precio_dia', 'plataforma']
    cols_show = [c for c in cols if c in df_f.columns]

    def _colorear(row):
        color = color_de(row['compania'])
        return [f'background-color: {color}22; color: {color}; font-weight: bold'
                if col == 'compania' else '' for col in row.index]

    st.dataframe(
        df_f[cols_show].style.apply(_colorear, axis=1),
        use_container_width=True,
        height=400,
    )
