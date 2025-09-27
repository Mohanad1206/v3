
# Dynamic Scraper (Playwright)

A production-ready scraper for **dynamic** e-commerce websites using **Playwright (Chromium)**.  
Outputs **newline-delimited JSON** (`.ndjson`) for easy piping to tools like Make, Apify, or data stores.

## Features
- Handles dynamic/SPAs with Playwright.
- Limits results to the **first N products** per URL (default **50**).
- **Domain-specific selector config** in `config/domain-selectors.json`.
- **JSON-LD** Product fallback for robustness.
- Blocks images/media/fonts to reduce bandwidth.
- Simple CLI with concurrency control and delays to be polite.

## Install
```bash
# Node 18+ recommended
npm i
# Playwright browser binaries
npm run postinstall
```

## Usage
Put one URL per line into an input file (e.g., `examples/urls.txt`).

```bash
# Basic
node src/scrape.js --in examples/urls.txt --out out/results.ndjson

# Increase concurrency and cap first 30 products per site
node src/scrape.js --in examples/urls.txt --out out/results.ndjson --concurrency 5 --max 30

# Headful (visible browser) + shorter timeout for debugging
node src/scrape.js --in examples/urls.txt --out out/results.ndjson --headful --timeout 20000
```

**Output**: Each line is a JSON object like:
```json
{
  "timestamp_iso": "2025-09-28T12:34:56.000Z",
  "site_name": "example.com",
  "product_name": "Controller XYZ",
  "sku": null,
  "product_url": "https://example.com/p/controller-xyz",
  "status": "Available",
  "price_value": 2499,
  "currency": "EGP",
  "raw_price_text": "EGP 2,499",
  "source_url": "https://example.com/gaming/controllers",
  "notes": "selectors"
}
```

## Configure Selectors
Edit `config/domain-selectors.json` and add a block with your domain keys (without `www.`).  
Example for `2b.com.eg` is included. Add/adjust CSS selectors for:
- `product_list` — links to each product from a category/listing page
- `name` — the product title on a product page
- `price` — the price element
- `availability` — stock status element

The `default` block has generic fallbacks used when a domain is not listed.

## Examples
`examples/urls.txt` contains a few placeholder category URLs. Replace with your real category/product URLs.  
Tip: Use category/listing pages. The scraper will visit **first N product links** from each listing.  
If it can't find product links, it will treat the URL itself as a product page and try to extract data.

## Tips for Dynamic Sites
- Try `--headful` the first time to ensure content renders as expected.
- Increase `--timeout` or add `--delay 1500` if sites rate limit.
- If the site uses infinite scroll, you can extend `extractWithSelectors` to scroll and load more.

## Piping to Make / Webhooks
You can tail the `.ndjson` and push lines to a webhook from your Make scenario, or run this as a step in GitHub Actions and POST the file after completion.

## License
MIT


---

## Make.com & Webhook Integration

### Option A: Line mode (recommended)
Sends **each product as a separate POST** to your Make webhook in real time.

```bash
export MAKE_WEBHOOK_URL="https://hook.us2.make.com/xxxxxxxxxxxxxxxx"
node src/scrape.js --in examples/urls.txt --out out/results.ndjson --webhook "$MAKE_WEBHOOK_URL" --webhook-mode line
```

- Content-Type: `application/json`
- Body: a single JSON object per request (see `examples/sample-webhook-payload.json`)
- In Make: start with a **Custom Webhook** → the output bundle is already JSON → map fields directly or use an **Array aggregator** to collect many rows then pass to Sheets / Datastore / CSV.

### Option B: Batch mode
Sends **one POST after run** with an **array** of all records.

```bash
export MAKE_WEBHOOK_URL="https://hook.us2.make.com/xxxxxxxxxxxxxxxx"
node src/scrape.js --in examples/urls.txt --out out/results.ndjson --webhook "$MAKE_WEBHOOK_URL" --webhook-mode batch
```

- Body: `{ "items": [ {...}, {...} ] }`

### Custom headers
```bash
node src/scrape.js --in examples/urls.txt --webhook "$MAKE_WEBHOOK_URL" --webhook-headers '{"X-Token":"abc123"}'
```

### Make field order & types
See `examples/make-mapping.json` for the canonical field list and types.


## GitHub Actions CI
This repo ships with `.github/workflows/scrape.yml`.

- **Manual run** from the Actions tab (workflow_dispatch).
- **Scheduled** (cron) run.
- Saves artifact `results.ndjson` and optionally **POSTs to Make** via `MAKE_WEBHOOK_URL` secret.

### Setup
1. Push to GitHub.
2. Go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `MAKE_WEBHOOK_URL`: your Make custom webhook URL
   - (Optional) `WEBHOOK_HEADERS`: JSON string for extra headers

### Run locally via Docker
```bash
docker build -t dyn-scraper .
docker run --rm -e MAKE_WEBHOOK_URL="https://hook.us2.make.com/your-id" dyn-scraper
```
