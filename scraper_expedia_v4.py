#!/usr/bin/env python3
"""scraper_expedia_v4.py — Selectores específicos para tarjetas reales."""
from __future__ import annotations

import argparse, asyncio, hashlib, logging, logging.handlers
import os, random, re, sqlite3, sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PWTimeout

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
LOG_PATH = os.path.join(BASE_DIR, "scraper_expedia_v4.log")
USER_DATA_DIR = os.path.join(BASE_DIR, "chrome_session_expedia")

HEADLESS = os.getenv("SCRAPER_HEADLESS", "0") == "1"
MAX_REINTENTOS = 3
TIMEOUT_NAV = 90_000

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

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
}

# Términos que indican que NO es una tarjeta de oferta
BASURA = {
    "popular filters", "free cancellation", "pick-up at airport",
    "6 or more passengers", "from", "see more", "show more",
    "total price", "price", "capacity", "payment option",
    "specifications", "cancellation policy", "traveler ratings",
    "airport pick-up", "save time", "exclusive offers", "great deal",
    "includes taxes", "popular", "filters", "sort by", "recommended",
}


class ColorFormatter(logging.Formatter):
    COLORS = {"DEBUG": "\033[36m", "INFO": "\033[92m", "WARNING": "\033[93m",
              "ERROR": "\033[91m", "CRITICAL": "\033[95m"}
    RESET = "\033[0m"
    def format(self, r):
        c = self.COLORS.get(r.levelname, "")
        return f"{c}{super().format(r)}{self.RESET}"


def setup_logging(verbose=False):
    logger = logging.getLogger("scraper_v4")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = "%(asctime)s │ %(levelname)-7s │ %(message)s"
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(ColorFormatter(fmt, datefmt="%H:%M:%S"))
    logger.addHandler(ch)
    fh = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=5_000_000,
                                                backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
    logger.addHandler(fh)
    return logger


log = setup_logging()


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

    def to_row(self):
        d = asdict(self)
        keys = ["fecha_consulta","fecha_alquiler","duracion_dias","plataforma",
                "compania","modelo","categoria","transmision","precio_total",
                "precio_dia","moneda","precio_total_crudo","precio_faltante",
                "precio_estimado_ia","fuente_precio","rating","reviews",
                "cancelacion_gratis","url","fingerprint"]
        return tuple(d[k] for k in keys)


SCHEMA = """
CREATE TABLE IF NOT EXISTS historial_precios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_consulta TEXT NOT NULL, fecha_alquiler TEXT NOT NULL,
    duracion_dias INTEGER NOT NULL, plataforma TEXT NOT NULL,
    compania TEXT, modelo TEXT, categoria TEXT, transmision TEXT,
    precio_total REAL, precio_dia REAL, moneda TEXT DEFAULT 'USD',
    precio_total_crudo TEXT, precio_faltante INTEGER DEFAULT 0,
    precio_estimado_ia REAL, fuente_precio TEXT DEFAULT 'expedia',
    rating REAL, reviews INTEGER, cancelacion_gratis INTEGER DEFAULT 0,
    url TEXT, fingerprint TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_fecha_alq ON historial_precios(fecha_alquiler);
CREATE INDEX IF NOT EXISTS idx_duracion ON historial_precios(duracion_dias);
CREATE INDEX IF NOT EXISTS idx_compania ON historial_precios(compania);
"""

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


def init_db():
    with _connect() as c:
        for s in SCHEMA.strip().split(";"):
            if s.strip():
                c.execute(s)
        c.commit()
    log.info("DB lista: %s", DB_PATH)


def guardar(r):
    try:
        with _connect() as c:
            cur = c.execute(INSERT_SQL, r.to_row())
            c.commit()
            return cur.rowcount > 0
    except sqlite3.Error as e:
        log.error("DB: %s", e)
        return False


PRICE_RE = re.compile(r"\$\s*([\d.,]+)|\b([\d.,]+)\s*\$")
RATING_RE = re.compile(r"(\d+[.,]\d)\s*(?:/|de)\s*5|(\d+[.,]\d)\s*★")
REVIEWS_RE = re.compile(r"\((\d{2,6})\)")
MODELO_RE = re.compile(
    r"\b(Toyota|Chevrolet|Hyundai|Kia|Nissan|Mazda|Renault|Ford|Volkswagen|VW|"
    r"Mitsubishi|Suzuki|Honda|Peugeot|Citro[eë]n|Fiat|Jeep|BMW|Mercedes|"
    r"Audi|Subaru|Chery|Great Wall|Haval|JAC|Dongfeng|BYD)\s+([A-Za-z0-9\- ]{2,25})",
    re.IGNORECASE)


def limpiar_precio(raw):
    if not raw: return None
    s = re.sub(r"[^\d.,]", "", raw.replace(" ", "").replace("\u00a0", ""))
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
        return "SUV Lujo" if any(w in t for w in ("lujo","luxury","premium")) else "SUV"
    if any(w in t for w in ("pickup","pick-up")): return "Pickup"
    if any(w in t for w in ("van","minivan","furgoneta")): return "Van"
    if any(w in t for w in ("deportivo","sport","convertible")): return "Deportivo"
    if any(w in t for w in ("econó","econom","compact","peque","mini")): return "Económico"
    if any(w in t for w in ("median","intermed","estándar","standard","full size")): return "Mediano"
    if any(w in t for w in ("lujo","luxury","premium","elite")): return "Lujo"
    return "Económico"


def clasificar_transmision(t):
    t = t.lower()
    if any(w in t for w in ("manual","mecánic","mecanic","stick")): return "Manual"
    return "Automática"


def detectar_compania(texto):
    if not texto: return None
    t = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", texto.lower())).strip()
    for nombre, variantes in VARIANTES.items():
        for v in variantes:
            if re.search(r"\b" + re.escape(v) + r"\b", t):
                return nombre
    return None


def parsear_rating(texto):
    r, rev = None, None
    m = RATING_RE.search(texto)
    if m:
        try: r = float((m.group(1) or m.group(2)).replace(",", "."))
        except: pass
    mr = REVIEWS_RE.search(texto)
    if mr:
        try: rev = int(mr.group(1))
        except: pass
    return r, rev


def extraer_modelo(texto):
    m = MODELO_RE.search(texto)
    return f"{m.group(1).title()} {m.group(2).strip()}"[:40] if m else ""


def fingerprint(fecha, dur, comp, cat, trans, precio):
    raw = f"{fecha}|{dur}|{comp}|{cat}|{trans}|{precio}"
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def es_basura(texto):
    """Detecta si el texto es un panel de filtros o basura similar."""
    t = texto.lower()[:300]
    # Si contiene 2+ términos de basura, es basura
    hits = sum(1 for b in BASURA if b in t)
    return hits >= 2


def parsear_card(texto, dias):
    if not texto or len(texto) > 2000 or "$" not in texto:
        return None

    # 1. Filtrar basura primero
    if es_basura(texto):
        return None

    # 2. Detectar compañía
    compania = detectar_compania(texto)
    if not compania:
        return None

    # 3. Extraer precio
    m = PRICE_RE.search(texto)
    if not m:
        return None
    precio_crudo = m.group(0)
    precio_total = limpiar_precio(m.group(1) or m.group(2))

    categoria = clasificar_categoria(texto)
    transmision = clasificar_transmision(texto)
    modelo = extraer_modelo(texto)
    rating, reviews = parsear_rating(texto)
    cancelacion = bool(re.search(r"cancelaci[oó]n\s+gratis|free\s+cancellation",
                                   texto, re.IGNORECASE))
    precio_dia = round(precio_total / dias, 2) if precio_total else None

    return {
        "compania": compania, "modelo": modelo, "categoria": categoria,
        "transmision": transmision, "precio_total": precio_total,
        "precio_dia": precio_dia, "precio_total_crudo": precio_crudo,
        "precio_faltante": 1 if precio_total is None else 0,
        "rating": rating, "reviews": reviews,
        "cancelacion_gratis": 1 if cancelacion else 0,
    }


async def _scroll(page, pasos=8):
    for _ in range(pasos):
        await page.mouse.wheel(0, random.randint(400, 1200))
        await asyncio.sleep(random.uniform(0.5, 1.2))


async def _cerrar_banners(page):
    for sel in ['button:has-text("Aceptar")', 'button:has-text("Accept")',
                'button[aria-label*="close" i]', '#onetrust-accept-btn-handler']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(timeout=2000)
                await asyncio.sleep(0.6)
        except: continue


async def _navegar(page, url):
    for i in range(1, MAX_REINTENTOS + 1):
        try:
            log.debug("GET %d/%d", i, MAX_REINTENTOS)
            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
            await asyncio.sleep(random.uniform(5, 9))
            await _cerrar_banners(page)
            await _scroll(page)
            return True
        except PWTimeout:
            log.warning("Timeout %d", i)
        except Exception as e:
            log.warning("Error: %s", e)
        await asyncio.sleep(4 * i + random.uniform(0, 2))
    return False


# ── SELECTORES ESPECÍFICOS DE TARJETAS DE OFERTAS ──────────────────────────
# Ordenados de más específico a más genérico. Evitan paneles de filtros.
SEL_TARJETAS = [
    '[data-testid="car-result-card"]',
    '[data-testid="vehicle-result"]',
    '[data-testid*="car-card"]',
    '[data-testid*="carResult"]',
    '[data-stid*="car-result"]',
    '[data-stid="lodging-card-responsive"]',  # a veces Expedia reusa esto
    'li[data-testid*="result"]',
    'div[data-testid*="result-card"]',
    'div[class*="uitk-card"][class*="car"]',
    'div[class*="CarResult"]',
    'div[class*="car-result"]',
    'article[data-testid]',
    'li[class*="result-card"]',
    'div[role="group"][class*="card"]',
]


async def extraer_tarjetas(page, fecha, dur):
    textos = []
    for sel in SEL_TARJETAS:
        try:
            els = await page.query_selector_all(sel)
        except Exception:
            continue
        for el in els:
            try:
                txt = (await el.inner_text()) or ""
            except Exception:
                continue
            if "$" in txt and 30 < len(txt) < 2000:
                href = ""
                try:
                    a = await el.query_selector("a[href]")
                    if a:
                        href = (await a.get_attribute("href")) or ""
                except: pass
                textos.append((txt, href))
        if len(textos) >= 15:
            break

    if not textos:
        log.warning("Sin tarjetas visibles (%dd)", dur)
        return 0

    log.info("%d tarjetas (%dd)", len(textos), dur)

    vistos = set()
    guardados = 0
    descartados = 0
    basura = 0
    fecha_consulta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for txt, href in textos:
        if es_basura(txt):
            basura += 1
            continue

        info = parsear_card(txt, dur)
        if not info:
            descartados += 1
            if descartados <= 2:
                log.warning("  🔍 DESCARTADA: %s", txt[:150].replace("\n", " | "))
            continue

        fp = fingerprint(fecha, dur, info["compania"], info["categoria"],
                         info["transmision"], info["precio_total_crudo"])
        if fp in vistos: continue
        vistos.add(fp)

        reg = Registro(
            fecha_consulta=fecha_consulta, fecha_alquiler=fecha, duracion_dias=dur,
            plataforma="Expedia", compania=info["compania"], modelo=info["modelo"],
            categoria=info["categoria"], transmision=info["transmision"],
            precio_total=info["precio_total"], precio_dia=info["precio_dia"],
            moneda="USD", precio_total_crudo=info["precio_total_crudo"],
            precio_faltante=info["precio_faltante"], precio_estimado_ia=None,
            fuente_precio="expedia", rating=info["rating"], reviews=info["reviews"],
            cancelacion_gratis=info["cancelacion_gratis"], url=href, fingerprint=fp)

        if guardar(reg):
            guardados += 1
            p = f"${info['precio_dia']:.2f}/d" if info["precio_dia"] else "?"
            log.info("  [+] %s │ %s │ %s │ %s │ %s", info["compania"],
                     info["categoria"], info["transmision"][:3],
                     info["precio_total_crudo"], p)

    log.info("%dd → %d guardados, %d descartados, %d basura filtrada",
             dur, guardados, descartados, basura)
    return guardados


def parsear_fecha(s):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try: return datetime.strptime(s.strip(), fmt)
        except ValueError: continue
    return None


async def scrapear(fecha, dur, page):
    d1 = fecha.strftime("%Y-%m-%d")
    d2 = (fecha + timedelta(days=dur)).strftime("%Y-%m-%d")
    date1 = fecha.strftime("%m/%d/%Y")
    date2 = (fecha + timedelta(days=dur)).strftime("%m/%d/%Y")
    url = ("https://www.expedia.com/carsearch?"
           "locn=Quito%2C%20Ecuador%20(UIO-Mariscal%20Sucre%20Intl.)&"
           "pickupIATACode=UIO&olat=-0.124336&olon=-78.360908&dpln=5196117&"
           f"d1={d1}&d2={d2}&date1={date1}&date2={date2}&"
           "time1=1030AM&time2=1030AM&aarpcr=off&sort=RECOMMENDED_PRICE")
    log.info("🚀 Expedia %s (%dd)", d1, dur)
    if not await _navegar(page, url): return 0
    return await extraer_tarjetas(page, d1, dur)


async def crear_contexto(pw):
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    ctx = await pw.chromium.launch_persistent_context(
        USER_DATA_DIR, headless=HEADLESS,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
              "--disable-dev-shm-usage", "--start-maximized",
              "--ozone-platform=x11"],  # fix wayland
        viewport=None if not HEADLESS else {"width": 1366, "height": 900},
        locale="es-EC", timezone_id="America/Guayaquil",
        user_agent=USER_AGENT,
        geolocation={"latitude": -0.1243, "longitude": -78.3602},
        permissions=["geolocation"],
        extra_http_headers={
            "Accept-Language": "es-EC,es;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    await ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome = { runtime: {} };")
    return ctx


async def ejecutar(fechas, duraciones):
    init_db()
    total = 0
    async with async_playwright() as pw:
        ctx = await crear_contexto(pw)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            for fecha in fechas:
                for dur in duraciones:
                    try:
                        total += await scrapear(fecha, dur, page)
                    except Exception as e:
                        log.exception("Error %s/%dd: %s", fecha.date(), dur, e)
                    await asyncio.sleep(random.uniform(3, 6))
        finally:
            log.info("═══ TOTAL: %d ═══", total)
            try: await ctx.close()
            except: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fechas", required=True)
    ap.add_argument("--duraciones", default="3,5,7,15,21,30")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.verbose:
        for h in log.handlers: h.setLevel(logging.DEBUG)

    fechas = [parsear_fecha(s) for s in args.fechas.split(",")]
    fechas = [f for f in fechas if f]
    if not fechas:
        log.error("Fechas inválidas"); sys.exit(1)

    duraciones = [int(d.strip()) for d in args.duraciones.split(",") if d.strip()]
    log.info("Fechas: %s", [f.date().isoformat() for f in fechas])
    log.info("Duraciones: %s", duraciones)

    try:
        asyncio.run(ejecutar(fechas, duraciones))
    except KeyboardInterrupt:
        log.warning("Interrumpido")


if __name__ == "__main__":
    main()
