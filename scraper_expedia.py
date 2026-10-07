#!/usr/bin/env python3
"""
scraper_expedia.py — Scraper de Expedia (solo) para alquiler de autos en UIO.
Diseño: Cyberpunk / senior-grade.
Extrae precios crudos + procesados. NO deja días sin precio (marca precio_faltante=1).
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
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Page,
    BrowserContext,
    TimeoutError as PlaywrightTimeoutError,
)

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
LOG_PATH = os.path.join(BASE_DIR, "scraper_expedia.log")
USER_DATA_DIR = os.path.join(BASE_DIR, "chrome_session_expedia")

HEADLESS = os.getenv("SCRAPER_HEADLESS", "0") == "1"
MAX_REINTENTOS = 3
BACKOFF_BASE = 4.0
TIMEOUT_NAV = 90_000
ESPERA_TRAS_CARGA = (5.0, 9.0)
ESPERA_ENTRE_HORIZONTES = (3.0, 6.0)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

DURACIONES_DEFAULT = [3, 5, 7, 15, 21, 30]

EMPRESAS = {
    "avis": "Avis", "hertz": "Hertz", "europcar": "Europcar", "budget": "Budget",
    "localiza": "Localiza", "sixt": "Sixt", "alamo": "Alamo", "enterprise": "Enterprise",
    "thrifty": "Thrifty", "dollar": "Dollar", "ecovia": "Ecovia", "goldcar": "Goldcar",
    "national": "National", "kayak": "Kayak", "flexways": "Flexways",
    "mexrentacar": "MexRentaCar", "united rent": "United Rent",
    "economy": "Economy", "payless": "Payless", "fox": "Fox", "green motion": "Green Motion",
}

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING (colores ANSI Cyberpunk)
# ──────────────────────────────────────────────────────────────────────────────
class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG":    "\033[36m",   # cian
        "INFO":     "\033[92m",   # verde neón
        "WARNING":  "\033[93m",   # amarillo Cyberpunk
        "ERROR":    "\033[91m",   # rojo neón
        "CRITICAL": "\033[95m",   # magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        msg = super().format(record)
        return f"{color}{msg}{self.RESET}"


def setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("scraper_expedia")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = "%(asctime)s │ %(levelname)-7s │ %(message)s"
    datefmt = "%H:%M:%S"

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(ColorFormatter(fmt, datefmt=datefmt))
    logger.addHandler(ch)

    fh = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logger.addHandler(fh)

    return logger


log = setup_logging()

# ──────────────────────────────────────────────────────────────────────────────
# MODELO
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Registro:
    fecha_consulta: str
    fecha_alquiler: str
    duracion_dias: int
    plataforma: str
    compania: str
    modelo: str
    categoria: str
    transmision: str
    precio_total: Optional[float]
    precio_dia: Optional[float]
    moneda: str
    precio_total_crudo: str
    precio_faltante: int
    precio_estimado_ia: Optional[float]
    fuente_precio: str
    rating: Optional[float]
    reviews: Optional[int]
    cancelacion_gratis: int
    url: str
    fingerprint: str

    def to_row(self) -> tuple:
        d = asdict(self)
        keys = [
            "fecha_consulta", "fecha_alquiler", "duracion_dias", "plataforma",
            "compania", "modelo", "categoria", "transmision",
            "precio_total", "precio_dia", "moneda", "precio_total_crudo",
            "precio_faltante", "precio_estimado_ia", "fuente_precio",
            "rating", "reviews", "cancelacion_gratis", "url", "fingerprint",
        ]
        return tuple(d[k] for k in keys)


# ──────────────────────────────────────────────────────────────────────────────
# DB
# ──────────────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS historial_precios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_consulta TEXT NOT NULL,
    fecha_alquiler TEXT NOT NULL,
    duracion_dias INTEGER NOT NULL,
    plataforma TEXT NOT NULL,
    compania TEXT,
    modelo TEXT,
    categoria TEXT,
    transmision TEXT,
    precio_total REAL,
    precio_dia REAL,
    moneda TEXT DEFAULT 'USD',
    precio_total_crudo TEXT,
    precio_faltante INTEGER DEFAULT 0,
    precio_estimado_ia REAL,
    fuente_precio TEXT DEFAULT 'expedia',
    rating REAL,
    reviews INTEGER,
    cancelacion_gratis INTEGER DEFAULT 0,
    url TEXT,
    fingerprint TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_fecha_alq ON historial_precios(fecha_alquiler);
CREATE INDEX IF NOT EXISTS idx_duracion ON historial_precios(duracion_dias);
CREATE INDEX IF NOT EXISTS idx_compania ON historial_precios(compania);
CREATE INDEX IF NOT EXISTS idx_categoria ON historial_precios(categoria);
CREATE INDEX IF NOT EXISTS idx_faltante ON historial_precios(precio_faltante);
"""

INSERT_SQL = """
INSERT OR IGNORE INTO historial_precios
(fecha_consulta, fecha_alquiler, duracion_dias, plataforma, compania, modelo,
 categoria, transmision, precio_total, precio_dia, moneda, precio_total_crudo,
 precio_faltante, precio_estimado_ia, fuente_precio, rating, reviews,
 cancelacion_gratis, url, fingerprint)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        for stmt in SCHEMA.strip().split(";"):
            if stmt.strip():
                conn.execute(stmt)
        conn.commit()
    log.info("DB lista: %s", DB_PATH)


def guardar_registro(reg: Registro) -> bool:
    try:
        with _connect() as conn:
            cur = conn.execute(INSERT_SQL, reg.to_row())
            conn.commit()
            return cur.rowcount > 0
    except sqlite3.Error as e:
        log.error("Error DB: %s", e)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# PARSERS
# ──────────────────────────────────────────────────────────────────────────────
PRICE_RE = re.compile(r"\$\s*([\d.,]+)|\b([\d.,]+)\s*\$")
RATING_RE = re.compile(r"(\d+[.,]\d)\s*(?:/|de)\s*5|(\d+[.,]\d)\s*★")
REVIEWS_RE = re.compile(r"\((\d{2,6})\)")

MODELO_RE = re.compile(
    r"\b(Toyota|Chevrolet|Hyundai|Kia|Nissan|Mazda|Renault|Ford|Volkswagen|VW|"
    r"Mitsubishi|Suzuki|Honda|Peugeot|Citro[eë]n|Fiat|Jeep|BMW|Mercedes|"
    r"Audi|Subaru|Chery|Great Wall|Haval|JAC|Dongfeng|BYD)\s+([A-Za-z0-9\- ]{2,25})",
    re.IGNORECASE,
)


def limpiar_precio(raw: str) -> Optional[float]:
    if not raw:
        return None
    s = raw.strip().replace(" ", "").replace("\u00a0", "")
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        partes = s.split(",")
        if len(partes[-1]) == 2:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        val = float(s)
    except ValueError:
        return None
    return val if 5 <= val <= 100_000 else None


def clasificar_categoria(texto: str) -> str:
    t = texto.lower()
    if any(w in t for w in ("suv", "todoterreno", "4x4", "crossover", "camioneta suv")):
        return "SUV Lujo" if any(w in t for w in ("lujo", "luxury", "premium")) else "SUV"
    if any(w in t for w in ("pickup", "pick-up", "camioneta pick")):
        return "Pickup"
    if any(w in t for w in ("van", "minivan", "furgoneta", "passenger van")):
        return "Van"
    if any(w in t for w in ("deportivo", "sport", "convertible", "cabrio")):
        return "Deportivo"
    if any(w in t for w in ("econó", "econom", "compact", "peque", "mini")):
        return "Económico"
    if any(w in t for w in ("median", "intermed", "estándar", "standard", "full size")):
        return "Mediano"
    if any(w in t for w in ("lujo", "luxury", "premium", "elite")):
        return "Lujo"
    return "Económico"


def clasificar_transmision(texto: str) -> str:
    t = texto.lower()
    if any(w in t for w in ("manual", "mecánic", "mecanic", "stick")):
        return "Manual"
    return "Automática"


def detectar_compania(texto: str, lineas: list) -> str:
    t = texto.lower()
    for key, nombre in EMPRESAS.items():
        if key in t:
            return nombre
    for ln in lineas:
        ln_s = ln.strip()
        if 2 < len(ln_s) < 40 and not re.search(r"[\$\d]", ln_s):
            return ln_s[:35]
    return "Proveedor UIO"


def parsear_rating(texto: str) -> tuple:
    rating, reviews = None, None
    m = RATING_RE.search(texto)
    if m:
        raw = m.group(1) or m.group(2)
        try:
            rating = float(raw.replace(",", "."))
        except (TypeError, ValueError):
            pass
    mr = REVIEWS_RE.search(texto)
    if mr:
        try:
            reviews = int(mr.group(1))
        except ValueError:
            pass
    return rating, reviews


def extraer_modelo(texto: str) -> str:
    m = MODELO_RE.search(texto)
    if m:
        return f"{m.group(1).title()} {m.group(2).strip()}"[:40]
    return ""


def fingerprint(fecha_alq: str, duracion: int, compania: str,
                categoria: str, transmision: str, precio_crudo: str) -> str:
    raw = f"{fecha_alq}|{duracion}|{compania}|{categoria}|{transmision}|{precio_crudo}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


# ──────────────────────────────────────────────────────────────────────────────
# PARSEO DE TARJETA
# ──────────────────────────────────────────────────────────────────────────────
def parsear_card(texto: str, dias: int) -> Optional[dict]:
    if not texto or len(texto) > 2000 or "$" not in texto:
        return None

    m = PRICE_RE.search(texto)
    if not m:
        return None
    precio_crudo = m.group(0)
    precio_total = limpiar_precio(m.group(1) or m.group(2))

    lineas = [l.strip() for l in texto.split("\n") if l.strip()]

    compania = detectar_compania(texto, lineas)
    modelo = extraer_modelo(texto)
    categoria = clasificar_categoria(texto)
    transmision = clasificar_transmision(texto)
    rating, reviews = parsear_rating(texto)

    cancelacion = bool(re.search(
        r"cancelaci[oó]n\s+gratis|free\s+cancellation|cancelaci[oó]n\s+flexible",
        texto, re.IGNORECASE,
    ))

    precio_dia = round(precio_total / dias, 2) if precio_total else None

    return {
        "compania": compania,
        "modelo": modelo,
        "categoria": categoria,
        "transmision": transmision,
        "precio_total": precio_total,
        "precio_dia": precio_dia,
        "precio_total_crudo": precio_crudo,
        "precio_faltante": 1 if precio_total is None else 0,
        "rating": rating,
        "reviews": reviews,
        "cancelacion_gratis": 1 if cancelacion else 0,
    }


# ──────────────────────────────────────────────────────────────────────────────
# NAVEGACIÓN
# ──────────────────────────────────────────────────────────────────────────────
async def _scroll_humano(page: Page, pasos: int = 6) -> None:
    for _ in range(pasos):
        delta = random.randint(400, 1200)
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(0.5, 1.2))


async def _cerrar_banners(page: Page) -> None:
    selectores = [
        'button:has-text("Aceptar")',
        'button:has-text("Accept")',
        'button:has-text("OK")',
        'button[aria-label*="close" i]',
        'button[aria-label*="cerrar" i]',
        '#onetrust-accept-btn-handler',
    ]
    for sel in selectores:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(timeout=2000)
                await asyncio.sleep(0.6)
        except Exception:
            continue


async def _detectar_bloqueo_real(page: Page) -> bool:
    """Solo bloquea si hay señal inequívoca Y no hay precios visibles."""
    try:
        content = (await page.content()).lower()
        señales = ["unusual traffic", "verifica que eres humano",
                   "are you a robot", "px-captcha", "please verify you are a human"]
        if not any(s in content for s in señales):
            return False
        try:
            precios = await page.query_selector_all("text=/\\$\\s*\\d/")
            if len(precios) > 3:
                return False
        except Exception:
            pass
        return True
    except Exception:
        return False


async def _navegar(page: Page, url: str) -> bool:
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            log.debug("GET intento %d/%d", intento, MAX_REINTENTOS)
            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
            await asyncio.sleep(random.uniform(*ESPERA_TRAS_CARGA))
            await _cerrar_banners(page)
            await _scroll_humano(page)
            if await _detectar_bloqueo_real(page):
                log.warning("🚨 CAPTCHA real detectado. Resuélvelo (3 min).")
                await asyncio.sleep(180)
                continue
            return True
        except PlaywrightTimeoutError:
            log.warning("Timeout (intento %d)", intento)
        except Exception as e:
            log.warning("Error navegando: %s", e)
        await asyncio.sleep(BACKOFF_BASE * intento + random.uniform(0, 2))
    return False


# ──────────────────────────────────────────────────────────────────────────────
# EXTRACCIÓN
# ──────────────────────────────────────────────────────────────────────────────
SEL_CANDIDATOS = [
    '[data-testid*="car"]',
    '[data-testid*="vehicle"]',
    '[data-testid*="result-card"]',
    'li[class*="car"]',
    'div[class*="CarCard"]',
    'div[class*="car-card"]',
    'div[class*="VehicleCard"]',
    'div[class*="vehicle-card"]',
    'div[class*="ResultCard"]',
    'div[class*="result-card"]',
    'article[class*="car"]',
    'div[class*="offer"]',
]


async def extraer_tarjetas(page: Page, fecha_alq: str, duracion: int) -> int:
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
        if len(textos) >= 8:
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
            if "$" in txt and 20 < len(txt) < 800:
                textos.append((txt, ""))

    if not textos:
        log.warning("Sin tarjetas para %dd", duracion)
        return 0

    log.info("%d tarjetas candidatas (%dd)", len(textos), duracion)

    vistos = set()
    guardados = 0
    fecha_consulta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for txt, href in textos:
        info = parsear_card(txt, duracion)
        if not info:
            continue

        fp = fingerprint(fecha_alq, duracion, info["compania"],
                         info["categoria"], info["transmision"],
                         info["precio_total_crudo"])
        if fp in vistos:
            continue
        vistos.add(fp)

        reg = Registro(
            fecha_consulta=fecha_consulta,
            fecha_alquiler=fecha_alq,
            duracion_dias=duracion,
            plataforma="Expedia",
            compania=info["compania"],
            modelo=info["modelo"],
            categoria=info["categoria"],
            transmision=info["transmision"],
            precio_total=info["precio_total"],
            precio_dia=info["precio_dia"],
            moneda="USD",
            precio_total_crudo=info["precio_total_crudo"],
            precio_faltante=info["precio_faltante"],
            precio_estimado_ia=None,
            fuente_precio="expedia",
            rating=info["rating"],
            reviews=info["reviews"],
            cancelacion_gratis=info["cancelacion_gratis"],
            url=href,
            fingerprint=fp,
        )
        if guardar_registro(reg):
            guardados += 1
            p = f"${info['precio_dia']:.2f}/d" if info["precio_dia"] else "?"
            log.info("  [+] %s │ %s │ %s │ %s │ %s",
                     info["compania"], info["categoria"],
                     info["transmision"][:3], info["precio_total_crudo"], p)

    log.info("%dd → %d registros", duracion, guardados)
    return guardados


# ──────────────────────────────────────────────────────────────────────────────
# FECHAS
# ──────────────────────────────────────────────────────────────────────────────
def parsear_fecha(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


# ──────────────────────────────────────────────────────────────────────────────
# SCRAPER PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────
async def scrapear_expedia(fecha_alq: datetime, duracion: int, page: Page) -> int:
    d1 = fecha_alq.strftime("%Y-%m-%d")
    d2 = (fecha_alq + timedelta(days=duracion)).strftime("%Y-%m-%d")
    date1 = fecha_alq.strftime("%m/%d/%Y")
    date2 = (fecha_alq + timedelta(days=duracion)).strftime("%m/%d/%Y")

    url = (
        "https://www.expedia.com/carsearch?"
        "locn=Quito%2C%20Ecuador%20(UIO-Mariscal%20Sucre%20Intl.)&"
        "pickupIATACode=UIO&olat=-0.124336&olon=-78.360908&dpln=5196117&"
        f"d1={d1}&d2={d2}&date1={date1}&date2={date2}&"
        "time1=1030AM&time2=1030AM&aarpcr=off&sort=RECOMMENDED_PRICE"
    )
    log.info("🚀 Expedia %s (%dd)", d1, duracion)
    if not await _navegar(page, url):
        return 0
    return await extraer_tarjetas(page, d1, duracion)


async def crear_contexto(pw) -> BrowserContext:
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    context = await pw.chromium.launch_persistent_context(
        USER_DATA_DIR,
        headless=HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--start-maximized",
        ],
        viewport=None if not HEADLESS else {"width": 1366, "height": 900},
        locale="es-EC",
        timezone_id="America/Guayaquil",
        user_agent=USER_AGENT,
        geolocation={"latitude": -0.1243, "longitude": -78.3602},
        permissions=["geolocation"],
        extra_http_headers={
            "Accept-Language": "es-EC,es;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    await context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome = { runtime: {} };"
    )
    return context


async def ejecutar(fechas: list, duraciones: list) -> None:
    init_db()
    total = 0
    async with async_playwright() as pw:
        context = await crear_contexto(pw)
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            for fecha in fechas:
                for dur in duraciones:
                    try:
                        n = await scrapear_expedia(fecha, dur, page)
                        total += n
                    except Exception as e:
                        log.exception("Error en %s/%dd: %s", fecha.date(), dur, e)
                    await asyncio.sleep(random.uniform(*ESPERA_ENTRE_HORIZONTES))
        finally:
            log.info("═══ TOTAL REGISTROS NUEVOS: %d ═══", total)
            try:
                await context.close()
            except Exception:
                pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Scraper Expedia — alquiler UIO")
    ap.add_argument("--fechas", required=True,
                    help="Fechas separadas por coma: 2026-12-31,2027-01-25")
    ap.add_argument("--duraciones", default="3,5,7,15,21,30",
                    help="Duraciones separadas por coma")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.verbose:
        for h in log.handlers:
            h.setLevel(logging.DEBUG)

    fechas = []
    for s in args.fechas.split(","):
        f = parsear_fecha(s)
        if f:
            fechas.append(f)
        else:
            log.error("Fecha inválida: %s", s)
            sys.exit(1)

    duraciones = [int(d.strip()) for d in args.duraciones.split(",") if d.strip()]

    log.info("Fechas: %s", [f.date().isoformat() for f in fechas])
    log.info("Duraciones: %s", duraciones)

    try:
        asyncio.run(ejecutar(fechas, duraciones))
    except KeyboardInterrupt:
        log.warning("Interrumpido por el usuario")


if __name__ == "__main__":
    main()
