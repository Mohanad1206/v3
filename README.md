# Gaming Accessories Scraper — Text Output + GitHub CI

- Static **and** dynamic scraping (Playwright).
- Output: **plain text** lines (not CSV).
- Rooted paths so you can run from anywhere.
- GitHub Actions workflow included (robust python selection, artifact upload, optional Make webhook).

## Local quick start
```bash
./scripts/run.sh   # macOS/Linux
# or
./scripts/run.ps1  # Windows PowerShell
```

## Output format (text)
```
timestamp_iso | site_name | product_name | status | price_value | currency | product_url | raw_price_text
```

## GitHub Actions
The workflow is in `.github/workflows/scrape.yml`.

- Runs on a schedule and manual dispatch.
- Picks `python` or `python3` automatically.
- Installs Playwright with browsers.
- Uploads `output/*.txt` as artifact.
- Optionally POSTs to Make webhook if `MAKE_WEBHOOK_URL` secret exists.

Configure repo variables in **Settings → Variables → Actions**:
- `SCRAPER_FIRST_N` (default 50)
- `SCRAPER_DYNAMIC` (`auto` or `always`)

Configure secret in **Settings → Secrets and variables → Actions** (optional):
- `MAKE_WEBHOOK_URL`
