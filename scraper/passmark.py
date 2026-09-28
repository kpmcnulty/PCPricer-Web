"""CPU and GPU benchmarks and prices from PassMark's "mega page" data endpoints.

The frontend prices a part as poly(benchmark) * decay(age):

- poly(benchmark) is what that much performance costs new today. It's fitted to
  recent desktop parts that PassMark lists a price for, one curve for CPUs and one
  for GPUs.
- decay(age) covers everything that makes a used part worth less than a new one
  with the same benchmark (no warranty, wear, older features, power draw).
"""
import re
import statistics
import time

from common import ScrapeError, decay_constant, fit, get, poly

CPU_PAGE = "https://www.cpubenchmark.net/CPU_mega_page.html"
CPU_DATA = "https://www.cpubenchmark.net/data/"
GPU_PAGE = "https://www.videocardbenchmark.net/GPU_mega_page.html"
GPU_DATA = "https://www.videocardbenchmark.net/data/"


# Years until a used part is worth 50% of a new part with the same benchmark, fitted with
# calibrate.py against eBay sold listings (Sep 2026). Cards/chips that sell above the new
# price for their benchmark (24GB+ NVIDIA cards, the fastest chip for an old socket like
# the 5800X3D or 9900K) are left out of those fits; the site notes them instead.
# GPU: 1080 Ti and RX 7900 XTX fit 8.5y.
# CPU: 12600K, 13700K, 8700K and Ryzen 5 3600 fit 9.6y.
GPU_HALFLIFE_YEARS = 8
CPU_HALFLIFE_YEARS = 10

# Only well-sampled, recent desktop parts go into the regression.
CPU_MIN_SAMPLES = 50
CPU_MAX_AGE_DAYS = 1095  # 500 left only 3 Intel parts in Sep 2026; 3 years gives ~30-40 per brand
GPU_MIN_SAMPLES = 100
GPU_MAX_AGE_DAYS = 1095
# Workstation cards are filed as "Desktop" but cost 3-4x a gaming card of the same speed,
# so they're kept out of the curve fit (they still appear in the site's list).
WORKSTATION_GPU = re.compile(r"\b(RTX A\d+|RTX PRO|Quadro|Radeon Pro|FirePro|Tesla|Arc Pro)\b", re.I)

# Parts with this few samples are left out of the site's lists entirely.
LIST_MIN_SAMPLES = 5

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def fetch_rows(s, page, data_url):
    get(s, page)  # sets the PHPSESSID cookie the data endpoint requires
    r = get(s, data_url, params={"_": int(time.time() * 1000)}, headers={
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": page,
    })
    try:
        payload = r.json()
    except ValueError as e:
        raise ScrapeError(f"{data_url}: response is not JSON (starts {r.text[:80]!r})") from e
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ScrapeError(f"{data_url}: unexpected JSON shape, keys {list(payload)[:10]}")
    return rows


def num(value):
    """'12,345' / '$1,234.56*' / 123 -> float; 'NA', '' or None -> None."""
    if value is None:
        return None
    cleaned = re.sub(r"[$,*\s]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return None


def age_days(date, today):
    """'Jan 2020' -> days since 15 Jan 2020; anything else -> None."""
    parts = str(date).split()
    if len(parts) != 2 or parts[0][:3] not in MONTHS or not parts[1].isdigit():
        return None
    released = today.replace(year=int(parts[1]), month=MONTHS[parts[0][:3]], day=15)
    return (today - released).days


def parse(rows, bench_key, today):
    parts = []
    for row in rows:
        age = age_days(row.get("date"), today)
        bench = num(row.get(bench_key))
        samples = num(row.get("samples"))
        if age is None or bench is None or samples is None or "id" not in row:
            continue
        parts.append({
            "idp": int(row["id"]),
            "name": str(row.get("name", "")).replace("\\", "").strip(),
            "bench": int(round(bench)),
            "age": age,
            "samples": samples,
            "price": num(row.get("price")),
            "desktop": str(row.get("cat", "")).strip() == "Desktop",
        })
    return parts


def regression_set(parts, min_samples, max_age):
    return [p for p in parts
            if p["desktop"] and p["price"] and p["samples"] >= min_samples and p["age"] <= max_age]


def price_frontier(parts):
    """Parts that no other part beats on both benchmark and price.

    A buyer's alternative to a used part is the cheapest new part with the same
    performance, so the curve is fitted to these. Overpriced listings drop out
    because something faster is always cheaper than them.
    """
    return [p for p in parts
            if not any(q is not p and q["bench"] >= p["bench"] and q["price"] <= p["price"] for q in parts)]


def fit_price_curve(parts, name, **kwargs):
    benches = [p["bench"] for p in parts]
    prices = [p["price"] for p in parts]
    # Start from price = k * bench; the optimizer's default start (all 1s on an x^4 curve)
    # can get stuck far from the answer.
    start = [0, 0, 0, statistics.median(y / x for x, y in zip(benches, prices))]
    return fit(poly, benches, prices, name, bounds=(0, 100), p0=start, **kwargs)


def fit_frontier(parts, name):
    frontier = price_frontier(parts)
    # sigma=price makes it a relative-error fit, so expensive parts don't dominate.
    return fit_price_curve(frontier, name, sigma=[p["price"] for p in frontier])


def scrape_cpus(s, today):
    rows = fetch_rows(s, CPU_PAGE, CPU_DATA)
    cpus = parse(rows, "cpumark", today)
    for cpu in cpus:
        cpu["name"] = cpu["name"].split("@")[0].strip()
        cpu["brand"] = "AMD" if "AMD" in cpu["name"] else "Intel" if "Intel" in cpu["name"] else "Unknown"
    if len(cpus) < 1000:
        raise ScrapeError(f"CPU list has only {len(cpus)} parts; PassMark data looks incomplete")

    # One curve for both brands: at the same benchmark they cost within ~5% of each other new.
    # Not the frontier fit: Core Ultra chips score high on CPU Mark but sell cheap, and would
    # drag every CPU's price down to theirs.
    x86 = regression_set([c for c in cpus if c["brand"] != "Unknown"], CPU_MIN_SAMPLES, CPU_MAX_AGE_DAYS)
    fitted = fit_price_curve(x86, "CPU")
    params = {f"cpu_{k}": v for k, v in zip("abcd", fitted)}

    listed = [{k: c[k] for k in ("idp", "name", "bench", "age", "brand")}
              for c in cpus if c["samples"] >= LIST_MIN_SAMPLES]
    return listed, params


def scrape_gpus(s, today):
    rows = fetch_rows(s, GPU_PAGE, GPU_DATA)
    gpus = parse(rows, "g3d", today)
    if len(gpus) < 500:
        raise ScrapeError(f"GPU list has only {len(gpus)} parts; PassMark data looks incomplete")

    gaming = [g for g in gpus if not WORKSTATION_GPU.search(g["name"])]
    fitted = fit_frontier(regression_set(gaming, GPU_MIN_SAMPLES, GPU_MAX_AGE_DAYS), "GPU")
    params = {f"gpu_{k}": v for k, v in zip("abcd", fitted)}

    listed = [{k: g[k] for k in ("idp", "name", "bench", "age")}
              for g in gpus if g["samples"] >= LIST_MIN_SAMPLES]
    return listed, params


def scrape(s, today):
    cpus, cpu_params = scrape_cpus(s, today)
    gpus, gpu_params = scrape_gpus(s, today)
    params = {**cpu_params, **gpu_params,
              "cpu_decay": decay_constant(CPU_HALFLIFE_YEARS),
              "gpu_decay": decay_constant(GPU_HALFLIFE_YEARS)}
    return cpus, gpus, params
