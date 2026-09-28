# PCPricer

Estimates what used PC parts are worth. Live at [pcpricer.net](https://pcpricer.net).

- **Site**: `index.html`, `script.js`, `style.css`, `images/`. It is static and reads `data.json`.
- **Scraper**: `scraper/`. This is the old Raspberry Pi scripts from [kpmcnulty/PCPricer](https://github.com/kpmcnulty/PCPricer), ported to run on GitHub Actions.
- **History**: `history/`. Each run appends the fitted curve parameters, so trends can be charted later. `history/2021/` holds the Pi-era logs.

## How data updates work

`.github/workflows/update-data.yml` runs every Monday; you can also start it by hand from the Actions tab. It:

1. scrapes PassMark (CPU/GPU benchmarks and prices) and Newegg (RAM, PSU, HDD, SSD prices),
2. fits the price curves that `script.js` uses,
3. commits `data.json` and `history/`, then deploys.

A run is all-or-nothing. If any source is blocked or returns data that fails the sanity checks, the job fails and GitHub emails you. `data.json` is not changed.

Motherboards and cases are not priced; the site estimates CPU, GPU, drives, RAM and PSU only.

## Hosting on Hostinger

`.github/workflows/deploy.yml` uploads the site over FTP. It runs on every push to `main` and after each data update. To turn it on:

1. In hPanel → Files → FTP Accounts, note the FTP host, username and password.
2. In GitHub → Settings → Secrets and variables → Actions:
   - Secrets: `FTP_SERVER`, `FTP_USERNAME`, `FTP_PASSWORD`
   - Variables: `HOSTINGER_DEPLOY` = `true`. Optionally set `FTP_SERVER_DIR`; the default is `public_html/`. It must end with `/`.
3. Run **Deploy to Hostinger** from the Actions tab, and check the site on Hostinger's temporary domain.
4. Point pcpricer.net's DNS at Hostinger, then turn off GitHub Pages.

## Run locally

```
pip install -r scraper/requirements.txt pytest
python -m pytest scraper/tests   # offline tests with fake responses
python scraper/build.py          # real scrape (takes ~10 min because it waits between requests)
```
