# ia_analisis.py
"""Análisis con IA local (Ollama)."""

import json
import hashlib
import os
import sqlite3
from datetime import datetime
from typing import Optional

OLLAMA_URL = "http://localhost:11434"
MODELO_ANALISIS = "qwen2.5:latest"
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ia_cache.db")


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:32]


def ollama_disponible() -> bool:
    try:
        import urllib.request
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _init_cache():
    conn = sqlite3.connect(CACHE_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache_ia (
            hash_prompt TEXT PRIMARY KEY,
            respuesta TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    return conn


def consultar_ia(prompt: str, sistema: str = "", timeout: int = 180) -> Optional[str]:
    if not ollama_disponible():
        return None

    h = _hash_prompt(prompt + sistema)
    try:
        conn = _init_cache()
        cur = conn.execute("SELECT respuesta FROM cache_ia WHERE hash_prompt = ?", (h,))
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass

    try:
        import urllib.request
        payload = {
            "model": MODELO_ANALISIS,
            "prompt": prompt,
            "system": sistema,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 500},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resultado = json.loads(resp.read().decode("utf-8"))
            respuesta = resultado.get("response", "").strip()

        try:
            conn = _init_cache()
            conn.execute(
                "INSERT OR REPLACE INTO cache_ia (hash_prompt, respuesta, timestamp) VALUES (?, ?, ?)",
                (h, respuesta, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

        return respuesta
    except Exception as e:
        print(f"[IA DEBUG] {type(e).__name__}: {e}")
        return None


def analizar_competencia(df_resumen, compania_foco="Europcar"):
    if not df_resumen:
        return "No hay datos para analizar."

    lineas = []
    for r in df_resumen:
        diff = r["p_yo"] - r["p_rival"]
        if diff > 0:
            estado = f"PERDIENDO (${diff:.2f} mas caro)"
        elif diff < 0:
            estado = f"GANANDO (${abs(diff):.2f} mas barato)"
        else:
            estado = "EMPATE"
        lineas.append(
            f"- {r['dias']}d {r['categoria']} {r['transmision']}: "
            f"Tu=${r['p_yo']:.2f} | Rival={r['rival']}(${r['p_rival']:.2f}) | "
            f"Pos=#{r['pos']} | {estado}"
        )
    contexto = "\n".join(lineas)

    sistema = (
        "Eres analista de pricing de alquiler de autos en Ecuador. "
        "Respondes en espanol, directo. Si ganas -> MANTENER. Si pierdes -> BAJAR."
    )

    prompt = (
        "Datos de " + compania_foco + " vs competencia:\n\n" + contexto +
        "\n\nGenera analisis en este formato:\n\n"
        "## ACCIONES URGENTES (perdiendo)\n"
        "Para cada una: [Xd categoria transmision] BAJAR de $XX a $YY (bajar $ZZ). Superar a [rival].\n\n"
        "## MANTENER (ganando)\n"
        "Lista de combinaciones donde ya eres el mas barato.\n\n"
        "## ANALISIS\n"
        "2-3 lineas de observacion estrategica.\n\n"
        "Maximo 400 palabras. Se especifico con numeros."
    )

    respuesta = consultar_ia(prompt, sistema, timeout=180)
    if respuesta:
        return respuesta
    return "IA no disponible."


def analizar_cambio(df_cambios):
    if not df_cambios:
        return "No hay cambios para analizar."

    lineas = []
    for c in df_cambios[:15]:
        signo = "BAJO" if c["variacion"] < 0 else "SUBE"
        lineas.append(
            f"- {c['compania']} {c['dias']}d {c['categoria']}: "
            f"${c['precio_ant']:.2f} -> ${c['precio_total']:.2f} ({signo} {c['pct']:+.1f}%)"
        )
    contexto = "\n".join(lineas)

    sistema = "Analista de pricing. Responde en espanol, conciso."
    prompt = (
        "Cambios detectados:\n\n" + contexto +
        "\n\nDime:\n1. Patron detectado\n2. Compania mas agresiva\n3. Recomendacion para Europcar\n\nMax 5 bullets."
    )

    respuesta = consultar_ia(prompt, sistema, timeout=180)
    if respuesta:
        return respuesta
    return "IA no disponible."


if __name__ == "__main__":
    print("Test IA...")
    print("Ollama disponible:", ollama_disponible())
    print()
    test = [
        {"dias": 3, "categoria": "Economico", "transmision": "Automatica",
         "p_yo": 24.33, "p_rival": 22.50, "rival": "Alamo", "pos": 2},
        {"dias": 7, "categoria": "SUV", "transmision": "Automatica",
         "p_yo": 45.00, "p_rival": 52.00, "rival": "Sixt", "pos": 1},
        {"dias": 15, "categoria": "Economico", "transmision": "Manual",
         "p_yo": 31.27, "p_rival": 25.73, "rival": "Sixt", "pos": 4},
    ]
    print("Analisis de prueba:")
    print(analizar_competencia(test))
