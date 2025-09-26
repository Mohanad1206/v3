#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gaming Accessories Scraper — rooted, text output, hardened.
"""

import argparse, asyncio, os, sys, time, random, re, pathlib, datetime, logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

import httpx
from bs4 import BeautifulSoup
from selectolax.parser import HTMLParser
from tenacity import retry, stop_after_attempt, wait_fixed

try:
    import yaml
except Exception:
    yaml = None

# ---------- Root resolution ----------
def PROJECT_ROOT() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent
ROOT = PROJECT_ROOT()
(ROOT / "logs").mkdir(parents=True, exist_ok=True)
(ROOT / "output").mkdir(parents=True, exist_ok=True)

# ---------- Logging ----------
logging.basicConfig(
    filename=str(ROOT / "logs" / "scrape.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger().addHandler(console)

# ---------- Helpers ----------
PRICE_RE = re.compile(r"(EGP|ج\.م|LE|جنيه)\s*[\d,.]+|[\d,.]+\s*(EGP|ج\.م|LE|جنيه)", re.IGNORECASE)
CURRENCY_MAP = {"EGP": "EGP", "LE": "EGP", "ج.م": "EGP", "جنيه": "EGP"}
AVAIL_OK = re.compile(r"(in stock|available|متاح|متوفّر|مُتاح)", re.IGNORECASE)
AVAIL_NO = re.compile(r"(out of stock|sold out|غير متاح|نفدت الكمية|غير متوفر)", re.IGNORECASE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en,ar;q=0.9"
}

@dataclass
class Product:
    name: str
    url: str
    price_value: Optional[float]
    currency: Optional[str]
    raw_price_text: str
    status: str

def now_iso() -> str:
    return datetime.datetime.utcnow().isoformat()

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def parse_price(text: str):
    m = PRICE_RE.search(text or "")
    if not m:
        return None, None, ""
    raw = m.group(0)
    digits = re.sub(r"[^\d.]", "", raw.replace(",", ""))
    try:
        val = float(digits) if digits else None
    except:
        val = None
    curr = None
    for k,v in CURRENCY_MAP.items():
        if k.lower() in raw.lower():
            curr = v
            break
    if not curr:
        curr = "EGP"
    return val, curr, raw

def guess_availability(text: str) -> str:
    if AVAIL_NO.search(text or ""):
        return "Out of stock"
    if AVAIL_OK.search(text or ""):
        return "Available"
    return "Unknown"

def jitter(min_s=0.2, max_s=0.8):
    time.sleep(min_s + random.random() * (max_s - min_s))

def make_httpx_client(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers=HEADERS, follow_redirects=True)

@retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
def fetch_static(url: str) -> str:
    jitter()
    with make_httpx_client() as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text

async def fetch_dynamic(url: str, wait_ms: int = 1200) -> str:
    from playwright.async_api import async_playwright
    jitter()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(java_script_enabled=True, user_agent=HEADERS["User-Agent"])
        await page.goto(url, timeout=30000)
        await page.wait_for_timeout(wait_ms)
        html = await page.content()
        await browser.close()
        return html

def discover_product_links(base_url: str, html: str, include_paths: List[str]) -> List[str]:
    parser = HTMLParser(html)
    links = set()
    for a in parser.css("a"):
        href = a.attributes.get("href") or ""
        if not href or href.startswith("#") or href.startswith("tel:") or href.startswith("javascript:"):
            continue
        full = httpx.URL(base_url).join(href).human_repr()
        if include_paths and not any(p in full for p in include_paths):
            continue
        txt = (a.text() or "") + " " + (a.parent.text() if a.parent else "")
        if PRICE_RE.search(txt) or any(k in full.lower() for k in ["/product", "/products", "/item", "/p/", "/sku", "/collections", "/category"]):
            links.add(full)
    return list(links)

def extract_from_card(card) -> Optional[Product]:
    text = card.get_text(" ", strip=True)
    price_val, curr, raw_price = parse_price(text)
    a = card.find("a", href=True)
    url = a["href"] if a else ""
    name = a.get_text(strip=True) if a and a.get_text(strip=True) else ""
    if not name:
        h = card.find(["h1","h2","h3","h4","h5"])
        if h: name = h.get_text(strip=True)
    status = guess_availability(text)
    if not url and not name and not raw_price:
        return None
    return Product(name=norm_space(name), url=url, price_value=price_val, currency=curr, raw_price_text=raw_price, status=status)

def extract_products(html: str, base_url: str) -> List[Product]:
    soup = BeautifulSoup(html, "lxml")
    products: List[Product] = []
    selectors = [
        ".product-item", ".product", ".grid-product", ".card-product", ".product-card", ".product-grid-item",
        "li.product", "article.product", "div[class*=product]", "div[class*=card]"
    ]
    for sel in selectors:
        for card in soup.select(sel):
            p = extract_from_card(card)
            if p:
                if p.url:
                    p.url = httpx.URL(base_url).join(p.url).human_repr()
                products.append(p)
    if not products:
        for a in soup.find_all("a", href=True):
            context = a.get_text(" ", strip=True) + " " + (a.find_parent().get_text(" ", strip=True) if a.find_parent() else "")
            if PRICE_RE.search(context):
                url = httpx.URL(base_url).join(a["href"]).human_repr()
                name = a.get_text(strip=True) or "N/A"
                pv, curr, raw = parse_price(context)
                status = guess_availability(context)
                products.append(Product(name=norm_space(name), url=url, price_value=pv, currency=curr, raw_price_text=raw, status=status))
    uniq = {}
    for p in products:
        key = p.url or p.name
        if key and key not in uniq:
            uniq[key] = p
    final = []
    for p in uniq.values():
        if p.price_value and not p.currency:
            p.currency = "EGP"
        final.append(p)
    return final

def load_config(path="config.yaml") -> Dict[str, dict]:
    if yaml is None:
        return {}
    fp = ROOT / path
    if not fp.exists():
        return {}
    with open(fp, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    out = {}
    for item in (data.get("sites") or []):
        host = (item.get("host") or "").replace("www.", "").strip()
        if host:
            out[host] = item
    return {"cfg_by_host": out, "defaults": data.get("defaults", {})}

def host_of(url: str) -> str:
    try:
        return httpx.URL(url).host.replace("www.", "")
    except Exception:
        return ""

async def fetch_html(url: str, mode: str) -> str:
    try:
        if mode == "static":
            return fetch_static(url)
        elif mode == "always":
            return await fetch_dynamic(url)
        elif mode == "auto":
            html = ""
            try:
                html = fetch_static(url)
            except Exception as e:
                logging.info(f"Static fetch failed for {url}: {e}. Falling back to dynamic.")
                return await fetch_dynamic(url)
            if len(html) < 30000 or not PRICE_RE.search(html):
                try:
                    logging.info(f"Static content seems thin/no-price for {url}; trying dynamic.")
                    dyn = await fetch_dynamic(url)
                    if len(dyn) > len(html):
                        return dyn
                except Exception as e:
                    logging.info(f"Dynamic fetch failed for {url}: {e}. Keeping static.")
            return html
        else:
            return fetch_static(url)
    except Exception as e:
        logging.error(f"Fetch failed for {url}: {e}")
        return ""

async def process_site(url: str, args, cfg_by_host: Dict[str, dict], out_fp):
    base_host = host_of(url)
    cfg = (cfg_by_host or {}).get(base_host, {})
    include_paths = cfg.get("include_paths", []) if cfg else []
    mode = "static" if args.static_only else ("always" if args.dynamic == "always" else "auto")

    logging.info(f"[{base_host}] Fetching ({mode}) → {url}")
    html = await fetch_html(url, mode)
    if not html:
        logging.warning(f"[{base_host}] Empty HTML")
        return

    candidates = discover_product_links(url, html, include_paths) or [url]
    collected = 0
    for link in candidates[: args.first_n]:
        html2 = await fetch_html(link, mode)
        if not html2:
            continue
        products = extract_products(html2, link)
        for p in products:
            line = " | ".join([
                now_iso(),
                base_host or "unknown",
                p.name or "N/A",
                p.status or "Unknown",
                f"{p.price_value:.2f}" if p.price_value is not None else "N/A",
                p.currency or "N/A",
                p.url or link,
                p.raw_price_text or "N/A",
            ])
            out_fp.write(line + "\n")
            collected += 1
        if collected >= args.first_n:
            break
    logging.info(f"[{base_host}] Wrote {collected} products")

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=str, default=None, help="Relative to project root (default config)")
    ap.add_argument("--out-dir", type=str, default=None, help="Relative to project root (default config)")
    ap.add_argument("--first-n", type=int, default=None, help="Max products per site")
    ap.add_argument("--dynamic", type=str, default=None, choices=["auto", "always"], help="Dynamic rendering behavior")
    ap.add_argument("--static-only", action="store_true", help="Force static only (no Playwright)")
    return ap.parse_args()

async def main():
    args = parse_args()
    cfg = load_config("config.yaml")
    cfg_by_host = (cfg or {}).get("cfg_by_host", {})
    defaults = (cfg or {}).get("defaults", {})

    sites_file = args.sites or defaults.get("sites_file", "sites.txt")
    out_dir_rel = args.out_dir or defaults.get("out_dir", "output")
    first_n = args.first_n or int(os.getenv("SCRAPER_FIRST_N", defaults.get("first_n", 50)))
    dynamic = args.dynamic or os.getenv("SCRAPER_DYNAMIC", defaults.get("dynamic", "auto"))
    static_only = args.static_only

    sites_path = ROOT / sites_file
    out_dir = ROOT / out_dir_rel
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{ts}_scrape.txt"

    with open(sites_path, "r", encoding="utf-8") as f:
        urls = [u.strip() for u in f if u.strip() and not u.strip().startswith("#")]

    with open(out_path, "w", encoding="utf-8") as out_fp:
        out_fp.write("timestamp_iso | site_name | product_name | status | price_value | currency | product_url | raw_price_text\n")
        for url in urls:
            try:
                await process_site(url, argparse.Namespace(
                    static_only=static_only,
                    dynamic=dynamic,
                    first_n=first_n
                ), cfg_by_host, out_fp)
            except Exception as e:
                logging.exception(f"Unhandled error for {url}: {e}")
    print(f"Wrote text output to: {out_path}")
