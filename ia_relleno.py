#!/usr/bin/env python3
"""
ia_relleno.py — Rellena precios faltantes usando Ollama (Qwen 2.5).
"""
from __future__ import annotations

import os
import re
import sqlite3
from typing import Optional

import ollama

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
MODELO = "qwen2.5:latest"

VERDE = "\033[92m"
AMARILLO = "\033[93m"
ROJO = "\033[91m"
CIAN = "\033[96m"
RESET = "\033[0m"


def log(msg: str, color: str = RESET) -> None:
    print(f"{color}{msg}{RESET}", flush=True)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_tabla() -> None:
    with _connect() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(historial_precios)")]
        if "precio_estimado_ia" not in cols:
            conn.execute("ALTER TABLE historial_precios ADD COLUMN precio_estimado_ia REAL")
        if "fuente_precio" not in cols:
            conn.execute("ALTER TABLE historial_precios ADD COLUMN fuente_precio TEXT DEFAULT 'expedia'")
        conn.commit()


def obtener_faltantes() -> list:
    with _connect() as conn:
        cur = conn.execute("""
            SELECT id, fecha_alquiler, duracion_dias, compania, categoria, transmision
            FROM historial_precios
            WHERE (precio_total IS NULL OR precio_total = 0 OR precio_faltante = 1)
              AND (precio_estimado_ia IS NULL OR precio_estimado_ia = 0)
            ORDER BY fecha_alquiler, duracion_dias, compania
        """)
        return cur.fetchall()


def obtener_contexto(compania: str, categoria: str, duracion: int) -> str:
    with _connect() as conn:
        cur = conn.execute("""
            SELECT fecha_alquiler, precio_total
            FROM historial_precios
            WHERE compania = ? AND categoria = ? AND duracion_dias = ?
              AND precio_total IS NOT NULL AND precio_total > 0
            ORDER BY fecha_alquiler DESC LIMIT 10
        """, (compania, categoria, duracion))
        rows = cur.fetchall()

    if rows:
        return "Precios historicos de la misma compania:\n" + \
               "\n".join([f"- {r[0]}: ${r[1]:.2f}" for r in rows])

    with _connect() as conn:
        cur = conn.execute("""
            SELECT compania, precio_total
            FROM historial_precios
            WHERE categoria = ? AND duracion_dias = ?
              AND precio_total IS NOT NULL AND precio_total > 0
            ORDER BY precio_total ASC LIMIT 10
        """, (categoria, duracion))
        rows = cur.fetchall()

    if rows:
        return "Precios de la competencia (misma categoria y duracion):\n" + \
               "\n".join([f"- {r[0]}: ${r[1]:.2f}" for r in rows])

    return "Sin contexto. Estima segun el mercado ecuatoriano."


def estimar_precio(compania: str, categoria: str, duracion: int, contexto: str) -> Optional[float]:
    prompt = f"""Eres un analista experto en alquiler de autos en Quito, Ecuador.
Estima el precio total (USD) que cobraria "{compania}" por un auto
de categoria "{categoria}" durante {duracion} dias.

{contexto}

Responde SOLO con el numero (sin $, sin texto). Por ejemplo: 245.50
Si no puedes, responde: 0"""

    try:
        resp = ollama.chat(
            model=MODELO,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2, "num_predict": 20},
        )
        texto = resp["message"]["content"].strip()
        m = re.search(r"(\d+(?:[.,]\d+)?)", texto)
        if not m:
            return None
        val = float(m.group(1).replace(",", "."))
        return val if 5 <= val <= 100_000 else None
    except Exception as e:
        log(f"  Error IA: {e}", AMARILLO)
        return None


def actualizar(id_: int, precio_est: float, duracion: int) -> None:
    with _connect() as conn:
        conn.execute("""
            UPDATE historial_precios
            SET precio_estimado_ia = ?,
                precio_dia = ?,
                fuente_precio = 'ia'
            WHERE id = ?
        """, (precio_est, round(precio_est / max(duracion, 1), 2), id_))
        conn.commit()


def main() -> None:
    log("=" * 60, CIAN)
    log("  RELLENO DE PRECIOS CON IA (Ollama + Qwen 2.5)", CIAN)
    log("=" * 60, CIAN)

    if not os.path.exists(DB_PATH):
        log(f"No existe DB en {DB_PATH}", ROJO)
        return

    init_tabla()
    faltantes = obtener_faltantes()

    if not faltantes:
        log("No hay precios faltantes por rellenar.", VERDE)
        return

    log(f"{len(faltantes)} registros sin precio. Empezando...\n", AMARILLO)

    rellenados = 0
    for i, (id_, fecha, dur, comp, cat, trans) in enumerate(faltantes, 1):
        log(f"[{i}/{len(faltantes)}] {fecha} | {dur}d | {comp} | {cat}", CIAN)
        contexto = obtener_contexto(comp, cat, dur)
        precio_est = estimar_precio(comp, cat, dur, contexto)

        if precio_est:
            actualizar(id_, precio_est, dur)
            log(f"  Estimado: ${precio_est:.2f} (${precio_est/dur:.2f}/dia)", VERDE)
            rellenados += 1
        else:
            log(f"  No se pudo estimar", ROJO)

    log("=" * 60, CIAN)
    log(f"TOTAL RELLENADOS: {rellenados}/{len(faltantes)}", VERDE)
    log("=" * 60, CIAN)


if __name__ == "__main__":
    main()
