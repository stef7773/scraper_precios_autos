# generar_reporte.py
"""
Reporte Excel enfocado en MI EMPRESA (Europcar) vs competencia.
6 hojas:
  1. Resumen Ejecutivo
  2. Yo vs Competencia
  3. Alertas de Bajadas
  4. Ranking por Categoría
  5. Histórico de Cambios
  6. Datos Completos
"""

import sqlite3
import pandas as pd
import os
from datetime import datetime

# 👇 TU EMPRESA
MI_EMPRESA = "Europcar"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'precios_competencia.db')
OUTPUT_EXCEL = os.path.join(
    BASE_DIR,
    f'Reporte_Competencia_UIO_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
)


def _cargar_df() -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM historial_precios ORDER BY fecha_consulta DESC", conn
    )
    conn.close()
    if not df.empty:
        df['fecha_consulta'] = pd.to_datetime(df['fecha_consulta'])
    return df


def _hoja_resumen(df: pd.DataFrame) -> pd.DataFrame:
    """KPIs globales del mercado."""
    total = len(df)
    min_p = df['precio_dia'].min()
    max_p = df['precio_dia'].max()
    avg_p = df['precio_dia'].mean()
    n_comp = df['compania'].nunique()
    n_plat = df['plataforma'].nunique()
    n_horiz = df['horizonte'].nunique()

    return pd.DataFrame({
        'Métrica': [
            'Total de registros',
            'Compañías únicas detectadas',
            'Plataformas monitoreadas',
            'Horizontes consultados',
            'Precio/día más bajo',
            'Precio/día más alto',
            'Precio/día promedio',
            'Fecha del reporte',
        ],
        'Valor': [
            total, n_comp, n_plat, n_horiz,
            f"${min_p:.2f}", f"${max_p:.2f}", f"${avg_p:.2f}",
            datetime.now().strftime('%Y-%m-%d %H:%M'),
        ],
    })


def _hoja_yo_vs_competencia(df: pd.DataFrame) -> pd.DataFrame:
    """
    Para cada combinación (horizonte, categoría, transmisión):
    precio de MI EMPRESA vs promedio y mínimo de competidores.
    """
    filas = []
    for (hz, cat, trans), grupo in df.groupby(['horizonte', 'categoria', 'transmision']):
        yo = grupo[grupo['compania'].str.lower() == MI_EMPRESA.lower()]
        comp = grupo[grupo['compania'].str.lower() != MI_EMPRESA.lower()]

        precio_yo = yo['precio_dia'].min() if not yo.empty else None
        precio_comp_min = comp['precio_dia'].min() if not comp.empty else None
        precio_comp_avg = comp['precio_dia'].mean() if not comp.empty else None

        if precio_yo is None and precio_comp_min is None:
            continue

        if precio_yo is not None and precio_comp_min is not None:
            diff = precio_yo - precio_comp_min
            if diff > 0:
                estado = f"⚠ Estás ${diff:.2f} MÁS CARO que {comp.loc[comp['precio_dia'].idxmin(), 'compania']}"
            elif diff < 0:
                estado = f"✅ Estás ${abs(diff):.2f} MÁS BARATO"
            else:
                estado = "🟰 Empate"
        elif precio_yo is None:
            estado = "❌ Sin datos de tu empresa"
        else:
            estado = "✅ Sin competidores en esta combinación"

        filas.append({
            'Horizonte': hz,
            'Categoría': cat,
            'Transmisión': trans,
            f'{MI_EMPRESA} ($/día)': round(precio_yo, 2) if precio_yo else None,
            'Competidor más barato': (
                comp.loc[comp['precio_dia'].idxmin(), 'compania'] if not comp.empty else None
            ),
            'Mín. competencia ($/día)': round(precio_comp_min, 2) if precio_comp_min else None,
            'Prom. competencia ($/día)': round(precio_comp_avg, 2) if precio_comp_avg else None,
            'Diferencia vs mínimo ($)': round(precio_yo - precio_comp_min, 2)
                if (precio_yo and precio_comp_min) else None,
            'Estado': estado,
        })

    return pd.DataFrame(filas)


def _hoja_alertas_bajadas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detecta cuándo cada compañía BAJÓ su precio respecto a la consulta anterior
    para la misma combinación horizonte+categoría+transmisión.
    """
    if df.empty:
        return pd.DataFrame()

    df_sorted = df.sort_values(
        ['compania', 'horizonte', 'categoria', 'transmision', 'fecha_consulta']
    )
    df_sorted['precio_anterior'] = (
        df_sorted.groupby(['compania', 'horizonte', 'categoria', 'transmision'])['precio_dia']
        .shift(1)
    )
    df_sorted['variacion'] = df_sorted['precio_dia'] - df_sorted['precio_anterior']
    df_sorted['pct_variacion'] = (
        (df_sorted['variacion'] / df_sorted['precio_anterior']) * 100
    )

    bajadas = df_sorted[
        df_sorted['variacion'].notnull() & (df_sorted['variacion'] < 0)
    ].copy()

    if bajadas.empty:
        return pd.DataFrame()

    bajadas['Prioridad'] = bajadas.apply(
        lambda r: '🔴 ALTA' if abs(r['pct_variacion']) >= 15
        else ('🟡 MEDIA' if abs(r['pct_variacion']) >= 7 else '🟢 BAJA'),
        axis=1,
    )

    resultado = bajadas[[
        'fecha_consulta', 'compania', 'horizonte', 'categoria', 'transmision',
        'precio_anterior', 'precio_dia', 'variacion', 'pct_variacion',
        'Prioridad', 'plataforma',
    ]].copy()
    resultado.columns = [
        'Fecha Detección', 'Compañía', 'Horizonte', 'Categoría', 'Transmisión',
        'Precio Anterior ($)', 'Precio Nuevo ($)', 'Bajada ($)', 'Bajada (%)',
        'Prioridad', 'Plataforma',
    ]
    resultado = resultado.sort_values('Bajada (%)')
    return resultado


def _hoja_ranking(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ranking de compañías por precio promedio en cada combinación
    (horizonte, categoría, transmisión).
    """
    ranking = (
        df.groupby(['horizonte', 'categoria', 'transmision', 'compania'])
        .agg(
            precio_min=('precio_dia', 'min'),
            precio_prom=('precio_dia', 'mean'),
            apariciones=('precio_dia', 'count'),
        )
        .reset_index()
    )
    ranking['ranking'] = (
        ranking.groupby(['horizonte', 'categoria', 'transmision'])['precio_prom']
        .rank(method='min')
        .astype(int)
    )
    ranking = ranking.sort_values(
        ['horizonte', 'categoria', 'transmision', 'ranking']
    )
    ranking.columns = [
        'Horizonte', 'Categoría', 'Transmisión', 'Compañía',
        'Precio Mín ($/día)', 'Precio Prom ($/día)', 'Apariciones', 'Ranking',
    ]
    ranking['Precio Mín ($/día)'] = ranking['Precio Mín ($/día)'].round(2)
    ranking['Precio Prom ($/día)'] = ranking['Precio Prom ($/día)'].round(2)
    return ranking


def _hoja_cambios(df: pd.DataFrame) -> pd.DataFrame:
    """Histórico completo de cambios (subidas y bajadas)."""
    if df.empty:
        return pd.DataFrame()

    df_sorted = df.sort_values(
        ['compania', 'horizonte', 'categoria', 'transmision', 'fecha_consulta']
    )
    df_sorted['precio_anterior'] = (
        df_sorted.groupby(['compania', 'horizonte', 'categoria', 'transmision'])['precio_dia']
        .shift(1)
    )
    df_sorted['variacion'] = df_sorted['precio_dia'] - df_sorted['precio_anterior']

    cambios = df_sorted[
        df_sorted['variacion'].notnull() & (df_sorted['variacion'] != 0)
    ].copy()

    if cambios.empty:
        return pd.DataFrame()

    cambios['Tendencia'] = cambios['variacion'].apply(
        lambda x: '🔻 BAJÓ' if x < 0 else '🔺 SUBIÓ'
    )

    resultado = cambios[[
        'fecha_consulta', 'compania', 'horizonte', 'categoria', 'transmision',
        'precio_anterior', 'precio_dia', 'variacion', 'Tendencia', 'plataforma',
    ]].copy()
    resultado.columns = [
        'Fecha', 'Compañía', 'Horizonte', 'Categoría', 'Transmisión',
        'Precio Anterior ($)', 'Precio Nuevo ($)', 'Diferencia ($)',
        'Tendencia', 'Plataforma',
    ]
    resultado = resultado.sort_values('Fecha', ascending=False)
    return resultado


def generar_excel():
    df = _cargar_df()
    if df.empty:
        print("⚠️ La base de datos está vacía. Corre primero el scraper.")
        return

    print(f"📊 Registros cargados: {len(df)}")
    print(f"🏢 Analizando vs: {MI_EMPRESA}")

    resumen = _hoja_resumen(df)
    yo_vs_comp = _hoja_yo_vs_competencia(df)
    alertas = _hoja_alertas_bajadas(df)
    ranking = _hoja_ranking(df)
    cambios = _hoja_cambios(df)

    with pd.ExcelWriter(OUTPUT_EXCEL, engine='openpyxl') as writer:
        resumen.to_excel(writer, sheet_name='Resumen Ejecutivo', index=False)

        if not yo_vs_comp.empty:
            yo_vs_comp.to_excel(writer, sheet_name='Yo vs Competencia', index=False)

        if not alertas.empty:
            alertas.to_excel(writer, sheet_name='Alertas de Bajadas', index=False)
        else:
            pd.DataFrame({
                'Mensaje': ['No se han detectado bajadas de precio todavía.']
            }).to_excel(writer, sheet_name='Alertas de Bajadas', index=False)

        if not ranking.empty:
            ranking.to_excel(writer, sheet_name='Ranking por Categoría', index=False)

        if not cambios.empty:
            cambios.to_excel(writer, sheet_name='Histórico de Cambios', index=False)

        df.to_excel(writer, sheet_name='Datos Completos', index=False)

    print(f"\n✅ Reporte generado: {OUTPUT_EXCEL}")
    print(f"   • Resumen Ejecutivo: {len(resumen)} filas")
    print(f"   • Yo vs Competencia: {len(yo_vs_comp)} filas")
    print(f"   • Alertas de Bajadas: {len(alertas)} filas")
    print(f"   • Ranking por Categoría: {len(ranking)} filas")
    print(f"   • Histórico de Cambios: {len(cambios)} filas")


if __name__ == '__main__':
    generar_excel()
