#!/usr/bin/env python3
"""
fix_parser_ia.py — Limpia la DB usando IA local (Qwen 2.5).
- Detecta "compañías" basura (texto suelto de la página).
- Las mapea a compañías reales o las marca para borrar.
- Actualiza historial_precios.
"""
from __future__ import annotations

import os
import re
import sqlite3

import ollama

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
MODELO = "qwen2.5:latest"

VERDE = "\033[92m"
AMARILLO = "\033[93m"
ROJO = "\033[91m"
CIAN = "\033[96m"
RESET = "\033[0m"

COMPANIAS_REALES = {
    "avis", "hertz", "europcar", "budget", "localiza", "sixt", "alamo",
    "enterprise", "thrifty", "dollar", "ecovia", "goldcar", "national",
    "kayak", "flexways", "mexrentacar", "united rent", "economy",
    "payless", "fox", "green motion",
}

BASURA_CONOCIDA = {
    "airport pick-up", "cancellation policy", "capacity", "compact",
    "compact suv", "economy", "exclusive offers", "fullsize pickup extended cab",
    "fullsize suv", "fullsize van", "great deal", "luxury suv", "midsize",
    "midsize crossover", "midsize elite crossover", "midsize suv", "mini",
    "mini van", "payment option", "popular filters", "proveedor uio",
    "save time during pick-up", "see more", "special suv", "specifications",
    "standard elite crossover", "total price", "traveler ratings",
    "includes taxes & fees", "fullsize", "premium", "standard", "intermediate",
}


def log(msg: str, color: str = RESET) -> None:
    print(f"{color}{msg}{RESET}", flush=True)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def es_compania_real(nombre: str) -> bool:
    n = nombre.lower().strip()
    return n in COMPANIAS_REALES


def es_basura_conocida(nombre: str) -> bool:
    n = nombre.lower().strip()
    return n in BASURA_CONOCIDA


def normalizar_compania(compania: str) -> str | None:
    """Devuelve el nombre normalizado o None si hay que borrar el registro."""
    if not compania:
        return None
    c = compania.strip()
    c_low = c.lower()

    # Si es compañía real, devolver nombre canónico
    for key in COMPANIAS_REALES:
        if key in c_low:
            return key.title().replace(" ", "")

    # Si es basura conocida → borrar
    if es_basura_conocida(c):
        return None

    # Si tiene números o es muy largo → probablemente basura
    if re.search(r"\d", c) or len(c) > 30:
        return None

    # Si parece un título (Title Case con palabras genéricas) → basura
    palabras_basura = {"suv", "van", "pickup", "compact", "economy",
                       "midsize", "fullsize", "mini", "premium", "standard",
                       "crossover", "elite", "special", "luxury", "popular",
                       "filters", "price", "policy", "capacity", "ratings",
                       "offers", "deal", "option"}
    if any(p in c_low for p in palabras_basura):
        return None

    return None  # Por defecto, si no reconocemos, borramos


def limpiar_con_ia(companias_unicas: list[str]) -> dict[str, str | None]:
    """Pide a la IA que clasifique las compañías dudosas."""
    prompt = f"""Tengo una lista de textos extraídos de una página de alquiler de autos.
Necesito saber cuáles son NOMBRES DE COMPAÑÍAS REALES de alquiler de autos
y cuáles son solo texto suelto de la página (categorías, filtros, títulos).

Lista:
{chr(10).join(f"- {c}" for c in companias_unicas)}

Responde SOLO con líneas en este formato exacto (una por compañía):
NOMBRE|REAL
o
NOMBRE|BASURA

Ejemplos:
Avis|REAL
Compact SUV|BASURA
Hertz|REAL
includes taxes & fees|BASURA

Responde en el mismo orden, sin texto adicional."""

    try:
        resp = ollama.chat(
            model=MODELO,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 800},
        )
        texto = resp["message"]["content"].strip()
        resultado = {}
        for linea in texto.split("\n"):
            linea = linea.strip()
            if "|" not in linea:
                continue
            partes = linea.split("|", 1)
            if len(partes) == 2:
                nombre, clasif = partes
                nombre = nombre.strip().lstrip("-* ").strip()
                clasif = clasif.strip().upper()
                resultado[nombre] = nombre if "REAL" in clasif else None
        return resultado
    except Exception as e:
        log(f"Error IA: {e}", ROJO)
        return {}


def main() -> None:
    log("=" * 60, CIAN)
    log("  LIMPIEZA DE DB CON IA (Qwen 2.5)", CIAN)
    log("=" * 60, CIAN)

    with _connect() as conn:
        cur = conn.execute("SELECT DISTINCT compania FROM historial_precios ORDER BY compania")
        companias = [r[0] for r in cur.fetchall() if r[0]]

    log(f"Compañías distintas en DB: {len(companias)}", CIAN)
    log("", RESET)
    for c in companias:
        log(f"  - {c}", RESET)

    log("", RESET)
    log("Clasificando con IA...", AMARILLO)

    dudosas = [c for c in companias if not es_compania_real(c) and not es_basura_conocida(c)]
    log(f"Compañías dudosas a consultar a la IA: {len(dudosas)}", AMARILLO)

    mapa_ia = limpiar_con_ia(dudosas) if dudosas else {}

    cambios = {"actualizadas": 0, "borradas": 0, "ok": 0}
    for c in companias:
        if es_compania_real(c):
            cambios["ok"] += 1
            continue

        if es_basura_conocida(c):
            with _connect() as conn:
                conn.execute("DELETE FROM historial_precios WHERE compania = ?", (c,))
                conn.commit()
            cambios["borradas"] += 1
            log(f"  BORRADA: {c}", ROJO)
            continue

        # Consultar resultado de la IA
        nueva = mapa_ia.get(c)
        if nueva is None:
            with _connect() as conn:
                conn.execute("DELETE FROM historial_precios WHERE compania = ?", (c,))
                conn.commit()
            cambios["borradas"] += 1
            log(f"  BORRADA (IA): {c}", ROJO)
        else:
            with _connect() as conn:
                conn.execute("UPDATE historial_precios SET compania = ? WHERE compania = ?", (nueva, c))
                conn.commit()
            cambios["actualizadas"] += 1
            log(f"  ACTUALIZADA: {c} -> {nueva}", VERDE)

    log("", RESET)
    log("=" * 60, CIAN)
    log(f"OK (ya eran reales): {cambios['ok']}", VERDE)
    log(f"BORRADAS (basura): {cambios['borradas']}", ROJO)
    log(f"ACTUALIZADAS (mapeadas): {cambios['actualizadas']}", AMARILLO)
    log("=" * 60, CIAN)

    # Resumen final
    with _connect() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM historial_precios")
        total = cur.fetchone()[0]
        cur = conn.execute("SELECT DISTINCT compania FROM historial_precios ORDER BY compania")
        finales = [r[0] for r in cur.fetchall()]

    log(f"REGISTROS RESTANTES: {total}", CIAN)
    log("COMPAÑÍAS FINALES:", CIAN)
    for c in finales:
        log(f"  - {c}", VERDE)


if __name__ == "__main__":
    main()
