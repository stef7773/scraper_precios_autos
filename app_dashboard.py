#!/usr/bin/env python3
"""
dashboard_final.py — Analizador de Precios · UIO
Europcar Competitive Intelligence
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")

# Colores
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

/* Cards de fecha estilo neón azul */
.fecha-card {{
    background: linear-gradient(135deg, rgba(0,229,255,0.12), rgba(0,229,255,0.03));
    border: 2px solid {AZUL};
    border-radius: 14px;
    padding: 20px 16px;
    text-align: center;
    box-shadow: 0 0 25px {AZUL}66, inset 0 0 25px {AZUL}22;
    transition: all 0.3s ease;
}}
.fecha-card:hover {{
    box-shadow: 0 0 40px {AZUL}, inset 0 0 30px {AZUL}33;
    transform: translateY(-3px);
}}
.fecha-card .label {{ color: {AZUL}; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 3px; }}
.fecha-card .fecha {{ color: white; font-size: 1.5rem; font-weight: 800; margin-top: 6px; letter-spacing: 1px; }}
.fecha-card .sub {{ color: #999; font-size: 0.75rem; margin-top: 4px; }}
.fecha-card .precio {{ color: {VERDE}; font-size: 1.1rem; font-weight: 700; margin-top: 8px; text-shadow: 0 0 8px {VERDE}; }}

/* Métricas */
[data-testid="stMetricValue"] {{ color: {VERDE}; font-size: 1.6rem; font-weight: 800; }}
[data-testid="stMetricLabel"] {{ color: {AZUL}; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 1px; }}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {{ background-color: {PANEL}; gap: 2px; border-bottom: 2px solid {VERDE}; }}
.stTabs [data-baseweb="tab"] {{
    background-color: transparent; color: #888; font-weight: 700;
    letter-spacing: 2px; text-transform: uppercase; font-size: 0.8rem; padding: 14px 20px;
}}
.stTabs [aria-selected="true"] {{ background-color: {VERDE}; color: white !important; box-shadow: 0 0 20px {VERDE}88; }}

/* Alertas */
.alerta-critica {{
    background: linear-gradient(90deg, {ROJO}33, {ROJO}11);
    border-left: 4px solid {ROJO}; padding: 14px 18px; border-radius: 8px;
    margin: 8px 0; box-shadow: 0 0 15px {ROJO}44;
}}
.alerta-info {{
    background: linear-gradient(90deg, {AZUL}33, {AZUL}11);
    border-left: 4px solid {AZUL}; padding: 14px 18px; border-radius: 8px;
    margin: 8px 0;
}}
.alerta-oport {{
    background: linear-gradient(90deg, {VERDE}33, {VERDE}11);
    border-left: 4px solid {VERDE}; padding: 14px 18px; border-radius: 8px;
    margin: 8px 0;
}}
.alerta-titulo {{ font-weight: 800; letter-spacing: 1px; text-transform: uppercase; font-size: 0.8rem; }}

/* Medallas */
.medalla {{ font-size: 1.3rem; margin-right: 6px; }}

/* Botones */
.stButton > button {{
    background-color: {VERDE}; color: white; font-weight: 800;
    border: none; text-transform: uppercase; letter-spacing: 1px;
    box-shadow: 0 0 15px {VERDE}55;
}}
.stButton > button:hover {{ background-color: {VERDE_OSC}; box-shadow: 0 0 25px {VERDE}; }}

h1, h2, h3 {{ color: {VERDE}; font-weight: 700; letter-spacing: 1px; }}
</style>
""", unsafe_allow_html=True)

# ── HEADER ─────────────────────────────────────────────────────────────────
st.markdown('<div class="titulo">ANALIZADOR DE PRECIOS</div>', unsafe_allow_html=True)
st.markdown(f'<div class="subtitulo">Inteligencia de Mercado · Quito UIO · {datetime.now():%Y-%m-%d %H:%M}</div>', unsafe_allow_html=True)
st.markdown('<div class="linea"></div>', unsafe_allow_html=True)

# ── CARGA DE DATOS ─────────────────────────────────────────────────────────
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
    st.stop()

# Procesamiento
df["precio_efectivo"] = df.apply(
    lambda r: r["precio_total"] if pd.notna(r["precio_total"]) and r["precio_total"]
    else (r["precio_estimado_ia"] if pd.notna(r.get("precio_estimado_ia")) and r["precio_estimado_ia"] else 0),
    axis=1)
df["precio_dia_efectivo"] = (df["precio_efectivo"] / df["duracion_dias"]).round(2)
df["fecha_alquiler"] = df["fecha_alquiler"].astype(str)
df["es_europcar"] = df["compania"].str.lower().str.contains("europcar", na=False)

fechas_unicas = sorted(df["fecha_alquiler"].unique())
durs_unicas = sorted(df["duracion_dias"].unique())
cats_unicas = sorted(df["categoria"].dropna().unique())
comps_unicas = sorted(df["compania"].dropna().unique())

# ── CARDS DE FECHAS (NEÓN AZUL) ────────────────────────────────────────────
st.markdown("### 📅 Fechas en análisis")
if len(fechas_unicas) > 0:
    cols = st.columns(min(len(fechas_unicas), 4))
    for i, fecha in enumerate(fechas_unicas[:4]):
        sub_f = df[(df["fecha_alquiler"] == fecha) & (df["precio_efectivo"] > 0)]
        n_regs = len(sub_f)
        n_comp = sub_f["compania"].nunique()
        precio_min = sub_f["precio_dia_efectivo"].min() if not sub_f.empty else 0
        precio_min_str = f"${precio_min:.2f}/día" if precio_min > 0 else "—"
        with cols[i]:
            st.markdown(f"""
            <div class="fecha-card">
                <div class="label">Fecha de alquiler</div>
                <div class="fecha">{fecha}</div>
                <div class="sub">{n_regs} ofertas · {n_comp} compañías</div>
                <div class="precio">Desde {precio_min_str}</div>
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

# ── TABS ───────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📅 PRECIOS POR FECHA",
    "🏆 RANKINGS",
    "⚔️ EUROPCAR VS MERCADO",
    "🔔 ALERTAS",
    "📈 EVOLUCIÓN",
    "🗄️ DATOS CRUDOS",
])

# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — PRECIOS POR FECHA
# ══════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### Precio mínimo por día")
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        f_sel = st.multiselect("Fecha", fechas_unicas, default=fechas_unicas, key="t1f")
    with col_f2:
        d_sel = st.multiselect("Duración", durs_unicas, default=durs_unicas, key="t1d")
    with col_f3:
        c_sel = st.multiselect("Categoría", cats_unicas, default=cats_unicas, key="t1c")

    fdf = df[df["fecha_alquiler"].isin(f_sel) & df["duracion_dias"].isin(d_sel)
             & df["categoria"].isin(c_sel) & (df["precio_efectivo"] > 0)]

    if fdf.empty:
        st.info("Sin datos con esos filtros.")
    else:
        st.markdown("#### 💰 Precio mínimo por día (USD)")
        pivot = fdf.pivot_table(index="fecha_alquiler", columns="duracion_dias",
                                 values="precio_dia_efectivo", aggfunc="min").round(2)
        pivot.columns = [f"{c} días" for c in pivot.columns]
        st.dataframe(pivot, use_container_width=True)

        st.markdown("#### 📊 Comparativa por duración")
        fig = px.bar(fdf, x="duracion_dias", y="precio_dia_efectivo",
                     color="compania", barmode="group", facet_col="fecha_alquiler",
                     labels={"duracion_dias": "Duración (días)", "precio_dia_efectivo": "Precio/día (USD)"},
                     color_discrete_sequence=[VERDE, AZUL, AMARILLO, "#9C27B0", "#FF9800", "#F44336", "#00BCD4", "#E91E63", "#4CAF50"])
        fig.update_layout(plot_bgcolor=PANEL, paper_bgcolor=NEGRO, font_color=TEXTO,
                           height=500, legend=dict(bgcolor=PANEL))
        st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — RANKINGS CON MEDALLAS
# ══════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### 🏆 Ranking de compañías")
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        fecha_r = st.selectbox("Fecha", fechas_unicas, key="t2f")
    with col_r2:
        cat_r = st.selectbox("Categoría", cats_unicas, key="t2c")
    with col_r3:
        dur_r = st.selectbox("Duración", durs_unicas, key="t2d")

    rdf = df[(df["fecha_alquiler"] == fecha_r) & (df["categoria"] == cat_r)
             & (df["duracion_dias"] == dur_r) & (df["precio_efectivo"] > 0)].copy()

    if rdf.empty:
        st.info("Sin datos para esta combinación.")
    else:
        rank = rdf.groupby("compania").agg(
            precio_min=("precio_dia_efectivo", "min"),
            precio_prom=("precio_dia_efectivo", "mean"),
            ofertas=("precio_dia_efectivo", "count"),
        ).round(2).sort_values("precio_min").reset_index()

        precio_euro = rank[rank["compania"].str.lower().str.contains("europcar", na=False)]["precio_min"]
        base = precio_euro.values[0] if len(precio_euro) > 0 else rank["precio_min"].iloc[0]

        def diff_pct(p):
            d = p - base
            return (d / base * 100) if base else 0

        rank["vs_euro"] = rank["precio_min"].apply(diff_pct)

        def medalla(i):
            return ["🥇", "🥈", "🥉"][i] if i < 3 else "  "

        rank.insert(0, "Medalla", [medalla(i) for i in range(len(rank))])

        st.markdown("#### 🥇 Más baratos")
        colores = [VERDE if "europcar" in c.lower() else AZUL for c in rank["compania"]]
        fig1 = go.Figure(go.Bar(
            y=rank["compania"][::-1], x=rank["precio_min"][::-1],
            orientation="h", marker_color=colores[::-1],
            text=[f"${p:.2f}" for p in rank["precio_min"][::-1]],
            textposition="outside", textfont=dict(color="white", size=12),
        ))
        fig1.update_layout(plot_bgcolor=PANEL, paper_bgcolor=NEGRO, font_color=TEXTO,
                            height=max(350, len(rank) * 40),
                            title=f"Más baratos · {fecha_r} · {cat_r} · {dur_r}d",
                            title_font_color=VERDE, xaxis_title="USD/día", showlegend=False)
        st.plotly_chart(fig1, use_container_width=True)

        st.markdown("#### 📋 Tabla completa")
        tabla = rank.copy()
        tabla["vs_euro"] = tabla["vs_euro"].apply(lambda x: f"{x:+.1f}%")

        def color_fila(row):
            if "europcar" in str(row["compania"]).lower():
                return [f"background-color: {VERDE}33; border-left: 4px solid {VERDE}; font-weight: bold;"] * len(row)
            return [""] * len(row)

        st.dataframe(
            tabla[["Medalla", "compania", "precio_min", "precio_prom", "ofertas", "vs_euro"]]
            .style.apply(color_fila, axis=1)
            .format({"precio_min": "${:.2f}", "precio_prom": "${:.2f}"}),
            use_container_width=True, hide_index=True
        )

# ══════════════════════════════════════════════════════════════════════════
# TAB 3 — EUROPCAR VS MERCADO
# ══════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### ⚔️ Europcar vs Mercado")
    if euro.empty:
        st.warning("No hay datos de Europcar.")
    else:
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.markdown("#### 💚 Europcar por categoría")
            euro_cat = euro.groupby("categoria").agg(
                precio_min=("precio_dia_efectivo", "min"),
                precio_prom=("precio_dia_efectivo", "mean"),
            ).round(2).reset_index()
            st.dataframe(euro_cat.style.format({
                "precio_min": "${:.2f}", "precio_prom": "${:.2f}"}),
                use_container_width=True, hide_index=True)

        with col_e2:
            st.markdown("#### 🌐 Mercado por categoría")
            comp_cat = comp.groupby("categoria").agg(
                precio_min=("precio_dia_efectivo", "min"),
                precio_prom=("precio_dia_efectivo", "mean"),
            ).round(2).reset_index()
            st.dataframe(comp_cat.style.format({
                "precio_min": "${:.2f}", "precio_prom": "${:.2f}"}),
                use_container_width=True, hide_index=True)

        st.markdown("#### 📊 Diferencia % por categoría")
        merge = euro.groupby("categoria")["precio_dia_efectivo"].mean().round(2).to_frame("Europcar").join(
            comp.groupby("categoria")["precio_dia_efectivo"].mean().round(2).to_frame("Mercado"),
            how="outer")
        merge["Diferencia $"] = (merge["Europcar"] - merge["Mercado"]).round(2)
        merge["% vs Mercado"] = ((merge["Diferencia $"] / merge["Mercado"]) * 100).round(1)

        def color_diff(v):
            if pd.isna(v): return ""
            if v > 0: return f"color: {ROJO}; font-weight: bold;"
            return f"color: {VERDE}; font-weight: bold;"

        st.dataframe(merge.style.map(color_diff, subset=["% vs Mercado"]).format({
            "Europcar": "${:.2f}", "Mercado": "${:.2f}",
            "Diferencia $": "${:+.2f}", "% vs Mercado": "{:+.1f}%",
        }, na_rep="—"), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 4 — ALERTAS
# ══════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### 🔔 Alertas de cambio de precio")
    n_ejecuciones = df["fecha_consulta"].nunique()
    if n_ejecuciones < 2:
        st.info(f"📋 Hay {n_ejecuciones} ejecución(es) del scraper. Corre el scraper varias veces (días distintos) para ver cambios aquí.")
        st.markdown("""
        <div class="alerta-info">
            <div class="alerta-titulo">ℹ️ Cómo funcionan las alertas</div>
            Cuando corras el scraper en días distintos, esta pestaña te mostrará:
            <ul>
                <li>🔴 <b>CRÍTICA</b>: competidor bajó el precio > 15% vs Europcar</li>
                <li>🟡 <b>MEDIA</b>: competidor bajó 5-15%</li>
                <li>🟢 <b>OPORTUNIDAD</b>: competidor subió el precio (puedes subir tú)</li>
                <li>ℹ️ <b>INFO</b>: cambio registrado sin urgencia</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.success(f"✅ {n_ejecuciones} ejecuciones detectadas. Analizando cambios...")

        # Detectar cambios entre las últimas 2 ejecuciones
        df_sorted = df.sort_values("fecha_consulta")
        ejecuciones = df_sorted["fecha_consulta"].unique()
        ult = df_sorted[df_sorted["fecha_consulta"] == ejecuciones[-1]]
        ant = df_sorted[df_sorted["fecha_consulta"] == ejecuciones[-2]]

        key_cols = ["fecha_alquiler", "duracion_dias", "compania", "categoria"]
        ult_g = ult.groupby(key_cols)["precio_dia_efectivo"].mean().round(2).reset_index()
        ant_g = ant.groupby(key_cols)["precio_dia_efectivo"].mean().round(2).reset_index()

        merged = ult_g.merge(ant_g, on=key_cols, suffixes=("_nuevo", "_ant"))
        merged["dif"] = (merged["precio_dia_efectivo_nuevo"] - merged["precio_dia_efectivo_ant"]).round(2)
        merged["dif_pct"] = ((merged["dif"] / merged["precio_dia_efectivo_ant"]) * 100).round(1)
        cambios = merged[merged["dif"].abs() > 0.01].sort_values("dif_pct")

        if cambios.empty:
            st.info("No se detectaron cambios de precio entre las últimas 2 ejecuciones.")
        else:
            st.markdown(f"#### 🚨 {len(cambios)} cambios detectados")
            for _, r in cambios.iterrows():
                direccion = "bajó" if r["dif"] < 0 else "subió"
                es_euro = "europcar" in str(r["compania"]).lower()
                clase = "alerta-critica" if (r["dif"] < 0 and not es_euro) else (
                    "alerta-oport" if r["dif"] > 0 and not es_euro else "alerta-info")
                st.markdown(f"""
                <div class="{clase}">
                    <div class="alerta-titulo">{r['compania']} · {r['categoria']} · {r['duracion_dias']}d · {r['fecha_alquiler']}</div>
                    Precio {direccion}: <b>${r['precio_dia_efectivo_ant']:.2f}</b> → <b>${r['precio_dia_efectivo_nuevo']:.2f}</b>
                    (<b>{r['dif_pct']:+.1f}%</b> · {r['dif']:+.2f} USD)
                </div>
                """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 5 — EVOLUCIÓN
# ══════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### 📈 Evolución histórica")
    n_ejec = df["fecha_consulta"].nunique()
    if n_ejec < 2:
        st.info(f"Solo hay {n_ejec} ejecución. Corre el scraper varios días para ver la evolución.")
    else:
        col_ev1, col_ev2, col_ev3 = st.columns(3)
        with col_ev1:
            comp_ev = st.selectbox("Compañía", comps_unicas, key="t5c")
        with col_ev2:
            cat_ev = st.selectbox("Categoría ", cats_unicas, key="t5cat")
        with col_ev3:
            dur_ev = st.selectbox("Duración ", durs_unicas, key="t5d")

        evol = df[(df["compania"] == comp_ev) & (df["categoria"] == cat_ev)
                  & (df["duracion_dias"] == dur_ev)].sort_values("fecha_consulta")

        if not evol.empty:
            fig = px.line(evol, x="fecha_consulta", y="precio_dia_efectivo", markers=True,
                           title=f"Evolución · {comp_ev} · {cat_ev} · {dur_ev}d")
            color_linea = VERDE if "europcar" in comp_ev.lower() else AZUL
            fig.update_traces(line_color=color_linea, marker_color=color_linea, line_width=3, marker_size=10)
            fig.update_layout(plot_bgcolor=PANEL, paper_bgcolor=NEGRO, font_color=TEXTO, height=450)
            st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 6 — DATOS CRUDOS
# ══════════════════════════════════════════════════════════════════════════
with tab6:
    st.markdown("### 🗄️ Datos completos")
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        comp_f = st.multiselect("Compañía", comps_unicas, key="t6c")
    with col_c2:
        trans_f = st.multiselect("Transmisión", sorted(df["transmision"].dropna().unique()), key="t6t")
    with col_c3:
        solo_euro = st.checkbox("Solo Europcar")

    view = df.copy()
    if comp_f: view = view[view["compania"].isin(comp_f)]
    if trans_f: view = view[view["transmision"].isin(trans_f)]
    if solo_euro: view = view[view["es_europcar"]]

    cols = ["fecha_consulta", "fecha_alquiler", "duracion_dias", "compania", "categoria",
            "transmision", "precio_total", "precio_dia", "precio_total_crudo",
            "rating", "reviews", "cancelacion_gratis", "url"]
    cols = [c for c in cols if c in view.columns]
    st.dataframe(view[cols], use_container_width=True, height=600)

    csv = view.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV", csv,
                        f"analisis_{datetime.now():%Y%m%d_%H%M}.csv", "text/csv")

# FOOTER
st.markdown('<div class="linea"></div>', unsafe_allow_html=True)
st.markdown(f'<div style="text-align:center;color:#666;font-size:0.7rem;letter-spacing:2px;">'
            f'ANALIZADOR DE PRECIOS · UIO · {len(df)} REGISTROS · {df["compania"].nunique()} COMPAÑÍAS</div>',
            unsafe_allow_html=True)
