#!/usr/bin/env python3
"""scraper_expedia_v6.py — Firefox real + detección CAPTCHA + monitorización humana."""
from __future__ import annotations

import argparse, asyncio, hashlib, json, logging, logging.handlers
import os, random, re, sqlite3, sys, subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PWTimeout

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "precios_competencia.db")
LOG_PATH = os.path.join(BASE_DIR, "scraper_expedia_v6.log")
USER_DATA_DIR = os.path.join(BASE_DIR, "firefox_session_expedia")

HEADLESS = os.getenv("SCRAPER_HEADLESS", "0") == "1"
MAX_REINTENTOS = 3
TIMEOUT_NAV = 120_000
ESPERA_JS = 45

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


class ColorFormatter(logging.Formatter):
    COLORS = {"DEBUG": "\033[36m", "INFO": "\033[92m", "WARNING": "\033[93m",
              "ERROR": "\033[91m", "CRITICAL": "\033[95m"}
    RESET = "\033[0m"
    def format(self, r):
        c = self.COLORS.get(r.levelname, "")
        return f"{c}{super().format(r)}{self.RESET}"


def setup_logging(verbose=False):
    lg = logging.getLogger("scraper_v6")
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


def beep(n=3):
    """Aviso sonoro para que te enteres aunque no estés mirando."""
    for _ in range(n):
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass


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
    if any(w in t for w in ("suv","todoterreno","4x4","crossover")):
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
    return "Manual" if any(w in t for w in ("manual","mecánic","mecanic","stick")) else "Automática"


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


# ═══════════════════════════════════════════════════════════════
#  DETECCIÓN DE CAPTCHA / BLOQUEO
# ═══════════════════════════════════════════════════════════════

async def hay_captcha(page: Page) -> bool:
    """Detecta si Expedia/Akamai nos está mostrando un CAPTCHA o challenge."""
    try:
        html = (await page.content())[:15000].lower()
        titulo = (await page.title()).lower()
        url = page.url.lower()

        señales = [
            "captcha" in html,
            "challenge" in html,
            "verify you are human" in html,
            "are you a robot" in html,
            "px-captcha" in html,
            "akamai" in html and "challenge" in html,
            "wildcard-challenge" in html,
            "unusual traffic" in html,
            "access denied" in html,
            "captcha" in titulo,
            "challenge" in titulo,
            "captcha" in url,
        ]
        return any(señales)
    except Exception:
        return False


async def esperar_captcha_resuelto(page: Page, max_min=10):
    """
    Pausa el script y espera a que TÚ resuelvas el CAPTCHA manualmente.
    Detecta automáticamente cuándo desaparece.
    """
    log.warning("=" * 60)
    log.warning("🚨 CAPTCHA / BLOQUEO DETECTADO 🚨")
    log.warning("=" * 60)
    log.warning("👉 Ve a la ventana de Firefox y resuélvelo manualmente.")
    log.warning("👉 El script esperará hasta %d minutos.", max_min)
    log.warning("👉 Cuando la página de Expedia cargue normal, seguirá solo.")
    log.warning("=" * 60)
    beep(5)

    for minuto in range(max_min * 6):  # chequea cada 10 seg
        await asyncio.sleep(10)
        if not await hay_captcha(page):
            log.info("✅ CAPTCHA resuelto. Continuando en 5s...")
            beep(2)
            await asyncio.sleep(5)
            return True
        if minuto % 6 == 0 and minuto > 0:
            log.warning("⏳ Aún esperando... (%d min transcurridos)", minuto // 6)

    log.error("❌ CAPTCHA no resuelto en %d minutos. Abortando esta URL.", max_min)
    beep(5)
    return False


# ═══════════════════════════════════════════════════════════════
#  EXTRACCIÓN
# ═══════════════════════════════════════════════════════════════

async def extraer_con_js(page, fecha, dur):
    tarjetas = await page.evaluate("""
        () => {
            const resultados = [];
            const selecciones = [
                '[data-stid*="car"]',
                '[data-testid*="car"]',
                'div[class*="uitk-card"]',
                'div[class*="result-card"]',
                'li[class*="result"]',
                'article',
                'div[role="button"]',
                'button[data-stid]',
            ];
            const vistos = new Set();
            for (const sel of selecciones) {
                try {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const txt = el.innerText || '';
                        if (txt.includes('$') && txt.length > 30 && txt.length < 3000) {
                            const hash = txt.slice(0, 100);
                            if (!vistos.has(hash)) {
                                vistos.add(hash);
                                resultados.push({
                                    texto: txt,
                                    url: el.querySelector('a')?.href || ''
                                });
                            }
                        }
                    }
                } catch(e) {}
            }
            return resultados;
        }
    """)
    return tarjetas


async def _cerrar_banners(page):
    for sel in ['button:has-text("Aceptar")', 'button:has-text("Accept")',
                'button[aria-label*="close" i]', '#onetrust-accept-btn-handler']:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click(timeout=2000)
                await asyncio.sleep(0.5)
        except: continue


async def _navegar(page, url):
    for i in range(1, MAX_REINTENTOS + 1):
        try:
            log.debug("GET %d/%d", i, MAX_REINTENTOS)
            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)

            # 🔴 Chequeo temprano de CAPTCHA
            await asyncio.sleep(3)
            if await hay_captcha(page):
                if not await esperar_captcha_resuelto(page):
                    return False

            log.info("⏳ Esperando %ds a que Expedia cargue JS...", ESPERA_JS)
            await asyncio.sleep(ESPERA_JS)

            # 🔴 Segundo chequeo después de la espera
            if await hay_captcha(page):
                if not await esperar_captcha_resuelto(page):
                    return False

            await _cerrar_banners(page)

            # Scroll aleatorio (más humano)
            log.info("🖱️  Scroll humano...")
            for _ in range(15):
                await page.mouse.wheel(0, random.randint(600, 1200))
                await asyncio.sleep(random.uniform(0.4, 1.2))
            await asyncio.sleep(3)
            return True
        except PWTimeout:
            log.warning("Timeout %d", i)
        except Exception as e:
            log.warning("Error: %s", e)
        await asyncio.sleep(5 * i)
    return False


async def extraer_tarjetas(page, fecha, dur):
    tarjetas = await extraer_con_js(page, fecha, dur)
    log.info("%d tarjetas crudas vía JS (%dd)", len(tarjetas), dur)

    if not tarjetas:
        # ¿Es porque hay CAPTCHA o porque no hay coches?
        if await hay_captcha(page):
            log.warning("⚠️  0 tarjetas porque hay CAPTCHA")
        else:
            log.warning("⚠️  0 tarjetas — puede que no haya disponibilidad")
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

        fp = fingerprint(fecha, dur, compania, categoria, transmision, precio_crudo)
        if fp in vistos: continue
        vistos.add(fp)

        reg = Registro(
            fecha_consulta=fecha_consulta, fecha_alquiler=fecha, duracion_dias=dur,
            plataforma="Expedia", compania=compania, modelo="",
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
            log.info("  [+] %s │ %s │ %s │ %s │ %s",
                     compania, categoria, transmision[:3], precio_crudo, p)

    log.info("%dd → %d guardados", dur, guardados)
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


async def crear_contexto_firefox(pw):
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    ctx = await pw.firefox.launch_persistent_context(
        USER_DATA_DIR, headless=HEADLESS,
        viewport=None if not HEADLESS else {"width": 1366, "height": 900},
        locale="es-EC", timezone_id="America/Guayaquil",
        user_agent=("Mozilla/5.0 (X11; Linux x86_64; rv:133.0) "
                    "Gecko/20100101 Firefox/133.0"),
        geolocation={"latitude": -0.1243, "longitude": -78.3602},
        permissions=["geolocation"],
        extra_http_headers={
            "Accept-Language": "es-EC,es;q=0.9,en;q=0.8",
        })
    return ctx


async def ejecutar(fechas, duraciones):
    init_db()
    total = 0
    async with async_playwright() as pw:
        ctx = await crear_contexto_firefox(pw)
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
