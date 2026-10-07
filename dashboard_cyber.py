#!/usr/bin/env python3
"""dashboard_cyber.py — Dashboard Cyberpunk 2077."""
from __future__ import annotations
import os, sqlite3
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st
import ollama

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
MODELO_IA = "qwen2.5:latest"

st.set_page_config(page_title="CyberRent · UIO", page_icon="🏁", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #050505; color: #E5E5E5; }
#MainMenu, header, footer { visibility: hidden; }
h1, h2, h3 { color: #FCEE0A; text-transform: uppercase; letter-spacing: 2px; }
.cyber-title { font-size: 2.5rem; font-weight: 900; color: #FCEE0A;
    text-shadow: 0 0 20px #FCEE0A; text-align: center; letter-spacing: 6px; }
.cyber-subtitle { text-align: center; color: #00F0FF; letter-spacing: 4px; }
.stTabs [data-baseweb="tab-list"] { background-color: #0F0F0F; gap: 4px; }
.stTabs [data-baseweb="tab"] { color: #888; font-weight: 700; letter-spacing: 2px;
    text-transform: uppercase; padding: 12px 24px; }
.stTabs [aria-selected="true"] { background-color: #FCEE0A; color: #050505 !important;
    box-shadow: 0 0 20px rgba(252,238,10,0.6); }
[data-testid="stMetricValue"] { color: #FCEE0A; font-weight: 800; }
[data-testid="stMetricLabel"] { color: #00F0FF; text-transform: uppercase; }
.stButton > button { background-color: #FCEE0A; color: #050505; font-weight: 800;
    text-transform: uppercase; border: none; }
.stButton > button:hover { background-color: #00F0FF; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="cyber-title">CYBERRENT · UIO</div>', unsafe_allow_html=True)
st.markdown(f'<div class="cyber-subtitle">Expedia Intel · {datetime.now():%Y-%m-%d %H:%M}</div>', unsafe_allow_html=True)
st.markdown("---")

@st.cache_data(ttl=10)
def cargar_datos():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query("SELECT * FROM historial_precios", conn)

df = cargar_datos()
if df.empty:
    st.warning("⚠️ No hay datos. Corre el scraper primero.")
    st.stop()

df["precio_efectivo"] = df.apply(
    lambda r: r["precio_total"] if pd.notna(r["precio_total"]) and r["precio_total"] else (
        r["precio_estimado_ia"] if pd.notna(r["precio_estimado_ia"]) and r["precio_estimado_ia"] else 0),
    axis=1)
df["precio_dia_efectivo"] = df["precio_efectivo"] / df["duracion_dias"]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("REGISTROS", len(df))
c2.metric("COMPAÑÍAS", df["compania"].nunique())
c3.metric("CATEGORÍAS", df["categoria"].nunique())
sub = df[df["precio_efectivo"] > 0]
c4.metric("PRECIO MIN", f"${sub['precio_dia_efectivo'].min():.2f}" if len(sub) else "$0")
c5.metric("PRECIO MAX", f"${sub['precio_dia_efectivo'].max():.2f}" if len(sub) else "$0")

st.markdown("---")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["💰 PRECIOS", "🏆 RANKING", "📈 CAMBIOS", "🗄️ DATOS", "🤖 IA"])

with tab1:
    st.subheader("Precio por fecha y duración")
    pivot = df[df["precio_efectivo"] > 0].pivot_table(
        index="fecha_alquiler", columns="duracion_dias",
        values="precio_dia_efectivo", aggfunc="min").round(2)
    st.dataframe(pivot, use_container_width=True)
    fig = px.bar(sub, x="duracion_dias", y="precio_dia_efectivo",
                 color="compania", barmode="group", facet_col="fecha_alquiler")
    fig.update_layout(plot_bgcolor="#0F0F0F", paper_bgcolor="#0F0F0F", font_color="#E5E5E5")
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Ranking")
    cat = st.selectbox("Categoría", sorted(df["categoria"].dropna().unique()))
    dur = st.selectbox("Duración", sorted(df["duracion_dias"].unique()))
    r = df[(df["categoria"] == cat) & (df["duracion_dias"] == dur) & (df["precio_efectivo"] > 0)]
    if not r.empty:
        rk = r.groupby("compania")["precio_dia_efectivo"].min().round(2).sort_values().reset_index()
        rk.columns = ["Compañía", "Precio/día mínimo"]
        rk.index = range(1, len(rk) + 1)
        st.dataframe(rk, use_container_width=True)
    else:
        st.info("Sin datos")

with tab3:
    st.subheader("Cambios de precio")
    if df["fecha_consulta"].nunique() > 1:
        st.info("La tabla de cambios se generará con ia_analisis.py (aún no construido).")
    else:
        st.info("Corre el scraper al menos 2 veces para ver cambios.")

with tab4:
    st.subheader("Datos crudos")
    st.dataframe(df, use_container_width=True)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ CSV", csv, f"cyberrent_{datetime.now():%Y%m%d}.csv")

with tab5:
    st.subheader("Asistente IA (Qwen 2.5)")
    if "msgs" not in st.session_state:
        st.session_state.msgs = []
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    p = st.chat_input("Pregunta sobre los precios...")
    if p:
        st.session_state.msgs.append({"role": "user", "content": p})
        with st.chat_message("user"):
            st.markdown(p)
        ctx = df.groupby(["compania", "categoria", "duracion_dias"])["precio_dia_efectivo"].agg(
            ["min", "mean"]).round(2).reset_index().to_string(index=False)[:3000]
        sys_p = f"Eres analista de alquiler de autos en Quito. Datos:\n{ctx}\nResponde en español, directo."
        with st.chat_message("assistant"):
            with st.spinner("..."):
                try:
                    resp = ollama.chat(model=MODELO_IA, messages=[
                        {"role": "system", "content": sys_p},
                        {"role": "user", "content": p}])
                    ans = resp["message"]["content"]
                except Exception as e:
                    ans = f"⚠️ Error: {e}"
            st.markdown(ans)
        st.session_state.msgs.append({"role": "assistant", "content": ans})
