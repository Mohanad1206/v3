
import { program } from "commander";
import { chromium } from "playwright";
import pLimit from "p-limit";
import fs from "fs";
import { domainFromUrl, extractNumber, normalizeCurrency, nowIso, sleep } from "./util.js";
import { parseJsonLdProducts } from "./jsonld.js";

const selectorsConfig = JSON.parse(fs.readFileSync(new URL("../config/domain-selectors.json", import.meta.url), "utf-8"));

program

// Webhook options
program
  .option("--webhook <url>", "Webhook URL to POST results (Make.com custom webhook)")
  .option("--webhook-mode <mode>", "line | batch (default: none)", "none")
  .option("--webhook-headers <json>", "Extra headers as JSON string", "{}");

  .requiredOption("--in <file>", "Path to input file containing one URL per line")
  .option("--out <file>", "Path to output .ndjson (default: out/results.ndjson)", "out/results.ndjson")
  .option("--concurrency <n>", "Max concurrent pages", "3")
  .option("--max <n>", "Max products per URL", "50")
  .option("--timeout <ms>", "Navigation timeout in ms", "45000")
  .option("--headful", "Run with a visible browser", false)
  .option("--delay <ms>", "Delay between requests (per page) in ms", "750")
  .parse(process.argv);

const opts = program.opts();
const WEBHOOK = opts.webhook || process.env.MAKE_WEBHOOK_URL || null;
const WEBHOOK_MODE = (opts.webhookMode || 'none').toLowerCase();
let webhookHeaders = {};
try { webhookHeaders = JSON.parse(opts.webhookHeaders || '{}'); } catch { webhookHeaders = {}; }
const IN = opts.in;
const OUT = opts.out;
const CONC = Math.max(1, parseInt(opts.concurrency));
const LIMIT = Math.max(1, parseInt(opts.max));
const TIMEOUT = Math.max(1000, parseInt(opts.timeout));
const HEADFUL = !!opts.headful;
const DELAY = Math.max(0, parseInt(opts.delay));

const inputUrls = fs.readFileSync(IN, "utf-8").split(/\r?\n/).map(s => s.trim()).filter(Boolean);
fs.mkdirSync("out", { recursive: true });
const outStream = fs.createWriteStream(OUT, { flags: "w", encoding: "utf-8" });
const batchItems = [];

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118 Safari/537.36";
const contextOptions = {
  userAgent: UA,
  viewport: { width: 1366, height: 768 },
};

function getSelectorsFor(url) {
  const host = domainFromUrl(url);
  return selectorsConfig[host] || selectorsConfig["default"];
}

async function extractWithSelectors(page, baseUrl, selectors, limit) {
  // find product listing links first; then visit each product (if listing page), else treat as product page
  const products = new Set();
  for (const sel of selectors.product_list || []) {
    try {
      const anchors = await page.$$eval(sel, nodes => nodes.map(n => n.getAttribute("href")).filter(Boolean));
      for (let href of anchors) {
        try {
          const u = new URL(href, baseUrl).toString();
          products.add(u);
          if (products.size >= limit) break;
        } catch {}
      }
      if (products.size >= limit) break;
    } catch {}
  }
  // If no product links found, try to treat the URL itself as a product page
  if (products.size === 0) products.add(baseUrl);

  const out = [];
  for (const url of Array.from(products).slice(0, limit)) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: TIMEOUT });
      // wait for possible dynamic price/name
      await page.waitForTimeout(1200);
      // JSON-LD pass
      const html = await page.content();
      const jsonld = parseJsonLdProducts(html).map(p => ({ ...p, source_url: url }));
      if (jsonld.length > 0) {
        jsonld.forEach(p => out.push(p));
        continue; // prefer JSON-LD when available
      }
      // Selector-based extraction
      const name = await firstText(page, selectors.name);
      const priceText = await firstText(page, selectors.price);
      const availRaw = await firstText(page, selectors.availability);
      const item = {
        timestamp_iso: nowIso(),
        site_name: domainFromUrl(url),
        product_name: name || null,
        sku: null,
        product_url: url,
        status: availRaw || null,
        price_value: extractNumber(priceText),
        currency: normalizeCurrency(priceText) || "EGP",
        raw_price_text: priceText || null,
        source_url: baseUrl,
        notes: "selectors"
      };
      out.push(item);
      await sleep(200);
    } catch (err) {
      out.push({
        timestamp_iso: nowIso(),
        site_name: domainFromUrl(url),
        product_name: null,
        sku: null,
        product_url: url,
        status: "error",
        price_value: null,
        currency: null,
        raw_price_text: null,
        source_url: baseUrl,
        notes: `error: ${err?.message || String(err)}`
      });
    }
  }
  return out;
}

async function firstText(page, selectors) {
  if (!selectors) return null;
  for (const sel of selectors) {
    try {
      if (sel.endsWith("::attr(content)")) {
        const css = sel.replace("::attr(content)", "");
        const v = await page.$eval(css, el => el.getAttribute("content"));
        if (v && v.trim()) return v.trim();
      } else {
        const v = await page.$eval(sel, el => (el.innerText || el.textContent || "").trim());
        if (v && v.trim()) return v.trim();
      }
    } catch {}
  }
  return null;
}

(async () => {
  const browser = await chromium.launch({ headless: !HEADFUL });
  const limit = pLimit(CONC);
  const context = await browser.newContext(contextOptions);

  try {
    await Promise.all(inputUrls.map((url, idx) => limit(async () => {
      const page = await context.newPage();
      page.setDefaultTimeout(TIMEOUT);
      // basic stealth-ish & resource blocking
      await page.route("**/*", (route) => {
        const req = route.request();
        const type = req.resourceType();
        if (["image", "media", "font"].includes(type)) return route.abort();
        route.continue();
      });
      try {
        await page.goto(url, { waitUntil: "domcontentloaded", timeout: TIMEOUT });
        // give SPA time to render listings
        await page.waitForLoadState("networkidle", { timeout: TIMEOUT }).catch(() => {});
        await page.waitForTimeout(1000);
        const sels = getSelectorsFor(url);
        const items = await extractWithSelectors(page, url, sels, LIMIT);
        for (const it of items) {
          const line = JSON.stringify(it, ensureJsonSafe);
outStream.write(line + "\n");
if (WEBHOOK && WEBHOOK_MODE === 'line') {
  await postJson(WEBHOOK, it, webhookHeaders).catch(()=>{});
}
batchItems.push(it);
        }
      } catch (e) {
        const __errObj = {
          timestamp_iso: nowIso(),
          site_name: domainFromUrl(url),
          product_name: null,
          sku: null,
          product_url: url,
          status: "error",
          price_value: null,
          currency: null,
          raw_price_text: null,
          source_url: url,
          notes: `top-level error: ${e?.message || String(e)}`
        };
const __line = JSON.stringify(__errObj, ensureJsonSafe);
outStream.write(__line + "\n");
if (WEBHOOK && WEBHOOK_MODE === 'line') { await postJson(WEBHOOK, __errObj, webhookHeaders).catch(()=>{}); }
batchItems.push(__errObj);
      } finally {
        await page.close().catch(()=>{});
      }
      await sleep(DELAY);
    })));
  } finally {
    await context.close().catch(()=>{});
    await browser.close().catch(()=>{});

    outStream.end();
    if (WEBHOOK && WEBHOOK_MODE === 'batch') {
      await postJson(WEBHOOK, { items: batchItems }, webhookHeaders).catch(()=>{});
    }
  }
})();



async function postJson(url, body, headers = {}) {
  const h = { "Content-Type": "application/json", ...headers };
  try {
    const res = await fetch(url, { method: "POST", headers: h, body: JSON.stringify(body) });
    return res.ok;
  } catch (e) {
    return false;
  }
}

function ensureJsonSafe(key, value) {
  // replace undefined / NaN
  if (typeof value === "number" && !Number.isFinite(value)) return null;
  if (value === undefined) return null;
  return value;
}
