#!/usr/bin/env python3
"""
dashboard_v3.py — Analizador de precios · UIO
Con Chat IA, exportación a Excel y reporte ejecutivo.
"""
from __future__ import annotations

import io
import os
import sqlite3
from datetime import datetime

import ollama
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
MODELO_IA = "qwen2.5:latest"

VERDE = "#00B140"
VERDE_OSC = "#008C32"
AZUL = "#00E5FF"
ROJO = "#FF2E4D"
AMARILLO = "#FFD700"
NEGRO = "#050505"
PANEL = "#0D0D0D"
TEXTO = "#E0E0E0"

st.set_page_config(page_title="Analizador de Precios · UIO", page_icon="🏁", layout="wide")

st.markdown(f"""
<style>
.stApp {{ background-color: {NEGRO}; color: {TEXTO}; font-family: 'Segoe UI', sans-serif; }}
#MainMenu, header, footer {{visibility: hidden;}}
.titulo {{
    font-size: 2.2rem; font-weight: 900; color: {VERDE};
    letter-spacing: 4px; text-align: center; margin-bottom: 2px;
    text-shadow: 0 0 25px {VERDE}, 0 0 50px {VERDE}88;
}}
.subtitulo {{
    text-align: center; color: {AZUL}; font-size: 0.85rem;
    letter-spacing: 3px; text-transform: uppercase;
    text-shadow: 0 0 10px {AZUL};
}}
.linea {{
    height: 2px; background: linear-gradient(90deg, transparent, {AZUL}, transparent);
    margin: 16px 0 24px 0;
}}
.fecha-card {{
    background: linear-gradient(135deg, rgba(0,229,255,0.12), rgba(0,229,255,0.03));
    border: 2px solid {AZUL};
    border-radius: 14px;
    padding: 20px 16px;
    text-align: center;
    box-shadow: 0 0 25px {AZUL}66, inset 0 0 25px {AZUL}22;
}}
.fecha-card .label {{ color: {AZUL}; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 3px; }}
.fecha-card .fecha {{ color: white; font-size: 1.5rem; font-weight: 800; margin-top: 6px; }}
.fecha-card .sub {{ color: #999; font-size: 0.75rem; margin-top: 4px; }}
.fecha-card .precio {{ color: {VERDE}; font-size: 1.1rem; font-weight: 700; margin-top: 8px; text-shadow: 0 0 8px {VERDE}; }}
[data-testid="stMetricValue"] {{ color: {VERDE}; font-size: 1.6rem; font-weight: 800; }}
[data-testid="stMetricLabel"] {{ color: {AZUL}; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 1px; }}
.stTabs [data-baseweb="tab-list"] {{ background-color: {PANEL}; gap: 2px; border-bottom: 2px solid {VERDE}; }}
.stTabs [data-baseweb="tab"] {{
    background-color: transparent; color: #888; font-weight: 700;
    letter-spacing: 2px; text-transform: uppercase; font-size: 0.8rem; padding: 14px 20px;
}}
.stTabs [aria-selected="true"] {{ background-color: {VERDE}; color: white !important; }}
h1, h2, h3 {{ color: {VERDE}; font-weight: 700; letter-spacing: 1px; }}
.stButton > button {{
    background-color: {VERDE}; color: white; font-weight: 800;
    border: none; text-transform: uppercase; letter-spacing: 1px;
}}
.stButton > button:hover {{ background-color: {VERDE_OSC}; }}
.alerta-critica {{ background: {ROJO}22; border-left: 4px solid {ROJO}; padding: 12px 16px; border-radius: 8px; margin: 6px 0; }}
.alerta-oport {{ background: {VERDE}22; border-left: 4px solid {VERDE}; padding: 12px 16px; border-radius: 8px; margin: 6px 0; }}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="titulo">ANALIZADOR DE PRECIOS</div>', unsafe_allow_html=True)
st.markdown(f'<div class="subtitulo">Inteligencia de Mercado · Quito UIO · {datetime.now():%Y-%m-%d %H:%M}</div>', unsafe_allow_html=True)
st.markdown('<div class="linea"></div>', unsafe_allow_html=True)


@st.cache_data(ttl=15)
def cargar_datos():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            return pd.read_sql_query("SELECT * FROM historial_precios", conn)
    except Exception as e:
        st.error(f"Error DB: {e}")
        return pd.DataFrame()


df = cargar_datos()
if df.empty:
    st.warning("⚠️ No hay datos.")
    st.stop()

df["precio_efectivo"] = df.apply(
    lambda r: r["precio_total"] if pd.notna(r["precio_total"]) and r["precio_total"]
    else (r["precio_estimado_ia"] if "precio_estimado_ia" in r and pd.notna(r["precio_estimado_ia"]) and r["precio_estimado_ia"] else 0),
    axis=1)
df["precio_dia_efectivo"] = (df["precio_efectivo"] / df["duracion_dias"]).round(2)
df["fecha_alquiler"] = df["fecha_alquiler"].astype(str)
df["es_europcar"] = df["compania"].str.lower().str.contains("europcar", na=False)

fechas_unicas = sorted(df["fecha_alquiler"].unique())
durs_unicas = sorted(df["duracion_dias"].unique())
cats_unicas = sorted(df["categoria"].dropna().unique())
comps_unicas = sorted(df["compania"].dropna().unique())

# ── CARDS DE FECHAS ────────────────────────────────────────────────────────
st.markdown("### 📅 Fechas en análisis")
if len(fechas_unicas) > 0:
    cols = st.columns(min(len(fechas_unicas), 4))
    for i, fecha in enumerate(fechas_unicas[:4]):
        sub_f = df[(df["fecha_alquiler"] == fecha) & (df["precio_efectivo"] > 0)]
        n_regs = len(sub_f)
        n_comp = sub_f["compania"].nunique()
        pmin = sub_f["precio_dia_efectivo"].min() if not sub_f.empty else 0
        pmax = sub_f["precio_dia_efectivo"].max() if not sub_f.empty else 0
        with cols[i]:
            st.markdown(f"""
            <div class="fecha-card">
                <div class="label">Fecha de alquiler</div>
                <div class="fecha">{fecha}</div>
                <div class="sub">{n_regs} ofertas · {n_comp} compañías</div>
                <div class="precio">${pmin:.0f} - ${pmax:.0f}/día</div>
            </div>
            """, unsafe_allow_html=True)

st.markdown('<div class="linea"></div>', unsafe_allow_html=True)

# ── MÉTRICAS ───────────────────────────────────────────────────────────────
sub = df[df["precio_efectivo"] > 0]
euro = sub[sub["es_europcar"]]
comp = sub[~sub["es_europcar"]]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("REGISTROS", len(df))
c2.metric("COMPAÑÍAS", df["compania"].nunique())
c3.metric("FECHAS", len(fechas_unicas))
c4.metric("EUROPCAR PROM/DÍA", f"${euro['precio_dia_efectivo'].mean():.2f}" if len(euro) else "—")
c5.metric("MERCADO PROM/DÍA", f"${comp['precio_dia_efectivo'].mean():.2f}" if len(comp) else "—")

st.markdown('<div class="linea"></div>', unsafe_allow_html=True)


# ── EXPORTAR A EXCEL ────────────────────────────────────────────────────────
def generar_excel(df: pd.DataFrame) -> bytes:
    """Genera Excel profesional con múltiples hojas."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        wb = writer.book
        fmt_title = wb.add_format({"bold": True, "font_size": 14, "bg_color": "#00B140",
                                     "font_color": "white", "align": "center", "valign": "vcenter"})
        fmt_header = wb.add_format({"bold": True, "bg_color": "#0D0D0D", "font_color": "#00B140",
                                      "border": 1, "align": "center"})
        fmt_money = wb.add_format({"num_format": "$#,##0.00", "border": 1})
        fmt_text = wb.add_format({"border": 1})
        fmt_euro = wb.add_format({"num_format": "$#,##0.00", "border": 1, "bg_color": "#C8E6C9", "bold": True})

        # Hoja 1: Datos completos
        sheet = wb.add_worksheet("Datos Completos")
        sheet.write(0, 0, "Datos extraídos de Expedia · Análisis de competencia UIO", fmt_title)
        sheet.merge_range(0, 0, 0, 12, "Datos extraídos de Expedia · Análisis de competencia UIO", fmt_title)
        headers = ["Fecha Alquiler", "Duración (d)", "Compañía", "Categoría", "Transmisión",
                   "Precio Total", "Precio/Día", "Rating", "Cancelación Gratis", "URL"]
        for i, h in enumerate(headers):
            sheet.write(2, i, h, fmt_header)
        sheet.set_column(0, 0, 14)
        sheet.set_column(1, 1, 12)
        sheet.set_column(2, 2, 14)
        sheet.set_column(3, 3, 14)
        sheet.set_column(4, 4, 12)
        sheet.set_column(5, 5, 12)
        sheet.set_column(6, 6, 12)
        sheet.set_column(7, 7, 10)
        sheet.set_column(8, 8, 16)
        sheet.set_column(9, 9, 30)

        for r, (_, row) in enumerate(df.iterrows(), start=3):
            sheet.write(r, 0, str(row["fecha_alquiler"]), fmt_text)
            sheet.write_number(r, 1, int(row["duracion_dias"]), fmt_text)
            sheet.write(r, 2, str(row["compania"]), fmt_euro if row["es_europcar"] else fmt_text)
            sheet.write(r, 3, str(row["categoria"]), fmt_text)
            sheet.write(r, 4, str(row["transmision"]), fmt_text)
            if pd.notna(row["precio_total"]):
                sheet.write_number(r, 5, float(row["precio_total"]), fmt_money)
            if pd.notna(row["precio_dia_efectivo"]):
                sheet.write_number(r, 6, float(row["precio_dia_efectivo"]), fmt_money)
            if pd.notna(row.get("rating")):
                sheet.write_number(r, 7, float(row["rating"]), fmt_text)
            sheet.write(r, 8, "SÍ" if row.get("cancelacion_gratis") else "NO", fmt_text)
            sheet.write(r, 9, str(row.get("url", "")), fmt_text)

        # Hoja 2: Ranking por categoría
        sheet2 = wb.add_worksheet("Ranking")
        sheet2.merge_range(0, 0, 0, 8, "Ranking de compañías por precio · mínimo por categoría y duración", fmt_title)
        r = 2
        for fecha in fechas_unicas:
            for dur in durs_unicas:
                sub_fd = df[(df["fecha_alquiler"] == fecha) & (df["duracion_dias"] == dur) & (df["precio_efectivo"] > 0)]
                if sub_fd.empty:
                    continue
                sheet2.write(r, 0, f"{fecha} · {dur} días", fmt_header)
                r += 1
                headers2 = ["Pos", "Compañía", "Categoría", "Precio Mín/Día", "Precio Prom/Día", "Ofertas"]
                for i, h in enumerate(headers2):
                    sheet2.write(r, i, h, fmt_header)
                r += 1
                rank = sub_fd.groupby(["compania", "categoria"]).agg(
                    pmin=("precio_dia_efectivo", "min"),
                    pprom=("precio_dia_efectivo", "mean"),
                    n=("precio_dia_efectivo", "count"),
                ).round(2).sort_values("pmin").reset_index()
                for pos, (_, rr) in enumerate(rank.iterrows(), 1):
                    sheet2.write_number(r, 0, pos, fmt_text)
                    sheet2.write(r, 1, rr["compania"], fmt_euro if "europcar" in str(rr["compania"]).lower() else fmt_text)
                    sheet2.write(r, 2, rr["categoria"], fmt_text)
                    sheet2.write_number(r, 3, float(rr["pmin"]), fmt_money)
                    sheet2.write_number(r, 4, float(rr["pprom"]), fmt_money)
                    sheet2.write_number(r, 5, int(rr["n"]), fmt_text)
                    r += 1
                r += 1
        sheet2.set_column(0, 0, 6)
        sheet2.set_column(1, 5, 16)

        # Hoja 3: Europcar vs Mercado
        sheet3 = wb.add_worksheet("Europcar vs Mercado")
        sheet3.merge_range(0, 0, 0, 5, "Europcar vs Mercado · por categoría", fmt_title)
        headers3 = ["Categoría", "Europcar Mín", "Europcar Prom", "Mercado Mín", "Mercado Prom", "% vs Mercado"]
        for i, h in enumerate(headers3):
            sheet3.write(2, i, h, fmt_header)
        if len(euro):
            for cat in cats_unicas:
                e_cat = euro[euro["categoria"] == cat]
                m_cat = comp[comp["categoria"] == cat]
                if len(e_cat) == 0:
                    continue
                ep = e_cat["precio_dia_efectivo"].mean()
                mp = m_cat["precio_dia_efectivo"].mean() if len(m_cat) else 0
                pct = ((ep - mp) / mp * 100) if mp else 0
                r = sheet3.dim_rowmax + 1
                sheet3.write(r, 0, cat, fmt_text)
                sheet3.write_number(r, 1, e_cat["precio_dia_efectivo"].min(), fmt_money)
                sheet3.write_number(r, 2, ep, fmt_money)
                if len(m_cat):
                    sheet3.write_number(r, 3, m_cat["precio_dia_efectivo"].min(), fmt_money)
                    sheet3.write_number(r, 4, mp, fmt_money)
                else:
                    sheet3.write(r, 3, "—", fmt_text)
                    sheet3.write(r, 4, "—", fmt_text)
                sheet3.write(r, 5, f"{pct:+.1f}%", fmt_text)
        sheet3.set_column(0, 5, 16)

    return buf.getvalue()


# ── TABS ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📅 PRECIOS", "🏆 RANKINGS", "⚔️ EUROPCAR VS MERCADO",
    "🔔 ALERTAS", "🗄️ DATOS", "🤖 CHAT IA"
])

with tab1:
    st.markdown("### Precios por fecha y duración")
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        f_sel = st.multiselect("Fecha", fechas_unicas, default=fechas_unicas, key="t1f")
    with col_f2:
        d_sel = st.multiselect("Duración", durs_unicas, default=durs_unicas, key="t1d")
    with col_f3:
        c_sel = st.multiselect("Categoría", cats_unicas, default=cats_unicas, key="t1c")

    fdf = df[df["fecha_alquiler"].isin(f_sel) & df["duracion_dias"].isin(d_sel)
             & df["categoria"].isin(c_sel) & (df["precio_efectivo"] > 0)]

    if not fdf.empty:
        pivot = fdf.pivot_table(index="fecha_alquiler", columns="duracion_dias",
                                 values="precio_dia_efectivo", aggfunc="min").round(2)
        pivot.columns = [f"{c}d" for c in pivot.columns]
        st.dataframe(pivot, use_container_width=True)

        fig = px.bar(fdf, x="duracion_dias", y="precio_dia_efectivo",
                     color="compania", barmode="group", facet_col="fecha_alquiler",
                     color_discrete_map={"Europcar": VERDE})
        fig.update_layout(plot_bgcolor=PANEL, paper_bgcolor=NEGRO, font_color=TEXTO, height=500)
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.markdown("### Ranking de compañías")
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        fecha_r = st.selectbox("Fecha", fechas_unicas, key="t2f")
    with col_r2:
        cat_r = st.selectbox("Categoría", cats_unicas, key="t2c")
    with col_r3:
        dur_r = st.selectbox("Duración", durs_unicas, key="t2d")

    rdf = df[(df["fecha_alquiler"] == fecha_r) & (df["categoria"] == cat_r)
             & (df["duracion_dias"] == dur_r) & (df["precio_efectivo"] > 0)]

    if not rdf.empty:
        rank = rdf.groupby("compania").agg(
            precio_min=("precio_dia_efectivo", "min"),
            precio_prom=("precio_dia_efectivo", "mean"),
            ofertas=("precio_dia_efectivo", "count"),
        ).round(2).sort_values("precio_min").reset_index()

        base_euro = rank[rank["compania"].str.lower().str.contains("europcar", na=False)]["precio_min"]
        base = base_euro.values[0] if len(base_euro) else rank["precio_min"].iloc[0]
        rank["vs_euro"] = ((rank["precio_min"] - base) / base * 100).round(1)
        medallas = ["🥇", "🥈", "🥉"]
        rank.insert(0, "Medalla", [medallas[i] if i < 3 else "  " for i in range(len(rank))])

        colores = [VERDE if "europcar" in c.lower() else AZUL for c in rank["compania"]]
        fig = go.Figure(go.Bar(
            y=rank["compania"][::-1], x=rank["precio_min"][::-1], orientation="h",
            marker_color=colores[::-1],
            text=[f"${p:.2f}" for p in rank["precio_min"][::-1]], textposition="outside",
        ))
        fig.update_layout(plot_bgcolor=PANEL, paper_bgcolor=NEGRO, font_color=TEXTO,
                            height=max(350, len(rank) * 40), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        tabla = rank.copy()
        tabla["vs_euro"] = tabla["vs_euro"].apply(lambda x: f"{x:+.1f}%")

        def color_fila(row):
            if "europcar" in str(row["compania"]).lower():
                return [f"background-color: {VERDE}33; font-weight: bold;"] * len(row)
            return [""] * len(row)

        st.dataframe(
            tabla[["Medalla", "compania", "precio_min", "precio_prom", "ofertas", "vs_euro"]]
            .style.apply(color_fila, axis=1)
            .format({"precio_min": "${:.2f}", "precio_prom": "${:.2f}"}),
            use_container_width=True, hide_index=True)

with tab3:
    st.markdown("### Europcar vs Mercado")
    if euro.empty:
        st.warning("No hay datos de Europcar.")
    else:
        rows = []
        for cat in cats_unicas:
            e = euro[euro["categoria"] == cat]
            m = comp[comp["categoria"] == cat]
            if len(e) == 0:
                continue
            ep = e["precio_dia_efectivo"].mean()
            mp = m["precio_dia_efectivo"].mean() if len(m) else 0
            pct = ((ep - mp) / mp * 100) if mp else 0
            rows.append({"Categoría": cat, "Europcar": ep, "Mercado": mp,
                         "Diferencia $": ep - mp, "% vs Mercado": pct})
        if rows:
            tabla = pd.DataFrame(rows).round(2)
            def col_pct(v):
                if pd.isna(v): return ""
                return f"color: {ROJO}; font-weight: bold;" if v > 0 else f"color: {VERDE}; font-weight: bold;"
            st.dataframe(
                tabla.style.map(col_pct, subset=["% vs Mercado"]).format({
                    "Europcar": "${:.2f}", "Mercado": "${:.2f}",
                    "Diferencia $": "${:+.2f}", "% vs Mercado": "{:+.1f}%"}),
                use_container_width=True, hide_index=True)

with tab4:
    st.markdown("### Alertas de cambio")
    n_ejec = df["fecha_consulta"].nunique() if "fecha_consulta" in df.columns else 0
    if n_ejec < 2:
        st.info(f"Hay {n_ejec} ejecución(es). Corre el scraper varios días para detectar cambios.")
    else:
        st.success(f"{n_ejec} ejecuciones detectadas. Comparando...")

with tab5:
    st.markdown("### Datos completos")
    st.dataframe(df, use_container_width=True, height=600)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ CSV", csv, f"datos_{datetime.now():%Y%m%d}.csv", "text/csv",
                            use_container_width=True)
    with col_d2:
        excel_bytes = generar_excel(df)
        st.download_button(
            "📊 EXCEL (con formato)",
            excel_bytes,
            f"analisis_competencia_{datetime.now():%Y%m%d}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)

with tab6:
    st.markdown("### Asistente IA · Qwen 2.5 local")
    st.caption("Pregunta lo que quieras sobre los datos. La IA responde con información real.")

    if "chat_msgs" not in st.session_state:
        st.session_state.chat_msgs = []

    for m in st.session_state.chat_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    p = st.chat_input("Ej: ¿En qué categoría Europcar está más caro que el mercado?")
    if p:
        st.session_state.chat_msgs.append({"role": "user", "content": p})
        with st.chat_message("user"):
            st.markdown(p)

        # Contexto compacto para la IA
        resumen = sub.groupby(["compania", "categoria", "duracion_dias"]).agg(
            pmin=("precio_dia_efectivo", "min"),
            pprom=("precio_dia_efectivo", "mean")).round(2).reset_index()
        contexto = resumen.to_string(index=False)[:3500]

        system = f"""Eres un analista experto en alquiler de autos en Quito, Ecuador.
Trabajas para Europcar. Analizas la competencia.

DATOS REALES (compañía | categoría | duración días | precio mín/día | precio prom/día):

{contexto}

Responde en español, claro, directo, con números concretos. Máximo 4 frases."""

        with st.chat_message("assistant"):
            with st.spinner("Analizando..."):
                try:
                    resp = ollama.chat(model=MODELO_IA, messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": p}])
                    ans = resp["message"]["content"]
                except Exception as e:
                    ans = f"⚠️ Error: {e}"
            st.markdown(ans)

        st.session_state.chat_msgs.append({"role": "assistant", "content": ans})

st.markdown('<div class="linea"></div>', unsafe_allow_html=True)
st.markdown(f'<div style="text-align:center;color:#666;font-size:0.7rem;">'
            f'{len(df)} registros · {df["compania"].nunique()} compañías · '
            f'{len(fechas_unicas)} fechas · {len(durs_unicas)} duraciones</div>',
            unsafe_allow_html=True)
