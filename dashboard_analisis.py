#!/usr/bin/env python3
"""
dashboard_analisis.py — Analizador de Precios por Fechas
Herramienta de inteligencia de mercado para alquiler de autos en UIO.
"""
from __future__ import annotations
import os, sqlite3
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import ollama

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
MODELO_IA = "qwen2.5:latest"

# Colores
VERDE_EUROPCAR = "#00B140"
VERDE_OSCURO = "#008C32"
GRIS_BG = "#0A0A0A"
GRIS_PANEL = "#141414"
GRIS_TEXTO = "#D0D0D0"
AMARILLO = "#FFD700"
ROJO = "#E63946"

st.set_page_config(page_title="Analizador de Precios · UIO", page_icon="🚗", layout="wide")

st.markdown(f"""
<style>
.stApp {{
    background-color: {GRIS_BG};
    color: {GRIS_TEXTO};
    font-family: 'Segoe UI', 'Helvetica', sans-serif;
}}
#MainMenu, header, footer {{visibility: hidden;}}

.titulo-principal {{
    font-size: 2rem;
    font-weight: 700;
    color: {VERDE_EUROPCAR};
    letter-spacing: 3px;
    text-align: center;
    margin-bottom: 4px;
    text-shadow: 0 0 15px rgba(0,177,64,0.4);
}}
.subtitulo {{
    text-align: center;
    color: #888;
    font-size: 0.85rem;
    letter-spacing: 2px;
    margin-top: 0;
    text-transform: uppercase;
}}
.linea-verde {{
    height: 3px;
    background: linear-gradient(90deg, transparent, {VERDE_EUROPCAR}, transparent);
    margin: 16px 0 24px 0;
}}

[data-testid="stMetricValue"] {{
    color: {VERDE_EUROPCAR};
    font-size: 1.6rem;
    font-weight: 700;
}}
[data-testid="stMetricLabel"] {{
    color: #999;
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 1px;
}}
[data-testid="stMetricDelta"] {{ font-size: 0.8rem; }}

.stTabs [data-baseweb="tab-list"] {{
    background-color: {GRIS_PANEL};
    gap: 2px;
    border-bottom: 2px solid {VERDE_EUROPCAR};
}}
.stTabs [data-baseweb="tab"] {{
    background-color: transparent;
    color: #999;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    font-size: 0.8rem;
    padding: 12px 20px;
}}
.stTabs [aria-selected="true"] {{
    background-color: {VERDE_EUROPCAR};
    color: white !important;
    box-shadow: 0 0 15px rgba(0,177,64,0.5);
}}

[data-testid="stDataFrame"] {{
    border: 1px solid {VERDE_EUROPCAR};
}}

h1, h2, h3 {{ color: {VERDE_EUROPCAR}; font-weight: 600; letter-spacing: 1px; }}

.stButton > button {{
    background-color: {VERDE_EUROPCAR};
    color: white;
    font-weight: 700;
    border: none;
    text-transform: uppercase;
    letter-spacing: 1px;
}}
.stButton > button:hover {{
    background-color: {VERDE_OSCURO};
}}

::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: {GRIS_BG}; }}
::-webkit-scrollbar-thumb {{ background: {VERDE_EUROPCAR}; border-radius: 4px; }}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="titulo-principal">ANALIZADOR DE PRECIOS POR FECHAS</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="subtitulo">Mercado de alquiler · Quito (UIO) · {datetime.now():%Y-%m-%d %H:%M}</div>',
    unsafe_allow_html=True)
st.markdown('<div class="linea-verde"></div>', unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# DATOS
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=15)
def cargar_datos():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df = pd.read_sql_query("SELECT * FROM historial_precios", conn)
        return df
    except Exception as e:
        st.error(f"Error DB: {e}")
        return pd.DataFrame()

df = cargar_datos()
if df.empty:
    st.warning("⚠️ No hay datos. Corre el scraper primero.")
    st.code('python scraper_expedia.py --fechas "2026-12-31,2027-01-25" --duraciones "3,5,7,15,21,30"')
    st.stop()

# Precio efectivo
df["precio_efectivo"] = df.apply(
    lambda r: r["precio_total"] if pd.notna(r["precio_total"]) and r["precio_total"]
    else (r["precio_estimado_ia"] if pd.notna(r["precio_estimado_ia"]) and r["precio_estimado_ia"] else 0),
    axis=1)
df["precio_dia_efectivo"] = (df["precio_efectivo"] / df["duracion_dias"]).round(2)
df["fecha_alquiler"] = df["fecha_alquiler"].astype(str)
df["es_europcar"] = df["compania"].str.lower().str.contains("europcar", na=False)

# ──────────────────────────────────────────────────────────────────────────────
# MÉTRICAS SUPERIORES
# ──────────────────────────────────────────────────────────────────────────────
sub = df[df["precio_efectivo"] > 0]
euro = sub[sub["es_europcar"]]
comp = sub[~sub["es_europcar"]]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("REGISTROS", len(df))
c2.metric("COMPAÑÍAS", df["compania"].nunique())
c3.metric("FECHAS", df["fecha_alquiler"].nunique())
if len(euro) > 0:
    c4.metric("EUROPCAR PROM/DÍA", f"${euro['precio_dia_efectivo'].mean():.2f}")
else:
    c4.metric("EUROPCAR PROM/DÍA", "—")
if len(comp) > 0:
    c5.metric("MERCADO PROM/DÍA", f"${comp['precio_dia_efectivo'].mean():.2f}")
else:
    c5.metric("MERCADO PROM/DÍA", "—")

st.markdown('<div class="linea-verde"></div>', unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# TABS
# ──────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📅 PRECIOS POR FECHA",
    "🏆 RANKINGS",
    "📊 COMPARATIVA EUROPCAR",
    "📈 CAMBIOS HISTÓRICOS",
    "🗄️ DATOS CRUDOS",
])

# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — PRECIOS POR FECHA
# ──────────────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Precios mínimos por fecha y duración")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        fechas = sorted(df["fecha_alquiler"].unique())
        f_sel = st.multiselect("Fecha de alquiler", fechas, default=fechas, key="t1_f")
    with col_f2:
        durs = sorted(df["duracion_dias"].unique())
        d_sel = st.multiselect("Duración (días)", durs, default=durs, key="t1_d")
    with col_f3:
        cats = sorted(df["categoria"].dropna().unique())
        c_sel = st.multiselect("Categoría", cats, default=cats, key="t1_c")

    fdf = df[
        df["fecha_alquiler"].isin(f_sel) &
        df["duracion_dias"].isin(d_sel) &
        df["categoria"].isin(c_sel) &
        (df["precio_efectivo"] > 0)
    ]

    if fdf.empty:
        st.info("No hay datos con esos filtros.")
    else:
        st.markdown("#### Precio mínimo por día (USD)")
        pivot = fdf.pivot_table(
            index="fecha_alquiler", columns="duracion_dias",
            values="precio_dia_efectivo", aggfunc="min"
        ).round(2)
        pivot.columns = [f"{c} días" for c in pivot.columns]
        st.dataframe(
            pivot.style.background_gradient(cmap="Greens", axis=None).format("${:.2f}"),
            use_container_width=True
        )

        st.markdown("#### Gráfico comparativo")
        fig = px.bar(
            fdf, x="duracion_dias", y="precio_dia_efectivo",
            color="compania", barmode="group",
            facet_col="fecha_alquiler",
            labels={"duracion_dias": "Duración (días)", "precio_dia_efectivo": "Precio/día (USD)"},
            color_discrete_map={"Europcar": VERDE_EUROPCAR},
        )
        fig.update_layout(
            plot_bgcolor=GRIS_PANEL, paper_bgcolor=GRIS_BG,
            font_color=GRIS_TEXTO, height=500,
            legend=dict(bgcolor=GRIS_PANEL),
        )
        st.plotly_chart(fig, use_container_width=True)

# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — RANKINGS
# ──────────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### Ranking de compañías por precio")

    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        fecha_r = st.selectbox("Fecha", sorted(df["fecha_alquiler"].unique()), key="t2_f")
    with col_r2:
        cat_r = st.selectbox("Categoría", sorted(df["categoria"].dropna().unique()), key="t2_c")
    with col_r3:
        dur_r = st.selectbox("Duración (días)", sorted(df["duracion_dias"].unique()), key="t2_d")

    rdf = df[
        (df["fecha_alquiler"] == fecha_r) &
        (df["categoria"] == cat_r) &
        (df["duracion_dias"] == dur_r) &
        (df["precio_efectivo"] > 0)
    ].copy()

    if rdf.empty:
        st.info("Sin datos para esta combinación.")
    else:
        rank = rdf.groupby("compania").agg(
            precio_min=("precio_dia_efectivo", "min"),
            precio_prom=("precio_dia_efectivo", "mean"),
            ofertas=("precio_dia_efectivo", "count"),
        ).round(2).sort_values("precio_min").reset_index()

        rank.insert(0, "Pos", range(1, len(rank) + 1))

        precio_euro = rank[rank["compania"].str.lower().str.contains("europcar", na=False)]["precio_min"]
        base = precio_euro.values[0] if len(precio_euro) > 0 else rank["precio_min"].iloc[0]

        def diff_vs_euro(row):
            d = row["precio_min"] - base
            pct = (d / base * 100) if base else 0
            return f"{'+' if d > 0 else ''}${d:.2f} ({'+' if pct > 0 else ''}{pct:.1f}%)"

        rank["vs Europcar"] = rank.apply(diff_vs_euro, axis=1)
        rank.columns = ["Pos", "Compañía", "Precio mín/día", "Precio prom/día", "Ofertas", "vs Europcar"]

        def resaltar(row):
            if "europcar" in str(row["Compañía"]).lower():
                return [f"background-color: {VERDE_EUROPCAR}; color: white; font-weight: bold;"] * len(row)
            return [""] * len(row)

        st.dataframe(
            rank.style.apply(resaltar, axis=1).format({
                "Precio mín/día": "${:.2f}",
                "Precio prom/día": "${:.2f}",
            }),
            use_container_width=True, hide_index=True
        )

        # Gráfico de barras
        fig = go.Figure()
        colores = [VERDE_EUROPCAR if "europcar" in c.lower() else "#4A4A4A" for c in rank["Compañía"]]
        fig.add_trace(go.Bar(
            x=rank["Compañía"], y=rank["Precio mín/día"],
            marker_color=colores,
            text=rank["Precio mín/día"].apply(lambda x: f"${x:.2f}"),
            textposition="outside",
        ))
        fig.update_layout(
            plot_bgcolor=GRIS_PANEL, paper_bgcolor=GRIS_BG,
            font_color=GRIS_TEXTO,
            title=f"Ranking · {fecha_r} · {cat_r} · {dur_r} días",
            title_font_color=VERDE_EUROPCAR,
            showlegend=False, height=450,
            yaxis_title="Precio/día (USD)",
        )
        st.plotly_chart(fig, use_container_width=True)

# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — COMPARATIVA EUROPCAR
# ──────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Europcar vs competencia")

    if len(euro) == 0:
        st.warning("No hay datos de Europcar en la base. Asegúrate de que el scraper capturó sus ofertas.")
    else:
        st.markdown("#### Resumen por categoría")
        comp_df = sub.copy()
        comp_df["grupo"] = comp_df["es_europcar"].map({True: "Europcar", False: "Competencia"})
        resumen = comp_df.groupby(["categoria", "grupo"]).agg(
            precio_min=("precio_dia_efectivo", "min"),
            precio_prom=("precio_dia_efectivo", "mean"),
            ofertas=("precio_dia_efectivo", "count"),
        ).round(2).reset_index()

        pivot_cat = resumen.pivot(index="categoria", columns="grupo", values="precio_prom").round(2)
        if "Europcar" in pivot_cat.columns and "Competencia" in pivot_cat.columns:
            pivot_cat["Diferencia"] = (pivot_cat["Europcar"] - pivot_cat["Competencia"]).round(2)
            pivot_cat["% vs Mercado"] = ((pivot_cat["Diferencia"] / pivot_cat["Competencia"]) * 100).round(1)

        st.dataframe(
            pivot_cat.style.format({
                "Europcar": "${:.2f}",
                "Competencia": "${:.2f}",
                "Diferencia": "${:+.2f}",
                "% vs Mercado": "{:+.1f}%",
            }, na_rep="—"),
            use_container_width=True
        )

        st.markdown("#### Posición de Europcar por fecha y duración")

        def posicion(grupo):
            if len(grupo) == 0:
                return None
            g = grupo.sort_values("precio_dia_efectivo")
            e = g[g["es_europcar"]]
            if len(e) == 0:
                return None
            return list(g.index).index(e.index[0]) + 1

        pos_df = df[df["precio_efectivo"] > 0].groupby(
            ["fecha_alquiler", "duracion_dias", "categoria"]
        ).apply(posicion).reset_index(name="Posición")

        if not pos_df.empty:
            pivot_pos = pos_df.pivot_table(
                index=["fecha_alquiler", "categoria"],
                columns="duracion_dias",
                values="Posición",
                aggfunc="first"
            )
            st.dataframe(pivot_pos, use_container_width=True)

# ──────────────────────────────────────────────────────────────────────────────
# TAB 4 — CAMBIOS HISTÓRICOS
# ──────────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown("### Evolución de precios en el tiempo")

    n_ejecuciones = df["fecha_consulta"].nunique()
    if n_ejecuciones < 2:
        st.info(f"Hay {n_ejecuciones} ejecución(es) del scraper. Corre el scraper varias veces a lo largo de los días para ver cambios aquí.")
    else:
        comp_sel = st.selectbox("Compañía", sorted(df["compania"].dropna().unique()), key="t4_c")
        cat_sel = st.selectbox("Categoría ", sorted(df["categoria"].dropna().unique()), key="t4_cat")
        dur_sel = st.selectbox("Duración ", sorted(df["duracion_dias"].unique()), key="t4_d")

        evol = df[
            (df["compania"] == comp_sel) &
            (df["categoria"] == cat_sel) &
            (df["duracion_dias"] == dur_sel)
        ].sort_values("fecha_consulta")

        if not evol.empty:
            fig = px.line(
                evol, x="fecha_consulta", y="precio_dia_efectivo",
                markers=True,
                title=f"Evolución · {comp_sel} · {cat_sel} · {dur_sel}d",
            )
            fig.update_traces(
                line_color=VERDE_EUROPCAR, marker_color=VERDE_EUROPCAR, line_width=3,
            )
            fig.update_layout(
                plot_bgcolor=GRIS_PANEL, paper_bgcolor=GRIS_BG,
                font_color=GRIS_TEXTO, height=450,
            )
            st.plotly_chart(fig, use_container_width=True)

# ──────────────────────────────────────────────────────────────────────────────
# TAB 5 — DATOS CRUDOS
# ──────────────────────────────────────────────────────────────────────────────
with tab5:
    st.markdown("### Datos completos extraídos de Expedia")

    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        comp_f = st.multiselect("Compañía", sorted(df["compania"].dropna().unique()), key="t5_c")
    with col_c2:
        trans_f = st.multiselect("Transmisión", sorted(df["transmision"].dropna().unique()), key="t5_t")
    with col_c3:
        solo_euro = st.checkbox("Solo Europcar", value=False)

    view = df.copy()
    if comp_f:
        view = view[view["compania"].isin(comp_f)]
    if trans_f:
        view = view[view["transmision"].isin(trans_f)]
    if solo_euro:
        view = view[view["es_europcar"]]

    cols = ["fecha_alquiler", "duracion_dias", "compania", "categoria",
            "transmision", "precio_total", "precio_dia", "precio_total_crudo",
            "rating", "reviews", "cancelacion_gratis", "url"]
    st.dataframe(view[cols], use_container_width=True, height=600)

    csv = view.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar CSV",
        csv,
        f"analisis_precios_{datetime.now():%Y%m%d_%H%M}.csv",
        "text/csv",
    )

# ──────────────────────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="linea-verde"></div>', unsafe_allow_html=True)
st.markdown(
    f'<div style="text-align:center; color:#666; font-size:0.75rem; letter-spacing:1px;">'
    f'Herramienta de análisis de mercado · Datos en vivo de Expedia · {len(df)} registros</div>',
    unsafe_allow_html=True
)
