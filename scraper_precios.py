# scraper_precios.py
"""
Scraper UIO — Perfil persistente + whitelist + stealth.
Parámetros: --fecha (hoy|YYYY-MM-DD) --duraciones --plataformas
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import logging.handlers
import os
import random
import re
import subprocess
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import List, Optional

from playwright.async_api import (
    async_playwright, Page, BrowserContext,
    TimeoutError as PlaywrightTimeoutError,
)

# Stealth opcional
try:
    from playwright_stealth import stealth_async
    STEALTH_DISPONIBLE = True
except ImportError:
    STEALTH_DISPONIBLE = False


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
LOG_PATH = os.path.join(BASE_DIR, "scraper.log")
USER_DATA_DIR = os.path.join(BASE_DIR, "chrome_session_data")

HEADLESS = os.getenv("SCRAPER_HEADLESS", "0") == "1"
MAX_REINTENTOS = 3
BACKOFF_BASE = 5.0
TIMEOUT_NAV = 90_000
PRECIO_MIN_DIA = 10.0
PRECIO_MAX_DIA = 3000.0
PRECIO_MIN_TOTAL = 20.0

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

COMPANIAS_WHITELIST = {
    "Europcar": ["europcar"],
    "Alamo": ["alamo"],
    "Localiza": ["localiza"],
    "Keddy": ["keddy"],
    "Goldcar": ["goldcar"],
    "Sixt": ["sixt"],
    "Avis": ["avis"],
    "Budget": ["budget"],
    "Hertz": ["hertz"],
    "National": ["national"],
    "Enterprise": ["enterprise"],
    "Thrifty": ["thrifty"],
    "Dollar": ["dollar"],
    "Fox": ["fox rent"],
    "Green Motion": ["green motion"],
    "Payless": ["payless"],
}


def buscar_compania_whitelist(texto_lower: str) -> Optional[str]:
    for nombre, keys in COMPANIAS_WHITELIST.items():
        for key in keys:
            if key in texto_lower:
                return nombre
    return None


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("scraper")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    fh = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


log = setup_logging()


# ══════════════════════════════════════════════════════════════════════════════
# MODELO
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Registro:
    fecha_consulta: str
    fecha_recogida: str
    plataforma: str
    compania: str
    categoria: str
    transmision: str
    precio_total: float
    precio_dia: float
    moneda: str
    dias: int
    horizonte: str
    fechas_alquiler: str
    url: str = ""
    fingerprint: str = ""

    def to_row(self) -> tuple:
        d = asdict(self)
        return tuple(d[k] for k in [
            "fecha_consulta", "fecha_recogida", "plataforma", "compania",
            "categoria", "transmision", "precio_total", "precio_dia",
            "moneda", "dias", "horizonte", "fechas_alquiler", "url", "fingerprint",
        ])


# ══════════════════════════════════════════════════════════════════════════════
# DB
# ══════════════════════════════════════════════════════════════════════════════

SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS historial_precios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_consulta TEXT NOT NULL,
    fecha_recogida TEXT,
    plataforma TEXT NOT NULL,
    compania TEXT,
    categoria TEXT,
    transmision TEXT,
    precio_total REAL,
    precio_dia REAL,
    moneda TEXT DEFAULT 'USD',
    dias INTEGER,
    horizonte TEXT,
    fechas_alquiler TEXT,
    url TEXT,
    fingerprint TEXT UNIQUE
)
"""

INSERT_SQL = """
INSERT OR IGNORE INTO historial_precios
(fecha_consulta, fecha_recogida, plataforma, compania, categoria, transmision,
 precio_total, precio_dia, moneda, dias, horizonte, fechas_alquiler, url, fingerprint)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _connect() as conn:
        conn.execute(SCHEMA_TABLE)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(historial_precios)").fetchall()]
        for col, tipo in [("fecha_recogida", "TEXT"), ("categoria", "TEXT"),
                          ("transmision", "TEXT"), ("precio_total", "REAL"),
                          ("precio_dia", "REAL"), ("dias", "INTEGER")]:
            if col not in cols:
                conn.execute(f"ALTER TABLE historial_precios ADD COLUMN {col} {tipo}")
        for stmt in [
            "CREATE INDEX IF NOT EXISTS idx_fecha_recogida ON historial_precios(fecha_recogida)",
            "CREATE INDEX IF NOT EXISTS idx_dias ON historial_precios(dias)",
            "CREATE INDEX IF NOT EXISTS idx_compania ON historial_precios(compania)",
        ]:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        conn.commit()
    log.info("DB lista en %s", DB_PATH)


def guardar_registro(reg: Registro) -> bool:
    try:
        with _connect() as conn:
            cur = conn.execute(INSERT_SQL, reg.to_row())
            conn.commit()
            return cur.rowcount > 0
    except sqlite3.Error as e:
        log.error("Error guardando: %s", e)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# PARSEO
# ══════════════════════════════════════════════════════════════════════════════

PRICE_RE = re.compile(
    r"\$\s*([\d]{1,5}(?:[.,]\d{1,3})*)|([\d]{1,5}(?:[.,]\d{1,3})*)\s*\$"
)
TOTAL_KEYWORDS = ["total", "precio total", "total price", "precio final", "importe"]
PER_DAY_KEYWORDS = ["por día", "por dia", "/día", "/dia", "per day", "/day", "daily"]


def _limpiar_numero(raw: str) -> Optional[float]:
    if not raw:
        return None
    s = raw.strip().replace(" ", "").replace("\xa0", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        partes = s.split(",")
        if len(partes[-1]) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        partes = s.split(".")
        if len(partes[-1]) != 2:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def extraer_precio_total(texto: str, dias: int) -> Optional[tuple]:
    if not texto or dias < 1:
        return None
    precios = []
    for m in PRICE_RE.finditer(texto):
        raw = m.group(1) or m.group(2)
        val = _limpiar_numero(raw)
        if val is None or val <= 0:
            continue
        ctx = (texto[max(0, m.start()-80):m.start()] + " " +
               texto[m.end():min(len(texto), m.end()+80)]).lower()
        precios.append({"valor": val, "ctx": ctx})
    if not precios:
        return None
    cands = [p["valor"] for p in precios
             if any(k in p["ctx"] for k in TOTAL_KEYWORDS)
             and not any(k in p["ctx"] for k in PER_DAY_KEYWORDS)]
    if cands:
        t = max(cands)
        pd_val = t / dias
        if PRECIO_MIN_TOTAL <= t <= (PRECIO_MAX_DIA * dias):
            return (round(t, 2), round(pd_val, 2))
    if len(precios) == 1:
        v = precios[0]["valor"]
        if v >= PRECIO_MIN_TOTAL:
            pd_val = v / dias
            if PRECIO_MIN_DIA <= pd_val <= PRECIO_MAX_DIA:
                return (round(v, 2), round(pd_val, 2))
    max_v = max(p["valor"] for p in precios)
    if max_v >= PRECIO_MIN_TOTAL:
        pd_val = max_v / dias
        if PRECIO_MIN_DIA <= pd_val <= PRECIO_MAX_DIA:
            return (round(max_v, 2), round(pd_val, 2))
    return None


def clasificar_categoria(texto: str) -> str:
    t = texto.lower()
    if any(w in t for w in ("suv", "todoterreno", "4x4", "crossover")):
        return "SUV Lujo" if any(w in t for w in ("lujo", "luxury", "premium")) else "SUV"
    if any(w in t for w in ("van", "minivan", "furgoneta")):
        return "Van"
    if any(w in t for w in ("pickup", "camioneta", "pick-up")):
        return "Pickup"
    if any(w in t for w in ("deportivo", "sport", "convertible")):
        return "Deportivo"
    if any(w in t for w in ("económ", "econom", "compact", "pequeño", "mini")):
        return "Económico"
    if any(w in t for w in ("median", "intermed", "estándar", "standard")):
        return "Mediano"
    return "Económico"


def clasificar_transmision(texto: str) -> str:
    t = texto.lower()
    if any(w in t for w in ("manual", "mecánic", "mt ", "m/t")):
        return "Manual"
    return "Automática"


def fingerprint(plataforma: str, compania: str, categoria: str,
                transmision: str, precio: float, fechas: str) -> str:
    raw = f"{plataforma}|{compania}|{categoria}|{transmision}|{precio:.2f}|{fechas}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def parsear_card(texto: str, dias: int) -> Optional[dict]:
    if not texto or len(texto) > 2000 or "$" not in texto:
        return None
    t_low = texto.lower()
    señales = ["suv", "sedan", "compact", "econom", "van", "pickup",
               "auto", "car", "vehicle", "vehículo", "asiento", "seat",
               "puerta", "door", "maleta", "bag", "automátic", "automatic",
               "manual", "transmisión", "rental", "día", "day"]
    if not any(s in t_low for s in señales):
        return None
    compania = buscar_compania_whitelist(t_low)
    if not compania:
        return None
    precio_info = extraer_precio_total(texto, dias)
    if not precio_info:
        return None
    precio_total, precio_dia = precio_info
    return {
        "compania": compania,
        "categoria": clasificar_categoria(texto),
        "transmision": clasificar_transmision(texto),
        "precio_total": precio_total,
        "precio_dia": precio_dia,
    }


# ══════════════════════════════════════════════════════════════════════════════
# LIMPIEZA + NAVEGACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def _matar_chromium_colgados():
    try:
        subprocess.run(
            ["pkill", "-f", "ms-playwright/.*chrome"],
            timeout=5, capture_output=True
        )
    except Exception:
        pass


async def _aplicar_stealth(page: Page):
    if STEALTH_DISPONIBLE:
        try:
            await stealth_async(page)
        except Exception:
            pass


async def _humanizar(page: Page, pasos: int = 6):
    for _ in range(pasos):
        try:
            await page.mouse.move(
                random.randint(100, 1200),
                random.randint(100, 700),
                steps=random.randint(5, 15),
            )
        except Exception:
            pass
        await page.mouse.wheel(0, random.randint(400, 1200))
        await asyncio.sleep(random.uniform(0.8, 2.2))


async def _cerrar_banners(page: Page):
    for sel in [
        'button:has-text("Aceptar")', 'button:has-text("Accept")',
        'button:has-text("Acepto")', 'button:has-text("OK")',
        '[id*="onetrust-accept"]', '#onetrust-accept-btn-handler',
    ]:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(timeout=2000)
                await asyncio.sleep(random.uniform(0.5, 1.5))
        except Exception:
            continue


async def _detectar_bloqueo(page: Page, plataforma: str) -> bool:
    try:
        try:
            title = (await page.title() or "").lower()
        except Exception:
            title = ""
        señales = ["bot or not", "access denied", "are you a robot",
                   "just a moment", "verifying you are human"]
        if any(s in title for s in señales):
            log.warning("🚨 CAPTCHA en %s. Resuélvelo en el navegador.", plataforma)
            log.warning("⏳ Esperando hasta 3 minutos...")
            for _ in range(36):
                await asyncio.sleep(5)
                try:
                    t2 = (await page.title() or "").lower()
                    if not any(s in t2 for s in señales):
                        log.info("✅ Captcha resuelto.")
                        return False
                except Exception:
                    pass
            log.error("❌ Timeout captcha.")
            return True
        try:
            body = (await page.inner_text("body"))[:2000].lower()
        except Exception:
            body = ""
        señales_body = ["show us your human side", "slide right to secure",
                        "confirm you are not a robot", "unusual traffic"]
        if any(s in body for s in señales_body):
            log.warning("🚨 CAPTCHA visible en %s. Resuélvelo (3 min).", plataforma)
            for _ in range(36):
                await asyncio.sleep(5)
                try:
                    b2 = (await page.inner_text("body"))[:2000].lower()
                    if not any(s in b2 for s in señales_body):
                        log.info("✅ Captcha resuelto.")
                        return False
                except Exception:
                    pass
            return True
        return False
    except Exception:
        return False


async def _navegar(page: Page, url: str, plataforma: str) -> bool:
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            log.debug("[%s] GET (intento %d/%d)", plataforma, intento, MAX_REINTENTOS)
            await _aplicar_stealth(page)
            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
            await asyncio.sleep(random.uniform(5.0, 9.0))
            await _cerrar_banners(page)
            await _humanizar(page, pasos=random.randint(5, 9))
            await asyncio.sleep(random.uniform(2.0, 4.0))
            if await _detectar_bloqueo(page, plataforma):
                log.warning("[%s] Bloqueo persistente. Saltando.", plataforma)
                return False
            return True
        except PlaywrightTimeoutError:
            log.warning("[%s] Timeout", plataforma)
        except Exception as e:
            log.warning("[%s] Error: %s", plataforma, e)
        await asyncio.sleep(BACKOFF_BASE * intento + random.uniform(0, 2))
    return False


SEL_CANDIDATOS = [
    '[data-testid*="car"]', '[data-testid*="vehicle"]',
    '[data-testid*="result-card"]', 'li[class*="car"]',
    'div[class*="CarCard"]', 'div[class*="car-card"]',
    'div[class*="VehicleCard"]', 'div[class*="vehicle-card"]',
    'div[class*="ResultCard"]', 'div[class*="result-card"]',
    'article[class*="car"]',
]


async def extraer_tarjetas(page: Page, plataforma: str, horizonte: str,
                           fechas: str, dias: int, fecha_recogida_iso: str) -> int:
    textos = []
    for sel in SEL_CANDIDATOS:
        try:
            els = await page.query_selector_all(sel)
        except Exception:
            continue
        for el in els:
            try:
                txt = (await el.inner_text()) or ""
            except Exception:
                continue
            if "$" in txt and 20 < len(txt) < 2000:
                href = ""
                try:
                    a = await el.query_selector("a[href]")
                    if a:
                        href = await a.get_attribute("href") or ""
                except Exception:
                    pass
                textos.append((txt, href))
        if len(textos) >= 10:
            break

    if not textos:
        try:
            els = await page.query_selector_all("div, li, article")
        except Exception:
            els = []
        for el in els:
            try:
                txt = (await el.inner_text()) or ""
            except Exception:
                continue
            if "$" in txt and 20 < len(txt) < 1000:
                textos.append((txt, ""))

    if not textos:
        log.warning("[%s] Sin tarjetas en %s", plataforma, horizonte)
        return 0

    log.info("[%s] %d tarjetas candidatas", plataforma, len(textos))

    vistos = set()
    guardados = 0
    fecha_consulta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for txt, href in textos:
        info = parsear_card(txt, dias)
        if not info:
            continue
        fp = fingerprint(plataforma, info["compania"], info["categoria"],
                         info["transmision"], info["precio_total"], fechas)
        if fp in vistos:
            continue
        vistos.add(fp)

        reg = Registro(
            fecha_consulta=fecha_consulta,
            fecha_recogida=fecha_recogida_iso,
            plataforma=plataforma,
            compania=info["compania"],
            categoria=info["categoria"],
            transmision=info["transmision"],
            precio_total=info["precio_total"],
            precio_dia=info["precio_dia"],
            moneda="USD",
            dias=dias,
            horizonte=horizonte,
            fechas_alquiler=fechas,
            url=href,
            fingerprint=fp,
        )
        if guardar_registro(reg):
            guardados += 1
            log.info("   [+] %s | %s | %s | $%.2f/día (%dd) | Total $%.2f",
                     plataforma, info["compania"], info["categoria"],
                     info["precio_dia"], dias, info["precio_total"])

    log.info("[%s] %s → %d registros", plataforma, horizonte, guardados)
    return guardados


# ══════════════════════════════════════════════════════════════════════════════
# SCRAPERS
# ══════════════════════════════════════════════════════════════════════════════

async def extraer_expedia(fecha_ini: datetime, dias: int, page: Page) -> int:
    fecha_fin = fecha_ini + timedelta(days=dias)
    d1 = fecha_ini.strftime("%Y-%m-%d")
    d2 = fecha_fin.strftime("%Y-%m-%d")
    date1 = fecha_ini.strftime("%m/%d/%Y")
    date2 = fecha_fin.strftime("%m/%d/%Y")

    url = (
        "https://www.expedia.com/carsearch?"
        "locn=Quito%2C%20Ecuador%20(UIO-Mariscal%20Sucre%20Intl.)&"
        "pickupIATACode=UIO&olat=-0.124336&olon=-78.360908&dpln=5196117&"
        f"d1={d1}&d2={d2}&date1={date1}&date2={date2}&"
        "time1=1030AM&time2=1030AM&aarpcr=off&sort=RECOMMENDED_PRICE"
    )
    fechas_str = f"{d1} a {d2}"
    log.info("🚀 [EXPEDIA] %s días desde %s", dias, d1)
    if not await _navegar(page, url, "Expedia"):
        return 0
    return await extraer_tarjetas(page, "Expedia", f"{dias} Días",
                                  fechas_str, dias, d1)


async def extraer_booking(fecha_ini: datetime, dias: int, page: Page) -> int:
    fecha_fin = fecha_ini + timedelta(days=dias)
    d1 = fecha_ini.strftime("%Y-%m-%d")
    d2 = fecha_fin.strftime("%Y-%m-%d")

    url = (
        "https://cars.booking.com/search-results?"
        "cor=ec&intent=direct&prefcurrency=USD&preflang=es&"
        "locationName=Aeropuerto+internacional+Mariscal+Sucre+%28UIO%29&locationIata=UIO&"
        "dropLocationName=Aeropuerto+internacional+Mariscal+Sucre+%28UIO%29&dropLocationIata=UIO&"
        "coordinates=-0.124283%2C-78.360198&dropCoordinates=-0.124283%2C-78.360198&"
        f"driversAge=30&puDay={fecha_ini.day}&puMonth={fecha_ini.month}&puYear={fecha_ini.year}"
        f"&puHour=10&puMinute=0&"
        f"doDay={fecha_fin.day}&doMonth={fecha_fin.month}&doYear={fecha_fin.year}"
        f"&doHour=10&doMinute=0&"
        "ftsType=A&dropFtsType=A&sort_by=price_asc"
    )
    fechas_str = f"{d1} a {d2}"
    log.info("🚀 [BOOKING] %s días desde %s", dias, d1)
    if not await _navegar(page, url, "Booking"):
        return 0
    return await extraer_tarjetas(page, "Booking", f"{dias} Días",
                                  fechas_str, dias, d1)


PLATAFORMAS = {"expedia": extraer_expedia, "booking": extraer_booking}


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXTO
# ══════════════════════════════════════════════════════════════════════════════

async def crear_contexto(pw) -> BrowserContext:
    _matar_chromium_colgados()
    await asyncio.sleep(1.5)
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--start-maximized",
        "--disable-notifications",
        "--disable-popup-blocking",
    ]

    for intento in range(1, 4):
        try:
            context = await pw.chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=HEADLESS,
                args=args,
                viewport=None if not HEADLESS else {"width": 1366, "height": 900},
                locale="es-EC",
                timezone_id="America/Guayaquil",
                user_agent=USER_AGENT,
                geolocation={"latitude": -0.1243, "longitude": -78.3602},
                permissions=["geolocation"],
                timeout=90_000,
                ignore_https_errors=True,
            )
            await context.add_init_script("""
                Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
                Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
                Object.defineProperty(navigator,'languages',{get:()=>['es-EC','es','en']});
                window.chrome = { runtime: {} };
            """)
            log.info("✅ Contexto Chromium listo")
            return context
        except Exception as e:
            log.warning("Intento %d crear contexto: %s", intento, e)
            _matar_chromium_colgados()
            if intento < 3:
                await asyncio.sleep(5 * intento)
                continue
            raise
    raise RuntimeError("No se pudo crear el contexto")


# ══════════════════════════════════════════════════════════════════════════════
# EJECUCIÓN
# ══════════════════════════════════════════════════════════════════════════════

async def ejecutar(fecha_recogida: datetime, duraciones: List[int],
                   plataformas: List[str]) -> None:
    init_db()
    total = 0
    async with async_playwright() as pw:
        context = await crear_contexto(pw)
        page = context.pages[0] if context.pages else await context.new_page()
        if STEALTH_DISPONIBLE:
            try:
                await stealth_async(page)
                log.info("🛡️ Stealth aplicado")
            except Exception:
                pass
        try:
            log.info("=" * 70)
            log.info("FECHA: %s | DURACIONES: %s | PLATAFORMAS: %s",
                     fecha_recogida.strftime("%Y-%m-%d"), duraciones, plataformas)
            log.info("=" * 70)
            for dias in duraciones:
                for nombre in plataformas:
                    fn = PLATAFORMAS[nombre]
                    try:
                        n = await fn(fecha_recogida, dias, page)
                        total += n
                    except Exception as e:
                        log.exception("[%s] Error (%dd): %s", nombre, dias, e)
                    await asyncio.sleep(random.uniform(6.0, 12.0))
        finally:
            log.info("TOTAL REGISTROS NUEVOS: %d", total)
            try:
                await context.close()
            except Exception:
                pass


def _parsear_fecha(s: str) -> datetime:
    s = s.strip().lower()
    if s in ("hoy", "today"):
        return datetime.now().replace(hour=10, minute=30, second=0, microsecond=0)
    if s in ("mañana", "manana", "tomorrow"):
        return (datetime.now() + timedelta(days=1)).replace(hour=10, minute=30, second=0, microsecond=0)
    return datetime.strptime(s, "%Y-%m-%d").replace(hour=10, minute=30, second=0, microsecond=0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", required=True)
    ap.add_argument("--duraciones", default="3,5,7,15,21,30")
    ap.add_argument("--plataformas", default="expedia,booking")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)
        for h in log.handlers:
            h.setLevel(logging.DEBUG)

    try:
        fecha = _parsear_fecha(args.fecha)
    except ValueError:
        log.error("Fecha inválida: %s", args.fecha)
        sys.exit(1)

    try:
        durs = sorted(set(int(d.strip()) for d in args.duraciones.split(",") if d.strip()))
    except ValueError:
        log.error("Duraciones inválidas")
        sys.exit(1)

    plats = [p.strip().lower() for p in args.plataformas.split(",") if p.strip()]
    invalidas = [p for p in plats if p not in PLATAFORMAS]
    if invalidas:
        log.error("Plataformas inválidas: %s", invalidas)
        sys.exit(1)

    try:
        asyncio.run(ejecutar(fecha, durs, plats))
    except KeyboardInterrupt:
        log.warning("Interrumpido")


if __name__ == "__main__":
    main()
