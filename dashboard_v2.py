# app_dashboard.py — Competitive Edge con FILTROS
"""Dashboard con filtros completos y sin errores."""

import os
import sys
import io
from datetime import datetime, timedelta
import streamlit as st
import sqlite3
import pandas as pd

MI_EMPRESA = "Europcar"
COMPANIAS_VALIDAS = {"Europcar", "Alamo", "Localiza", "Keddy", "Goldcar",
                     "Sixt", "Avis", "Budget", "Hertz", "National",
                     "Enterprise", "Thrifty", "Dollar", "Fox",
                     "Green Motion", "Payless"}
COLORES = {
    "Europcar": "#10B981", "Alamo": "#3B82F6", "Localiza": "#22D3EE",
    "Keddy": "#A78BFA", "Goldcar": "#FBBF24", "Sixt": "#F97316",
    "Avis": "#DC2626", "Budget": "#0EA5E9", "Hertz": "#FACC15",
    "National": "#059669", "Enterprise": "#047857", "Thrifty": "#C084FC",
    "Dollar": "#94A3B8", "Fox": "#84CC16", "Green Motion": "#14B8A6",
    "Payless": "#8B5CF6",
}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
FECHAS_ACTIVAS_PATH = os.path.join(BASE_DIR, "fechas_activas.txt")

st.set_page_config(page_title="UIO Competitive Edge", page_icon="🚗",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #05080f; }
    h1 { color: #22D3EE !important; font-family: 'Courier New', monospace;
         font-size: 24px !important; text-align: center; margin: 10px 0 !important;
         letter-spacing: 4px; text-shadow: 0 0 25px rgba(34,211,238,0.9); }
    h2 { color: #22D3EE !important; font-size: 16px !important; margin: 15px 0 10px 0 !important; }
    h3 { color: #22D3EE !important; font-size: 14px !important; margin: 12px 0 8px 0 !important; }
    p, label, span { font-size: 12px !important; }
    .stButton > button { background: #0a0f1a !important; color: #22D3EE !important;
        border: 2px solid #22D3EE !important; font-family: 'Courier New', monospace !important;
        font-size: 14px !important; font-weight: bold !important;
        padding: 12px 6px !important; border-radius: 8px !important; width: 100% !important; }
    .stButton > button:hover { background: #22D3EE !important; color: #000 !important; }
    .action-banner { padding: 24px 30px; border-radius: 12px; margin: 15px 0 25px 0;
        text-align: center; font-family: 'Courier New', monospace; }
    .action-win { background: linear-gradient(135deg, #052e1f 0%, #0a1a0e 100%);
        border: 3px solid #10B981; }
    .action-lose { background: linear-gradient(135deg, #2a0e0e 0%, #1a0808 100%);
        border: 3px solid #EF4444; }
    .action-mixed { background: linear-gradient(135deg, #2a2210 0%, #1a1508 100%);
        border: 3px solid #FBBF24; }
    .action-title { font-size: 26px; font-weight: bold; letter-spacing: 2px; }
    .action-subtitle { color: #E6EDF3; font-size: 14px; margin-top: 10px; }
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 15px 0; }
    .kpi-item { background: linear-gradient(135deg, #0a0f1a 0%, #1a2333 100%);
        border: 2px solid #22D3EE; border-radius: 10px; padding: 18px; text-align: center; }
    .kpi-item-win { border-color: #10B981; }
    .kpi-item-lose { border-color: #EF4444; }
    .kpi-item-warn { border-color: #FBBF24; }
    .kpi-label { color: #94A3B8; font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; }
    .kpi-value { font-size: 34px; font-weight: bold; font-family: 'Courier New', monospace; margin-top: 8px; }
    .kpi-sub { color: #94A3B8; font-size: 10px; margin-top: 4px; }
    .combo-card { background: linear-gradient(135deg, #0a0f1a 0%, #0f1626 100%);
        border: 2px solid #1a2333; border-radius: 12px; margin: 20px 0;
        overflow: hidden; font-family: 'Courier New', monospace; }
    .combo-header { padding: 16px 20px; border-bottom: 2px solid;
        background: rgba(0,0,0,0.4); }
    .combo-title { color: #fff; font-size: 17px; font-weight: bold; letter-spacing: 1.5px; }
    .combo-dates { color: #22D3EE; font-size: 13px; margin-top: 6px; font-weight: bold; }
    .combo-body { padding: 0; }
    .combo-row { display: flex; align-items: center; gap: 12px;
        padding: 10px 20px; border-bottom: 1px solid #1a2333; font-size: 14px; }
    .combo-row-yo { background: rgba(16,185,129,0.08); border-left: 4px solid #10B981; }
    .combo-medal { font-size: 18px; min-width: 30px; text-align: center; }
    .combo-name { flex: 1; font-weight: bold; }
    .combo-bar-wrap { flex: 2; min-width: 120px; }
    .combo-bar-bg { background: #1a2333; height: 18px; border-radius: 9px; overflow: hidden; }
    .combo-bar { height: 100%; border-radius: 9px; }
    .combo-price { font-weight: bold; font-size: 16px; min-width: 90px; text-align: right; }
    .combo-total { color: #94A3B8; font-size: 12px; min-width: 85px; text-align: right; }
    .combo-footer { padding: 16px 20px; background: rgba(0,0,0,0.3); }
    .combo-action { padding: 14px 18px; border-radius: 8px; font-size: 14px;
        font-weight: bold; text-align: center; letter-spacing: 0.5px; }
    .combo-action-win { background: #052e1f; color: #10B981; border-left: 5px solid #10B981; }
    .combo-action-lose { background: #2a0e0e; color: #EF4444; border-left: 5px solid #EF4444; }
    .combo-action-tie { background: #2a2210; color: #FBBF24; border-left: 5px solid #FBBF24; }
    .combo-action-sob { color: #E6EDF3; font-size: 12px; margin-top: 8px; font-weight: normal; text-align: center; }
    .plan-item { background: #0a0f1a; padding: 14px 18px; margin: 8px 0;
        border-radius: 6px; font-family: 'Courier New', monospace; border-left: 5px solid; }
    .plan-item-urgent { border-left-color: #EF4444; }
    .plan-item-mid { border-left-color: #FBBF24; }
    .plan-item-ok { border-left-color: #10B981; }
    .plan-title { color: #fff; font-size: 14px; font-weight: bold; }
    .plan-detail { color: #94A3B8; font-size: 12px; margin-top: 4px; }
    .leyenda-box { background: #0a0f1a; border: 1px solid #22D3EE;
        border-radius: 8px; padding: 10px 14px; margin: 12px 0;
        font-family: 'Courier New', monospace; font-size: 11px;
        color: #E6EDF3; display: flex; flex-wrap: wrap; gap: 18px; justify-content: center; }
    .leyenda-item { display: flex; align-items: center; gap: 6px; }
    .leyenda-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
    button[data-baseweb="tab"] { font-family: 'Courier New', monospace !important;
        font-size: 13px !important; padding: 10px 6px !important; }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #22D3EE !important; border-bottom: 3px solid #22D3EE !important; }
    [data-testid="stToolbar"] { visibility: hidden; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ UIO COMPETITIVE EDGE")

MESES_CORTO = {1:"ENE",2:"FEB",3:"MAR",4:"ABR",5:"MAY",6:"JUN",
               7:"JUL",8:"AGO",9:"SEP",10:"OCT",11:"NOV",12:"DIC"}


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
    df['fecha_recogida'] = pd.to_datetime(df['fecha_recogida'], errors='coerce')
    df['precio_base'] = df['precio_base'].fillna(0)
    
    # VALIDACIÓN: rechazar registros donde precio_total > 2x precio_base (dato erróneo)
    # Solo aplica cuando ambos existen
    mask_sospechoso = (
        (df['precio_base'] > 0) & 
        (df['precio_total'] > df['precio_base'] * 2)
    )
    df.loc[mask_sospechoso, 'precio_total'] = df.loc[mask_sospechoso, 'precio_base']
    # Recalcular precio_dia
    df['precio_dia'] = df['precio_total'] / df['dias'].clip(lower=1)
    
    return df


def color_de(c):
    return COLORES.get(c, "#64748B")



# REGLAS DE NEGOCIO ECUADOR
def corregir_transmision(row):
    """Aplica reglas de negocio de rentadoras ecuatorianas."""
    cat = row['categoria']
    trans = row['transmision']
    
    # REGLA 1: En rentadoras de Ecuador NO existen pickups automáticas
    if cat == 'Camioneta Pickup' and trans == 'Automática':
        return 'Manual'
    
    # REGLA 2: Mini y Económico suelen ser manuales
    if cat in ('Mini', 'Económico') and trans == 'Sin especificar':
        return 'Manual'
    
    # REGLA 3: SUV y Lujo suelen ser automáticas
    if cat in ('SUV', 'SUV Lujo', 'Camioneta SUV', 'Lujo') and trans == 'Sin especificar':
        return 'Automática'
    
    return trans


def analizar_combinacion(sub, compania_foco):
    """Analiza una combinación."""
    if sub.empty:
        return None

    ranking = (sub.groupby('compania')
               .agg(precio_min=('precio_dia', 'min'),
                    precio_total=('precio_total', 'min'))
               .reset_index()
               .sort_values('precio_min'))

    yo = sub[sub['compania'] == compania_foco]
    comp = sub[sub['compania'] != compania_foco]

    if yo.empty or comp.empty:
        return None

    p_yo = yo['precio_dia'].min()
    idx_riv = comp['precio_dia'].idxmin()
    p_riv = comp.loc[idx_riv, 'precio_dia']
    rival_mas_barato = comp.loc[idx_riv, 'compania']
    diff = p_yo - p_riv

    pos_yo = list(ranking['compania']).index(compania_foco) + 1 if compania_foco in list(ranking['compania']) else 0

    if diff > 0:
        estado = 'perdiendo'
        accion = f"⚠️ BAJA ${diff + 0.5:.2f}/día"
        detalle = f"{rival_mas_barato} está ${diff:.2f}/día más barato. Baja a ${p_riv - 0.5:.2f}/día para ser #1."
    elif diff < 0:
        estado = 'ganando'
        accion = "✅ ERES EL MÁS BARATO"
        detalle = f"Estás ${abs(diff):.2f}/día por debajo de {rival_mas_barato}."
    else:
        estado = 'empate'
        accion = "🟰 EMPATE"
        detalle = f"Baja $1 para diferenciarte de {rival_mas_barato}."

    return {
        'ranking': ranking,
        'estado': estado,
        'p_yo': p_yo,
        'p_riv': p_riv,
        'rival': rival_mas_barato,
        'diff': diff,
        'pos_yo': pos_yo,
        'accion': accion,
        'detalle': detalle,
    }


df_completo = cargar_datos()

if df_completo.empty:
    st.warning("### 📭 Sin datos")
    st.stop()

if not os.path.exists(FECHAS_ACTIVAS_PATH):
    st.error("### ⚠️ No hay fechas configuradas")
    st.stop()

with open(FECHAS_ACTIVAS_PATH, "r", encoding="utf-8") as f:
    fechas_activas_str = [line.strip() for line in f if line.strip()]

if not fechas_activas_str:
    st.error("### ⚠️ fechas_activas.txt vacío")
    st.stop()

fechas_dt = [pd.to_datetime(f).date() for f in fechas_activas_str]
df = df_completo[df_completo['fecha_recogida'].dt.date.isin(fechas_dt)].copy()

if df.empty:
    st.warning(f"### 📭 Sin datos para: {', '.join(fechas_activas_str)}")
    st.stop()

# Sidebar - filtros globales
st.sidebar.markdown("### 🎯 Compañía")
companias_disp = sorted(df['compania'].unique().tolist())
if MI_EMPRESA in companias_disp:
    companias_disp.remove(MI_EMPRESA)
    companias_disp.insert(0, MI_EMPRESA)
compania_foco = st.sidebar.selectbox("Compañía en foco", companias_disp, index=0, label_visibility="collapsed")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🚙 Filtros globales")

categorias_disp = sorted(df['categoria'].unique().tolist())
cat_filter = st.sidebar.multiselect("Categorías", categorias_disp, default=categorias_disp)

trans_disp = sorted(df['transmision'].unique().tolist())
trans_filter = st.sidebar.multiselect("Transmisiones", trans_disp, default=trans_disp)

dias_disp = sorted(df['dias'].unique().tolist())
dias_filter = st.sidebar.multiselect("Duraciones (días)", dias_disp, default=dias_disp)

# Aplicar filtros globales
df = df[df['categoria'].isin(cat_filter)]
df = df[df['transmision'].isin(trans_filter)]
df = df[df['dias'].isin(dias_filter)]

if df.empty:
    st.warning("### 📭 No hay datos con los filtros seleccionados")
    st.stop()

# Selector de fecha
fechas_disponibles = sorted(df['fecha_recogida'].dropna().dt.date.unique().tolist())
if not fechas_disponibles:
    st.warning("### 📭 No hay fechas disponibles con estos filtros")
    st.stop()

if "fecha_sel" not in st.session_state or st.session_state["fecha_sel"] not in fechas_disponibles:
    st.session_state["fecha_sel"] = fechas_disponibles[0]

st.markdown('<div style="color:#22D3EE; text-align:center; font-family:Courier New; '
            'font-size:15px; font-weight:bold; margin:15px 0 12px 0; letter-spacing:3px;">'
            '📅 ¿PARA QUÉ FECHA DE RECOGIDA?</div>', unsafe_allow_html=True)

cols_f = st.columns(min(len(fechas_disponibles), 5))
for i, fecha_op in enumerate(fechas_disponibles):
    with cols_f[i % len(cols_f)]:
        es_actual = (fecha_op == st.session_state["fecha_sel"])
        label = f"{'✅ ' if es_actual else ''}{fecha_op.strftime('%d')} {MESES_CORTO[fecha_op.month]}{' ✅' if es_actual else ''}"
        if st.button(label, key=f"btn_{fecha_op}", use_container_width=True):
            st.session_state["fecha_sel"] = fecha_op
            st.rerun()

fecha_sel = st.session_state["fecha_sel"]

st.markdown(
    f'<div style="background: linear-gradient(90deg, #22D3EE 0%, #06B6D4 100%); '
    f'padding: 14px 20px; border-radius: 10px; margin: 15px 0 20px 0; text-align: center;">'
    f'<div style="color:#000; font-size:11px; font-weight:bold; letter-spacing:3px;">'
    f'FECHA DE RECOGIDA</div>'
    f'<div style="color:#000; font-size:26px; font-weight:bold; margin-top:4px;">'
    f'{fecha_sel.strftime("%d/%m/%Y")}</div></div>',
    unsafe_allow_html=True,
)

df_f = df[df['fecha_recogida'].dt.date == fecha_sel].copy()

# Análisis global
combos = df_f.groupby(['dias', 'categoria', 'transmision']).size().reset_index(name='n')
analisis_global = []
for _, combo in combos.iterrows():
    sub = df_f[(df_f['dias'] == combo['dias']) &
               (df_f['categoria'] == combo['categoria']) &
               (df_f['transmision'] == combo['transmision'])]
    r = analizar_combinacion(sub, compania_foco)
    if r:
        r['dias'] = combo['dias']
        r['categoria'] = combo['categoria']
        r['transmision'] = combo['transmision']
        if r is not None:
            analisis_global.append(r)

ganando = sum(1 for r in analisis_global if r['estado'] == 'ganando')
perdiendo = sum(1 for r in analisis_global if r['estado'] == 'perdiendo')
empatando = sum(1 for r in analisis_global if r['estado'] == 'empate')
total = len(analisis_global)

# Banner
if total > 0:
    if perdiendo == 0:
        clase_banner, color_titulo = "action-win", "#10B981"
        titulo = "✅ ESTÁS GANANDO EN TODO"
        subtitulo = f"Eres el más barato en las {total} combinaciones. Mantén precios."
    elif ganando == 0:
        clase_banner, color_titulo = "action-lose", "#EF4444"
        titulo = f"⚠️ NECESITAS BAJAR PRECIOS EN {perdiendo} CATEGORÍAS"
        subtitulo = f"Ganas en {ganando} de {total}. Revisa el análisis abajo."
    else:
        clase_banner, color_titulo = "action-mixed", "#FBBF24"
        titulo = f"🎯 {ganando} GANANDO · {perdiendo} PERDIENDO · {empatando} EMPATANDO"
        subtitulo = "Revisa las combinaciones donde estás perdiendo."

    st.markdown(
        f'<div class="action-banner {clase_banner}">'
        f'<div class="action-title" style="color:{color_titulo};">{titulo}</div>'
        f'<div class="action-subtitle">{subtitulo}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown(
    f'<div class="kpi-grid">'
    f'<div class="kpi-item kpi-item-win"><div class="kpi-label">Ganando</div>'
    f'<div class="kpi-value" style="color:#10B981;">{ganando}</div>'
    f'<div class="kpi-sub">combinaciones</div></div>'
    f'<div class="kpi-item kpi-item-lose"><div class="kpi-label">Perdiendo</div>'
    f'<div class="kpi-value" style="color:#EF4444;">{perdiendo}</div>'
    f'<div class="kpi-sub">combinaciones</div></div>'
    f'<div class="kpi-item kpi-item-warn"><div class="kpi-label">Empates</div>'
    f'<div class="kpi-value" style="color:#FBBF24;">{empatando}</div>'
    f'<div class="kpi-sub">combinaciones</div></div>'
    f'<div class="kpi-item"><div class="kpi-label">Total</div>'
    f'<div class="kpi-value" style="color:#22D3EE;">{total}</div>'
    f'<div class="kpi-sub">analizadas</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="leyenda-box">'
    '<div class="leyenda-item"><span class="leyenda-dot" style="background:#10B981;"></span>GANAS</div>'
    '<div class="leyenda-item"><span class="leyenda-dot" style="background:#EF4444;"></span>BAJA</div>'
    '<div class="leyenda-item"><span class="leyenda-dot" style="background:#FBBF24;"></span>EMPATE</div>'
    '<div class="leyenda-item"><span class="leyenda-dot" style="background:#22D3EE;"></span>TU EMPRESA</div>'
    '</div>',
    unsafe_allow_html=True,
)

tab1, tab2, tab3, tab4 = st.tabs(["🎯 ANÁLISIS", "📋 PLAN", "📊 DATOS", "🤖 ANÁLISIS IA"])


with tab1:
    st.markdown("### 🎯 Análisis por combinación")
    st.caption("Ordenado por estado: perdiendo primero, luego empates, luego ganando.")

    # Filtros locales
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filtro_estado = st.radio("Estado", ["Todos", "🔴 Perdiendo", "🟡 Empates", "🟢 Ganando"],
                                  horizontal=True, key="filtro_estado")
    with col_f2:
        filtro_cat = st.selectbox("Categoría específica",
                                   ["Todas"] + sorted(df_f['categoria'].unique().tolist()),
                                   key="filtro_cat")

    analisis_filtrado = analisis_global.copy()
    if filtro_estado == "🔴 Perdiendo":
        analisis_filtrado = [a for a in analisis_filtrado if a['estado'] == 'perdiendo']
    elif filtro_estado == "🟡 Empates":
        analisis_filtrado = [a for a in analisis_filtrado if a['estado'] == 'empate']
    elif filtro_estado == "🟢 Ganando":
        analisis_filtrado = [a for a in analisis_filtrado if a['estado'] == 'ganando']
    if filtro_cat != "Todas":
        analisis_filtrado = [a for a in analisis_filtrado if a['categoria'] == filtro_cat]

    # Ordenar
    analisis_ordenado = sorted(analisis_filtrado,
                                key=lambda x: (x['estado'] != 'perdiendo',
                                               x['estado'] != 'empate',
                                               x['dias'], x['categoria']))

    if not analisis_ordenado:
        st.info("No hay combinaciones con los filtros seleccionados.")
    else:
        for a in analisis_ordenado:
            dias = a['dias']
            cat = a['categoria']
            trans = a['transmision']
            estado = a['estado']
            fecha_dev = fecha_sel + timedelta(days=int(dias))

            if estado == 'ganando':
                border_color = "#10B981"
            elif estado == 'perdiendo':
                border_color = "#EF4444"
            else:
                border_color = "#FBBF24"

            html = f'<div class="combo-card" style="border-color:{border_color};">'
            html += f'<div class="combo-header" style="border-bottom-color:{border_color};">'
            html += f'<div class="combo-title">⏱️ {dias} DÍAS · 🚗 {cat} · ⚙️ {trans}</div>'
            html += f'<div class="combo-dates">📅 {fecha_sel.strftime("%d/%m/%Y")} → {fecha_dev.strftime("%d/%m/%Y")}</div>'
            html += f'</div>'
            html += f'<div class="combo-body">'

            ranking = a['ranking']
            max_p = ranking['precio_min'].max()
            for idx, r in ranking.iterrows():
                es_mi = r['compania'] == compania_foco
                c = color_de(r['compania'])
                medal = ["🥇","🥈","🥉"][idx] if idx < 3 else f"#{idx+1}"
                marca = " ★ TÚ" if es_mi else ""
                pct_barra = max(((max_p - r['precio_min'] + 1) / max_p) * 100, 15)
                clase_row = "combo-row combo-row-yo" if es_mi else "combo-row"

                html += f'<div class="{clase_row}">'
                html += f'<div class="combo-medal">{medal}</div>'
                html += f'<div class="combo-name" style="color:{c};">{r["compania"]}{marca}</div>'
                html += f'<div class="combo-bar-wrap"><div class="combo-bar-bg">'
                html += f'<div class="combo-bar" style="width:{pct_barra}%; background:{c};"></div>'
                html += f'</div></div>'
                html += f'<div class="combo-price" style="color:{c};">${r["precio_min"]:.2f}/día</div>'
                html += f'<div class="combo-total">Total ${r["precio_total"]:.0f}</div>'
                html += f'</div>'

            html += f'</div><div class="combo-footer">'
            if estado == 'ganando':
                html += f'<div class="combo-action combo-action-win">{a["accion"]}</div>'
            elif estado == 'perdiendo':
                html += f'<div class="combo-action combo-action-lose">{a["accion"]}</div>'
            else:
                html += f'<div class="combo-action combo-action-tie">{a["accion"]}</div>'
            html += f'<div class="combo-action-sob">{a["detalle"]}</div>'
            html += f'</div></div>'

            st.markdown(html, unsafe_allow_html=True)


with tab2:
    st.markdown("### 📋 Plan de acción")
    st.caption("Ajustes exactos que necesitas hacer.")

    perdiendo_list = [a for a in analisis_global if a['estado'] == 'perdiendo']
    ganando_list = [a for a in analisis_global if a['estado'] == 'ganando']
    empate_list = [a for a in analisis_global if a['estado'] == 'empate']

    if perdiendo_list:
        st.markdown("#### 🔴 Urgente — Bajar precios")
        for a in sorted(perdiendo_list, key=lambda x: -x['diff']):
            fecha_dev = fecha_sel + timedelta(days=int(a['dias']))
            st.markdown(
                f'<div class="plan-item plan-item-urgent">'
                f'<div class="plan-title">⏱️ {a["dias"]} días · 🚗 {a["categoria"]} · ⚙️ {a["transmision"]}</div>'
                f'<div class="plan-detail">📅 {fecha_sel.strftime("%d/%m/%Y")} → {fecha_dev.strftime("%d/%m/%Y")}</div>'
                f'<div class="plan-detail" style="margin-top:8px;">'
                f'<b style="color:#EF4444;">BAJA a ${a["p_riv"] - 0.5:.2f}/día</b> '
                f'(ahora ${a["p_yo"]:.2f}). Rival: <b>{a["rival"]}</b> a ${a["p_riv"]:.2f}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.success("🎉 No hay acciones urgentes.")

    if empate_list:
        st.markdown("#### 🟡 Empates — Diferenciarte")
        for a in sorted(empate_list, key=lambda x: (x['dias'], x['categoria'])):
            st.markdown(
                f'<div class="plan-item plan-item-mid">'
                f'<div class="plan-title">⏱️ {a["dias"]} días · 🚗 {a["categoria"]} · ⚙️ {a["transmision"]}</div>'
                f'<div class="plan-detail">Empate con {a["rival"]}. Baja $1 para ganar.</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    if ganando_list:
        st.markdown("#### 🟢 Mantén precios")
        for a in sorted(ganando_list, key=lambda x: (x['dias'], x['categoria'])):
            fecha_dev = fecha_sel + timedelta(days=int(a['dias']))
            st.markdown(
                f'<div class="plan-item plan-item-ok">'
                f'<div class="plan-title">⏱️ {a["dias"]} días · 🚗 {a["categoria"]} · ⚙️ {a["transmision"]}</div>'
                f'<div class="plan-detail">📅 {fecha_sel.strftime("%d/%m/%Y")} → {fecha_dev.strftime("%d/%m/%Y")}</div>'
                f'<div class="plan-detail" style="margin-top:8px;">'
                f'<b style="color:#10B981;">MANTÉN ${a["p_yo"]:.2f}/día</b>. '
                f'Ganas por ${abs(a["diff"]):.2f} vs {a["rival"]}.</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


with tab3:
    st.markdown("### 📊 Datos crudos")

    # Filtros locales
    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        filtro_comp_datos = st.multiselect("Compañía",
                                            sorted(df_f['compania'].unique().tolist()),
                                            default=sorted(df_f['compania'].unique().tolist()),
                                            key="filtro_comp_datos")
    with col_d2:
        filtro_cat_datos = st.multiselect("Categoría",
                                           sorted(df_f['categoria'].unique().tolist()),
                                           default=sorted(df_f['categoria'].unique().tolist()),
                                           key="filtro_cat_datos")
    with col_d3:
        filtro_dias_datos = st.multiselect("Días",
                                            sorted(df_f['dias'].unique().tolist()),
                                            default=sorted(df_f['dias'].unique().tolist()),
                                            key="filtro_dias_datos")

    df_mostrar = df_f[
        (df_f['compania'].isin(filtro_comp_datos)) &
        (df_f['categoria'].isin(filtro_cat_datos)) &
        (df_f['dias'].isin(filtro_dias_datos))
    ].copy()

    df_mostrar['fecha_dev'] = df_mostrar.apply(
        lambda r: r['fecha_recogida'] + timedelta(days=int(r['dias'])), axis=1)

    def fmt_precio(v):
        return f"${v:.2f}" if pd.notna(v) and v > 0 else "—"

    df_mostrar['base_str'] = df_mostrar['precio_base'].apply(fmt_precio)
    df_mostrar['total_str'] = df_mostrar['precio_total'].apply(fmt_precio)
    df_mostrar['dia_str'] = df_mostrar['precio_dia'].apply(fmt_precio)
    df_mostrar['alquiler'] = df_mostrar.apply(
        lambda r: f"{r['fecha_recogida'].strftime('%d/%m/%Y')} → {r['fecha_dev'].strftime('%d/%m/%Y')}", axis=1)

    cols_show = ['compania', 'categoria', 'transmision', 'dias', 'alquiler',
                 'base_str', 'total_str', 'dia_str', 'plataforma']
    df_show = df_mostrar[cols_show].copy()
    df_show.columns = ['Compañía', 'Categoría', 'Transmisión', 'Días', 'Alquiler',
                       'Base', 'Total', 'Precio/día', 'Plataforma']

    def _colorear(row):
        color = color_de(row['Compañía'])
        return [f'background-color: {color}22; color: {color}; font-weight: bold'
                if col == 'Compañía' else '' for col in row.index]

    st.dataframe(df_show.style.apply(_colorear, axis=1),
                 use_container_width=True, height=500)

    st.caption(f"Mostrando {len(df_show)} de {len(df_f)} registros")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: ANÁLISIS CON IA
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    st.markdown("### 🤖 Análisis con Inteligencia Artificial")
    st.caption("Recomendaciones estratégicas generadas por IA local (Ollama + qwen2.5).")

    # Verificar que Ollama esté disponible
    try:
        from ia_analisis import ollama_disponible, analizar_competencia
        ollama_ok = ollama_disponible()
    except ImportError as e:
        ollama_ok = False
        st.error(f"❌ No se pudo importar ia_analisis.py: {e}")
        st.info("Verifica que el archivo ia_analisis.py exista en la carpeta del proyecto.")

    if not ollama_ok:
        st.warning(
            "### ⚠️ Ollama no está corriendo\n\n"
            "**Para activar el análisis IA:**\n\n"
            "1. Abre una terminal nueva\n"
            "2. Ejecuta:\n"
            "```bash\n"
            "ollama serve\n"
            "```\n\n"
            "3. Vuelve a cargar este dashboard"
        )
    else:
        # Preparar los datos para IA
        # Necesitamos: dias, categoria, transmision, p_yo, p_rival, rival, pos
        datos_ia = []
        for a in analisis_global:
            if not a or not isinstance(a, dict):
                continue
            if a.get("estado") == "sin_datos":
                continue
            # Verificar SOLO las claves esenciales
            if "dias" not in a or "categoria" not in a or "estado" not in a:
                continue
            # Usar .get() con defaults para el resto
            p_yo = a.get("p_yo")
            p_rival = a.get("p_riv")  # ← FIX: la función devuelve "p_riv" no "p_rival"
            if p_yo is None or p_rival is None:
                continue
            datos_ia.append({
                "dias": a.get("dias"),
                "categoria": a.get("categoria", "N/A"),
                "transmision": a.get("transmision", "N/A"),
                "p_yo": p_yo,
                "p_rival": p_rival,
                "rival": a.get("rival", "N/A"),
                "pos": a.get("pos_yo", 0),
            })

        # Hash para cache
        import hashlib
        hash_key = hashlib.md5(
            str(sorted([f"{d['dias']}{d['categoria']}{d['transmision']}{d['p_yo']}" for d in datos_ia])).encode()
        ).hexdigest()[:12]

        if "ia_cache_key" not in st.session_state:
            st.session_state["ia_cache_key"] = None
        if "ia_respuesta" not in st.session_state:
            st.session_state["ia_respuesta"] = None

        col_btn1, col_btn2 = st.columns([2, 1])
        with col_btn1:
            if st.button("🔮 Generar análisis con IA", type="primary", use_container_width=True):
                with st.spinner("🤖 La IA está analizando... (15-30 seg la primera vez)"):
                    respuesta = analizar_competencia(datos_ia, compania_foco)
                    st.session_state["ia_respuesta"] = respuesta
                    st.session_state["ia_cache_key"] = hash_key
                st.rerun()
        with col_btn2:
            if st.button("🔄 Limpiar análisis", use_container_width=True):
                st.session_state["ia_respuesta"] = None
                st.session_state["ia_cache_key"] = None
                st.rerun()

        # Mostrar resultado
        if st.session_state["ia_respuesta"]:
            st.markdown("---")

            # Info
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.metric("Combinaciones analizadas", len(datos_ia))
            with col_info2:
                st.metric("Compañía analizada", compania_foco)
            with col_info3:
                n_perdiendo = len([d for d in datos_ia if d["p_yo"] > d["p_rival"]])
                st.metric("Perdiendo en", f"{n_perdiendo} combinaciones",
                          delta=f"-{n_perdiendo}" if n_perdiendo > 0 else "OK",
                          delta_color="inverse")

            st.markdown("---")

            # Resultado IA formateado
            st.markdown(
                '<div style="background: linear-gradient(135deg, #0a0f1a 0%, #1a2333 100%); '
                'border: 2px solid #22D3EE; border-radius: 12px; padding: 24px; '
                'font-family: Courier New, monospace; color: #E6EDF3; '
                'line-height: 1.8; font-size: 13px; white-space: pre-wrap;">'
                f'{st.session_state["ia_respuesta"]}'
                '</div>',
                unsafe_allow_html=True
            )

            st.markdown("---")
            st.caption(
                "💡 Las recomendaciones se basan en los datos actuales. "
                "El análisis se cachea para no repetir la consulta a la IA."
            )
        else:
            st.info(
                "👆 **Pulsa el botón de arriba** para generar el análisis con IA.\n\n"
                "La IA va a analizar las " + str(len(datos_ia)) + " combinaciones "
                "y darte recomendaciones específicas de **qué precio poner** "
                "para superar a cada competidor."
            )

            # Preview de lo que va a analizar
            if datos_ia and len(datos_ia) > 0:
                df_preview = pd.DataFrame(datos_ia)
                if len(df_preview.columns) == 7:
                    df_preview.columns = ["Días", "Categoría", "Transmisión",
                                           "Precio", "Precio rival", "Rival", "Posición"]
                st.dataframe(df_preview, use_container_width=True, height=300)
            else:
                st.info("No se detectaron combinaciones con datos válidos.")

# ══════════════════════════════════════════════════════════════════════════════
