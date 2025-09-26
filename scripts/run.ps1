# PowerShell
$py = "python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { $py = "python3" }
& $py -m venv .venv
. .\.venv\Scripts\Activate.ps1
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt
& $py -m playwright install --with-deps
& $py scrape.py --dynamic auto
