cd ~/Proyectos/scraper_precios_autos

cat > ia_parser.py << 'IA_PARSER'
# ia_parser.py
"""
Parser con IA local (Ollama) para extraer info precisa de tarjetas de Expedia.
Usa llama3.2:1b por velocidad (2-3 seg por batch).
"""

import json
import re
import hashlib
import urllib.request
import urllib.error
import sqlite3
from datetime import datetime
from typing import Optional

OLLAMA_URL = "http://localhost:11434"
MODELO = "llama3.2:1b"
CACHE_PATH = "ia_cache.db"

# ══════════════════════════════════════════════════════════════════════════════
# REGLAS DE NEGOCIO ECUADOR (rentadoras)
# ══════════════════════════════════════════════════════════════════════════════

RANGOS_PRECIO = {
    'Mini':               (15, 45),
    'Económico':          (18, 55),
    'Compacto':           (22, 65),
    'Mediano':            (28, 75),
    'Estándar':           (30, 85),
    'Grande':             (35, 100),
    'Lujo':               (60, 250),
    'SUV':                (45, 150),
    'SUV Lujo':           (80, 300),
    'Camioneta SUV':      (70, 250),
    'Camioneta Pickup':   (75, 200),   # Pickup real: $75-200/día
    'Van':                (60, 200),
    'Minivan':            (70, 220),
    'Deportivo':          (80, 300),
    'Otro':               (20, 500),
}

COMPANIAS_VALIDAS = {
    'europcar', 'alamo', 'localiza', 'keddy', 'goldcar', 'sixt',
    'avis', 'budget', 'hertz', 'national', 'enterprise', 'thrifty',
    'dollar', 'fox', 'green motion', 'payless',
}


def get_cache():
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


def consultar_ia(prompt: str, timeout: int = 90) -> Optional[str]:
    """Llama a Ollama con cache."""
    h = hashlib.sha256(prompt.encode()).hexdigest()[:32]
    try:
        conn = get_cache()
        row = conn.execute(
            "SELECT respuesta FROM cache_ia WHERE hash_prompt = ?", (h,)
        ).fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass

    try:
        payload = {
            "model": MODELO,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 500},
        }
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            respuesta = data.get("response", "").strip()

        try:
            conn = get_cache()
            conn.execute(
                "INSERT OR REPLACE INTO cache_ia VALUES (?, ?, ?)",
                (h, respuesta, datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
        return respuesta
    except Exception as e:
        print(f"[IA ERROR] {type(e).__name__}: {e}")
        return None


def parsear_bloques_con_ia(textos: list) -> list:
    """
    Recibe lista de bloques de texto y devuelve lista de dicts parseados.
    Procesa en batches de 8 para velocidad.
    """
    resultados = []
    BATCH = 8

    for i in range(0, len(textos), BATCH):
        lote = textos[i:i+BATCH]
        resultados.extend(_parsear_lote(lote))

    return resultados


def _parsear_lote(bloques: list) -> list:
    """Parsea un lote de hasta 8 bloques en 1 llamada a IA."""

    # Preparar prompt
    bloques_txt = ""
    for idx, txt in enumerate(bloques, 1):
        # Limpiar y truncar
        txt_limpio = re.sub(r"\s+", " ", txt)[:400]
        bloques_txt += f"\n--- BLOQUE {idx} ---\n{txt_limpio}\n"

    prompt = f"""Eres un experto en rentadoras de autos en Ecuador.
Analiza estos {len(bloques)} bloques de Expedia. Devuelve SOLO un JSON array válido, sin explicaciones.

REGLAS ESTRICTAS:
1. compania: SOLO si es Europcar, Alamo, Sixt, Budget, Avis, Localiza, Keddy, Goldcar, Hertz, National, Enterprise, Thrifty, Dollar, Fox. Si no detectas, pon null.
2. categoria: Una de estas exactas: Mini, Económico, Compacto, Mediano, Estándar, Grande, Lujo, SUV, SUV Lujo, Camioneta SUV, Camioneta Pickup, Van, Minivan, Deportivo. Si no puedes saber, pon null.
3. transmision: "Manual" o "Automática". REGLA: Pickup SIEMPRE es Manual (no existen automáticas en rentadoras de Ecuador).
4. modelo: Marca + modelo del auto (ej: "Kia Rio", "Toyota Corolla"). Si no sabes, pon null.
5. precio_total: El precio TOTAL del alquiler en USD (el más bajo que aparezca, ej: si dice "$33 $30 total" → 30). Si no hay, null.
6. precio_base: El precio tachado/antes del descuento (ej: 33 en "$33 $30 total"). Si no hay, null.

Devuelve un JSON array con {len(bloques)} objetos:
[
  {{"compania": "...", "categoria": "...", "transmision": "...", "modelo": "...", "precio_total": 0, "precio_base": 0}},
  ...
]

BLOQUES:
{bloques_txt}

JSON array:
"""

    respuesta = consultar_ia(prompt, timeout=90)
    if not respuesta:
        return [None] * len(bloques)

    # Extraer JSON de la respuesta
    json_match = re.search(r'\[.*\]', respuesta, re.DOTALL)
    if not json_match:
        return [None] * len(bloques)

    try:
        items = json.loads(json_match.group(0))
        # Asegurar tamaño correcto
        if len(items) < len(bloques):
            items += [None] * (len(bloques) - len(items))
        return items[:len(bloques)]
    except json.JSONDecodeError as e:
        print(f"[JSON ERROR] {e}")
        return [None] * len(bloques)


# ══════════════════════════════════════════════════════════════════════════════
# VALIDACIONES DE NEGOCIO
# ══════════════════════════════════════════════════════════════════════════════

def validar_y_corregir(item: dict, dias: int) -> Optional[dict]:
    """Aplica reglas de negocio a un item parseado por IA."""
    if not item:
        return None

    compania = item.get("compania")
    categoria = item.get("categoria")
    transmision = item.get("transmision")
    modelo = item.get("modelo") or ""
    precio_total = item.get("precio_total")
    precio_base = item.get("precio_base")

    # Validar compañía
    if not compania or compania.lower() not in COMPANIAS_VALIDAS:
        return None

    # Capitalizar compañía correctamente
    for key, nombre in {
        'europcar': 'Europcar', 'alamo': 'Alamo', 'sixt': 'Sixt',
        'budget': 'Budget', 'avis': 'Avis', 'localiza': 'Localiza',
        'keddy': 'Keddy', 'goldcar': 'Goldcar', 'hertz': 'Hertz',
        'national': 'National', 'enterprise': 'Enterprise',
        'thrifty': 'Thrifty', 'dollar': 'Dollar', 'fox': 'Fox',
        'green motion': 'Green Motion', 'payless': 'Payless',
    }.items():
        if key in compania.lower():
            compania = nombre
            break

    # Validar categoría
    categorias_validas = list(RANGOS_PRECIO.keys())
    if categoria not in categorias_validas:
        return None

    # Validar transmisión
    if transmision not in ("Manual", "Automática"):
        transmision = "Manual" if categoria in ("Camioneta Pickup", "Mini", "Económico") else "Automática"

    # Regla: Pickup SIEMPRE Manual
    if categoria == "Camioneta Pickup":
        transmision = "Manual"

    # Validar precio
    if not precio_total or precio_total <= 0:
        return None

    precio_dia = precio_total / dias

    # Validar rango de precio por categoría
    rango = RANGOS_PRECIO.get(categoria, (15, 500))
    if not (rango[0] <= precio_dia <= rango[1]):
        return None

    return {
        "compania": compania,
        "categoria": categoria,
        "transmision": transmision,
        "modelo": modelo[:40],
        "precio_total": round(precio_total, 2),
        "precio_base": round(precio_base, 2) if precio_base else None,
        "precio_dia": round(precio_dia, 2),
    }


if __name__ == "__main__":
    # Test
    print("Test IA Parser...")

    # Verificar Ollama
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            print("✅ Ollama OK")
    except Exception:
        print("❌ Ollama no responde. Ejecuta: sudo systemctl start ollama")
        exit(1)

    # Test con 3 bloques
    test = [
        "Europcar, KIA RIO LX 1.4 o similar, Estándar, $33 $30 total",
        "Sixt, Toyota Hilux o similar, Manual, $180 $165 total",
        "Alamo, Chevrolet Spark, Automático, $25 $20 total",
    ]

    print("\nParseando 3 bloques con IA...")
    import time
    t0 = time.time()
    resultados = parsear_bloques_con_ia(test)
    print(f"⏱️ Tiempo: {time.time()-t0:.1f} seg\n")

    for i, (txt, r) in enumerate(zip(test, resultados), 1):
        print(f"BLOQUE {i}:")
        print(f"  Texto: {txt[:60]}...")
        print(f"  Parseado: {r}")
        if r:
            valido = validar_y_corregir(r, dias=3)
            print(f"  Validado: {valido}")
        print()
IA_PARSER

echo "✅ ia_parser.py creado"
wc -l ia_parser.py
./venv/bin/python3 -c "import ast; ast.parse(open('ia_parser.py').read()); print('✅ Sintaxis OK')"
