#!/usr/bin/env python3
"""
scraper_humano.py — Scraper de Expedia "modo humano".
Diseñado para NO ser bloqueado: navega despacio, rota identidad, cierra sesiones.
Extrae exactamente la misma información que el scraper v5.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import logging.handlers
import os
import random
import re
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PWTimeout

# ── CONFIG ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
LOG_PATH = os.path.join(BASE_DIR, "scraper_humano.log")
PROGRESO_PATH = os.path.join(BASE_DIR, "scraper_humano.progreso.json")

HEADLESS = os.getenv("SCRAPER_HEADLESS", "0") == "1"
MAX_REINTENTOS = 2
TIMEOUT_NAV = 120_000
ESPERA_JS = 45  # segundos a esperar a que Expedia cargue JS

# ── MODOS DE VELOCIDAD ─────────────────────────────────────────────────────
MODOS = {
    "rapido": {
        "nav_por_sesion": 12,
        "pausa_entre_nav": (2, 5),       # minutos
        "pausa_entre_sesion": (2, 5),    # minutos
        "descripcion": "~30 min (mayor riesgo de bloqueo)"
    },
    "normal": {
        "nav_por_sesion": 4,
        "pausa_entre_nav": (3, 6),
        "pausa_entre_sesion": (10, 15),
        "descripcion": "~1-1.5h (riesgo bajo)"
    },
    "seguro": {
        "nav_por_sesion": 3,
        "pausa_entre_nav": (5, 8),
        "pausa_entre_sesion": (18, 25),
        "descripcion": "~2-3h (riesgo muy bajo)"
    }
}

# ── IDENTIDADES ROTATIVAS ──────────────────────────────────────────────────
USER_AGENTS = [
    # Chrome en Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    # Chrome en Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    # Firefox en Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Firefox en Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Edge en Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1366, "height": 768},
    {"width": 1600, "height": 900},
]

IDIOMAS = ["es-EC,es;q=0.9,en;q=0.8", "es-ES,es;q=0.9,en;q=0.8", "en-US,en;q=0.9,es;q=0.8"]

# ── COMPAÑÍAS Y VARIANTES ──────────────────────────────────────────────────
VARIANTES = {
    "Avis": ["avis"], "Hertz": ["hertz"], "Europcar": ["europcar"],
    "Budget": ["budget"], "Localiza": ["localiza"], "Sixt": ["sixt"],
    "Alamo": ["alamo"], "Enterprise": ["enterprise"], "Thrifty": ["thrifty"],
    "Dollar": ["dollar"], "Ecovia": ["ecovia"], "Goldcar": ["goldcar"],
    "National": ["national"], "Payless": ["payless"],
    "Fox": ["fox rent", "fox car"],
    "Green Motion": ["green motion"],
    "Economy": ["economy rent", "economy car"],
    "MexRentaCar": ["mexrentacar"],
    "United Rent": ["united rent"],
    "Flexways": ["flexways"],
    "Kayak": ["kayak"],
}


# ── LOGGING ────────────────────────────────────────────────────────────────
class ColorFormatter(logging.Formatter):
    COLORS = {"DEBUG": "\033[36m", "INFO": "\033[92m", "WARNING": "\033[93m",
              "ERROR": "\033[91m", "CRITICAL": "\033[95m"}
    RESET = "\033[0m"
    def format(self, r):
        c = self.COLORS.get(r.levelname, "")
        return f"{c}{super().format(r)}{self.RESET}"


def setup_logging(verbose=False):
    lg = logging.getLogger("scraper_humano")
    lg.setLevel(logging.DEBUG)
    lg.handlers.clear()
    fmt = "%(asctime)s │ %(levelname)-7s │ %(message)s"
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(ColorFormatter(fmt, datefmt="%H:%M:%S"))
    lg.addHandler(ch)
    fh = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=5_000_000,
                                                backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
    lg.addHandler(fh)
    return lg


log = setup_logging()


# ── MODELO ─────────────────────────────────────────────────────────────────
@dataclass
class Registro:
    fecha_consulta: str; fecha_alquiler: str; duracion_dias: int
    plataforma: str; compania: str; modelo: str; categoria: str; transmision: str
    precio_total: Optional[float]; precio_dia: Optional[float]; moneda: str
    precio_total_crudo: str; precio_faltante: int; precio_estimado_ia: Optional[float]
    fuente_precio: str; rating: Optional[float]; reviews: Optional[int]
    cancelacion_gratis: int; url: str; fingerprint: str

    def to_row(self):
        d = asdict(self)
        keys = ["fecha_consulta", "fecha_alquiler", "duracion_dias", "plataforma",
                "compania", "modelo", "categoria", "transmision", "precio_total",
                "precio_dia", "moneda", "precio_total_crudo", "precio_faltante",
                "precio_estimado_ia", "fuente_precio", "rating", "reviews",
                "cancelacion_gratis", "url", "fingerprint"]
        return tuple(d[k] for k in keys)


# ── DB ─────────────────────────────────────────────────────────────────────
INSERT_SQL = """INSERT OR IGNORE INTO historial_precios
(fecha_consulta, fecha_alquiler, duracion_dias, plataforma, compania, modelo,
 categoria, transmision, precio_total, precio_dia, moneda, precio_total_crudo,
 precio_faltante, precio_estimado_ia, fuente_precio, rating, reviews,
 cancelacion_gratis, url, fingerprint)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""


def _connect():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def guardar(r):
    try:
        with _connect() as c:
            cur = c.execute(INSERT_SQL, r.to_row())
            c.commit()
            return cur.rowcount > 0
    except sqlite3.Error as e:
        log.error("DB: %s", e)
        return False


# ── PARSERS ────────────────────────────────────────────────────────────────
PRICE_RE = re.compile(r"\$\s*([\d.,]+)|\b([\d.,]+)\s*\$")


def limpiar_precio(raw):
    if not raw: return None
    s = re.sub(r"[^\d.,]", "", str(raw).replace(" ", ""))
    if not s: return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        p = s.split(",")
        s = s.replace(".", "").replace(",", ".") if len(p[-1]) == 2 else s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if 5 <= v <= 100_000 else None


def clasificar_categoria(t):
    t = t.lower()
    if any(w in t for w in ("suv", "todoterreno", "4x4", "crossover")):
        return "SUV Lujo" if any(w in t for w in ("lujo", "luxury", "premium")) else "SUV"
    if any(w in t for w in ("pickup", "pick-up")): return "Pickup"
    if any(w in t for w in ("van", "minivan", "furgoneta")): return "Van"
    if any(w in t for w in ("deportivo", "sport", "convertible")): return "Deportivo"
    if any(w in t for w in ("econó", "econom", "compact", "peque", "mini")): return "Económico"
    if any(w in t for w in ("median", "intermed", "estándar", "standard", "full size")): return "Mediano"
    if any(w in t for w in ("lujo", "luxury", "premium", "elite")): return "Lujo"
    return "Económico"


def clasificar_transmision(t):
    t = t.lower()
    return "Manual" if any(w in t for w in ("manual", "mecánic", "mecanic", "stick")) else "Automática"


def detectar_compania(texto):
    if not texto: return None
    t = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", texto.lower())).strip()
    for nombre, variantes in VARIANTES.items():
        for v in variantes:
            if re.search(r"\b" + re.escape(v) + r"\b", t):
                return nombre
    return None


def fingerprint(fecha, dur, comp, cat, trans, precio):
    raw = f"{fecha}|{dur}|{comp}|{cat}|{trans}|{precio}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


# ── BLOQUEO ────────────────────────────────────────────────────────────────
async def detectar_bloqueo(page) -> bool:
    try:
        title = (await page.title()).lower()
        if "bot or not" in title:
            return True
        html = (await page.content()).lower()
        señales = ["show us your human side", "you have been blocked",
                   "unusual traffic", "are you a robot"]
        return any(s in html for s in señales)
    except Exception:
        return False


# ── EXTRACCIÓN JS ──────────────────────────────────────────────────────────
async def extraer_con_js(page):
    """Extrae tarjetas con JavaScript (lee Shadow DOM y contenido dinámico)."""
    try:
        tarjetas = await page.evaluate("""
            () => {
                const resultados = [];
                const selects = [
                    '[data-stid*="car"]',
                    '[data-testid*="car"]',
                    'div[class*="uitk-card"]',
                    'div[class*="result-card"]',
                    'li[class*="result"]',
                    'article',
                ];
                const vistos = new Set();
                for (const sel of selects) {
                    try {
                        document.querySelectorAll(sel).forEach(el => {
                            const txt = el.innerText || '';
                            if (txt.includes('$') && txt.length > 40 && txt.length < 3000) {
                                const h = txt.slice(0, 100);
                                if (!vistos.has(h)) {
                                    vistos.add(h);
                                    resultados.push({
                                        texto: txt,
                                        url: el.querySelector('a')?.href || ''
                                    });
                                }
                            }
                        });
                    } catch(e) {}
                }
                return resultados;
            }
        """)
        return tarjetas or []
    except Exception as e:
        log.warning("Error JS: %s", e)
        return []


# ── SCROLL HUMANO ──────────────────────────────────────────────────────────
async def scroll_humano(page):
    pasos = random.randint(8, 18)
    for _ in range(pasos):
        delta = random.randint(500, 1300)
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(0.7, 1.6))
    # A veces sube un poco (como humano)
    if random.random() < 0.4:
        await page.mouse.wheel(0, -random.randint(200, 500))
        await asyncio.sleep(random.uniform(0.5, 1.2))


async def cerrar_banners(page):
    for sel in ['button:has-text("Aceptar")', 'button:has-text("Accept")',
                'button:has-text("OK")', 'button[aria-label*="close" i]',
                '#onetrust-accept-btn-handler']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(timeout=2000)
                await asyncio.sleep(random.uniform(0.5, 1.2))
        except:
            continue


# ── NAVEGACIÓN ─────────────────────────────────────────────────────────────
async def navegar_y_extraer(page, fecha_alq, dur):
    d1 = fecha_alq.strftime("%Y-%m-%d")
    d2 = (fecha_alq + timedelta(days=dur)).strftime("%Y-%m-%d")
    date1 = fecha_alq.strftime("%m/%d/%Y")
    date2 = (fecha_alq + timedelta(days=dur)).strftime("%m/%d/%Y")

    url = ("https://www.expedia.com/carsearch?"
           "locn=Quito%2C%20Ecuador%20(UIO-Mariscal%20Sucre%20Intl.)&"
           "pickupIATACode=UIO&olat=-0.124336&olon=-78.360908&dpln=5196117&"
           f"d1={d1}&d2={d2}&date1={date1}&date2={date2}&"
           "time1=1030AM&time2=1030AM&aarpcr=off&sort=RECOMMENDED_PRICE")

    log.info("🌐 Navegando: %s · %dd", d1, dur)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
    except PWTimeout:
        log.warning("⏱️ Timeout en %s · %dd", d1, dur)
        return 0

    # Espera humana para que Expedia cargue JS
    log.info("   ⏳ Esperando %ds a que cargue Expedia...", ESPERA_JS)
    await asyncio.sleep(ESPERA_JS)

    # Detectar bloqueo
    if await detectar_bloqueo(page):
        log.error("🚨 BLOQUEO DETECTADO en %s · %dd", d1, dur)
        return -1

    await cerrar_banners(page)
    await scroll_humano(page)

    # Extraer con JS
    tarjetas = await extraer_con_js(page)
    log.info("   📦 %d tarjetas crudas", len(tarjetas))

    if not tarjetas:
        return 0

    vistos = set()
    guardados = 0
    fecha_consulta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for t in tarjetas:
        txt = t.get("texto", "")
        href = t.get("url", "")

        compania = detectar_compania(txt)
        if not compania:
            continue

        m = PRICE_RE.search(txt)
        if not m:
            continue

        precio_crudo = m.group(0)
        precio_total = limpiar_precio(m.group(1) or m.group(2))
        categoria = clasificar_categoria(txt)
        transmision = clasificar_transmision(txt)
        precio_dia = round(precio_total / dur, 2) if precio_total else None

        fp = fingerprint(fecha_alq.strftime("%Y-%m-%d"), dur, compania, categoria,
                         transmision, precio_crudo)
        if fp in vistos: continue
        vistos.add(fp)

        reg = Registro(
            fecha_consulta=fecha_consulta, fecha_alquiler=fecha_alq.strftime("%Y-%m-%d"),
            duracion_dias=dur, plataforma="Expedia", compania=compania, modelo="",
            categoria=categoria, transmision=transmision,
            precio_total=precio_total, precio_dia=precio_dia,
            moneda="USD", precio_total_crudo=precio_crudo,
            precio_faltante=1 if precio_total is None else 0,
            precio_estimado_ia=None, fuente_precio="expedia",
            rating=None, reviews=None, cancelacion_gratis=0,
            url=href, fingerprint=fp)

        if guardar(reg):
            guardados += 1
            p = f"${precio_dia:.2f}/d" if precio_dia else "?"
            log.info("   [+] %s │ %s │ %s │ %s",
                     compania, categoria, transmision[:3], p)

    return guardados


# ── PROGRESO ───────────────────────────────────────────────────────────────
def cargar_progreso():
    if not os.path.exists(PROGRESO_PATH):
        return {"hechas": [], "fecha_inicio": datetime.now().isoformat()}
    try:
        with open(PROGRESO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"hechas": [], "fecha_inicio": datetime.now().isoformat()}


def guardar_progreso(progreso):
    with open(PROGRESO_PATH, "w", encoding="utf-8") as f:
        json.dump(progreso, f, indent=2, ensure_ascii=False)


def limpiar_progreso():
    if os.path.exists(PROGRESO_PATH):
        os.remove(PROGRESO_PATH)


# ── PARSER FECHA ───────────────────────────────────────────────────────────
def parsear_fecha(s):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


# ── EJECUCIÓN PRINCIPAL ────────────────────────────────────────────────────
async def ejecutar(fechas, duraciones, modo):
    config = MODOS[modo]
    nav_por_sesion = config["nav_por_sesion"]
    pausa_min, pausa_max = config["pausa_entre_nav"]
    pausa_ses_min, pausa_ses_max = config["pausa_entre_sesion"]

    # Construir lista de tareas
    tareas = []
    for f in fechas:
        for d in duraciones:
            tareas.append((f, d))

    # Orden aleatorio para no ser predecible
    random.shuffle(tareas)

    progreso = cargar_progreso()
    hechas = set(progreso.get("hechas", []))
    pendientes = [(f, d) for f, d in tareas
                  if f"{f.strftime('%Y-%m-%d')}|{d}" not in hechas]

    total = len(pendientes)
    log.info("=" * 60)
    log.info("  SCRAPER HUMANO · MODO: %s", modo.upper())
    log.info("  %s", config["descripcion"])
    log.info("  Tareas pendientes: %d (de %d totales)", total, len(tareas))
    log.info("  Navegaciones por sesión: %d", nav_por_sesion)
    log.info("  Pausa entre navegaciones: %d-%d min", pausa_min, pausa_max)
    log.info("  Pausa entre sesiones: %d-%d min", pausa_ses_min, pausa_ses_max)
    log.info("=" * 60)

    if total == 0:
        log.info("✅ Todo ya estaba hecho.")
        return

    total_guardados = 0
    num_sesion = 0

    async with async_playwright() as pw:
        while pendientes:
            num_sesion += 1
            # Nuevo navegador por sesión (fingerprint distinto)
            user_agent = random.choice(USER_AGENTS)
            viewport = random.choice(VIEWPORTS)
            idioma = random.choice(IDIOMAS)

            log.info("")
            log.info("═" * 60)
            log.info("🚀 SESIÓN %d · UA: %s", num_sesion, user_agent[:60])
            log.info("═" * 60)

            browser = await pw.chromium.launch(
                headless=HEADLESS,
                args=["--disable-blink-features=AutomationControlled",
                      "--no-sandbox", "--disable-dev-shm-usage",
                      "--ozone-platform=x11"],
            )
            context = await browser.new_context(
                viewport=viewport,
                locale="es-EC",
                timezone_id="America/Guayaquil",
                user_agent=user_agent,
                extra_http_headers={"Accept-Language": idioma},
                geolocation={"latitude": -0.1243, "longitude": -78.3602},
                permissions=["geolocation"],
            )
            await context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                "window.chrome = { runtime: {} };"
                "Object.defineProperty(navigator,'languages',{get:()=>['es-EC','es','en']});"
                "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
            )
            page = await context.new_page()

            try:
                for i in range(nav_por_sesion):
                    if not pendientes:
                        break
                    fecha, dur = pendientes.pop(0)

                    guardados = await navegar_y_extraer(page, fecha, dur)

                    if guardados == -1:
                        # Bloqueo → parar todo
                        log.error("🛑 BLOQUEO · Parando ejecución")
                        log.error("   Espera 24-48h antes de volver a intentar")
                        log.error("   Progreso guardado: puedes reanudar después")
                        guardar_progreso({"hechas": list(hechas),
                                           "fecha_inicio": progreso.get("fecha_inicio")})
                        await context.close()
                        await browser.close()
                        return

                    hechas.add(f"{fecha.strftime('%Y-%m-%d')}|{dur}")
                    total_guardados += guardados

                    guardar_progreso({"hechas": list(hechas),
                                       "fecha_inicio": progreso.get("fecha_inicio")})

                    log.info("   ✅ %d registros guardados (total: %d)",
                             guardados, total_guardados)

                    # Pausa entre navegaciones (si quedan)
                    if i < nav_por_sesion - 1 and pendientes:
                        seg = random.randint(pausa_min * 60, pausa_max * 60)
                        log.info("   💤 Pausa %d min...", seg // 60)
                        await asyncio.sleep(seg)

            finally:
                try:
                    await context.close()
                    await browser.close()
                    log.info("   🔒 Navegador cerrado")
                except:
                    pass

            # Pausa entre sesiones (si quedan tareas)
            if pendientes:
                seg = random.randint(pausa_ses_min * 60, pausa_ses_max * 60)
                log.info("")
                log.info("⏸️  Pausa entre sesiones: %d min", seg // 60)
                log.info("   Próxima sesión a las %s",
                         (datetime.now() + timedelta(seconds=seg)).strftime("%H:%M"))
                await asyncio.sleep(seg)

    log.info("")
    log.info("═" * 60)
    log.info("✅ COMPLETADO")
    log.info("   Total registros guardados: %d", total_guardados)
    log.info("   Fecha inicio: %s", progreso.get("fecha_inicio", "—"))
    log.info("═" * 60)
    limpiar_progreso()


def main():
    ap = argparse.ArgumentParser(description="Scraper humano Expedia")
    ap.add_argument("--fechas", required=True,
                    help="Fechas separadas por coma: 2026-12-31,2027-01-25")
    ap.add_argument("--duraciones", default="3,5,7,15,21,30")
    ap.add_argument("--modo", choices=["rapido", "normal", "seguro"],
                    default="seguro", help="Velocidad de navegación")
    ap.add_argument("--reanudar", action="store_true",
                    help="Reanudar desde progreso guardado")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.verbose:
        for h in log.handlers:
            h.setLevel(logging.DEBUG)

    if not args.reanudar and os.path.exists(PROGRESO_PATH):
        log.warning("⚠️ Existe progreso anterior. Se ignorará. Usa --reanudar para continuar.")

    fechas = [parsear_fecha(s) for s in args.fechas.split(",")]
    fechas = [f for f in fechas if f]
    if not fechas:
        log.error("Fechas inválidas"); sys.exit(1)

    duraciones = [int(d.strip()) for d in args.duraciones.split(",") if d.strip()]

    log.info("Fechas: %s", [f.date().isoformat() for f in fechas])
    log.info("Duraciones: %s", duraciones)
    log.info("Modo: %s", args.modo)

    try:
        asyncio.run(ejecutar(fechas, duraciones, args.modo))
    except KeyboardInterrupt:
        log.warning("⚠️ Interrumpido. Progreso guardado en %s", PROGRESO_PATH)
        log.warning("   Reanuda con: --reanudar")


if __name__ == "__main__":
    main()
