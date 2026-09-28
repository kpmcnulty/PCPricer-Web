"""CPU and GPU benchmarks and prices from PassMark's "mega page" data endpoints.

The frontend prices a part as poly(benchmark) * decay(age). This fits poly to
recent desktop parts that PassMark lists a price for, separately for AMD CPUs,
Intel CPUs and GPUs.
"""
import math
import re
import time

from common import ScrapeError, fit, get, poly

CPU_PAGE = "https://www.cpubenchmark.net/CPU_mega_page.html"
CPU_DATA = "https://www.cpubenchmark.net/data/"
GPU_PAGE = "https://www.videocardbenchmark.net/GPU_mega_page.html"
GPU_DATA = "https://www.videocardbenchmark.net/data/"

HALFLIFE_YEARS = 20  # years until a part is worth 50% of its benchmark price
DECAY = (365 * HALFLIFE_YEARS) ** 2 / -math.log(2)

# Only well-sampled, recent desktop parts go into the regression.
CPU_MIN_SAMPLES = 50
CPU_MAX_AGE_DAYS = 500
GPU_MIN_SAMPLES = 100
GPU_MAX_AGE_DAYS = 800

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


def fit_parts(parts, name):
    return fit(poly, [p["bench"] for p in parts], [p["price"] for p in parts], name, bounds=(0, 100))


def scrape_cpus(s, today):
    rows = fetch_rows(s, CPU_PAGE, CPU_DATA)
    cpus = parse(rows, "cpumark", today)
    for cpu in cpus:
        cpu["name"] = cpu["name"].split("@")[0].strip()
        cpu["brand"] = "AMD" if "AMD" in cpu["name"] else "Intel" if "Intel" in cpu["name"] else "Unknown"
    if len(cpus) < 1000:
        raise ScrapeError(f"CPU list has only {len(cpus)} parts; PassMark data looks incomplete")

    params = {}
    for brand in ("AMD", "Intel"):
        fitted = fit_parts(
            regression_set([c for c in cpus if c["brand"] == brand], CPU_MIN_SAMPLES, CPU_MAX_AGE_DAYS),
            f"{brand} CPU")
        params.update({f"{brand.lower()}_{k}": v for k, v in zip("abcd", fitted)})

    listed = [{k: c[k] for k in ("idp", "name", "bench", "age", "brand")}
              for c in cpus if c["samples"] >= LIST_MIN_SAMPLES]
    return listed, params


def scrape_gpus(s, today):
    rows = fetch_rows(s, GPU_PAGE, GPU_DATA)
    gpus = parse(rows, "g3d", today)
    if len(gpus) < 500:
        raise ScrapeError(f"GPU list has only {len(gpus)} parts; PassMark data looks incomplete")

    fitted = fit_parts(regression_set(gpus, GPU_MIN_SAMPLES, GPU_MAX_AGE_DAYS), "GPU")
    params = {f"gpu_{k}": v for k, v in zip("abcd", fitted)}

    listed = [{k: g[k] for k in ("idp", "name", "bench", "age")}
              for g in gpus if g["samples"] >= LIST_MIN_SAMPLES]
    return listed, params


def scrape(s, today):
    cpus, cpu_params = scrape_cpus(s, today)
    gpus, gpu_params = scrape_gpus(s, today)
    params = {**cpu_params, **gpu_params, "cpu_decay": DECAY, "gpu_decay": DECAY}
    return cpus, gpus, params
