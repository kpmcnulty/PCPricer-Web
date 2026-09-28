"""RAM, PSU and drive prices from Newegg search listings.

Each URL is a Newegg search filtered to one size or tier. We take the median
listed price per URL and fit the curve the frontend uses for that part type.
"""
import json
import re

import numpy as np

from common import ScrapeError, decay_constant, fit, get, linear, ln, ypoly

INITIAL_STATE = re.compile(r"window\.__initialState__\s*=\s*(\{.*?\})\s*</script>", re.S)

# Share of the new price a used PSU sells for, whatever its age. eBay sold listings (Sep 2026):
# 27 used ATX PSUs went for a median 40% of the new price of the same rating and wattage
# (middle half 35-56%), and 3-year-old units sold as cheaply as 11-year-old ones, so PSUs
# get this flat factor instead of an age decay.
USED_FACTOR_PSU = 0.5

# Years until a used part is worth 50% of a new one (see passmark.py). None = no decay.
RAM_HALFLIFE_YEARS = None  # used RAM sells for about what new RAM costs
# From eBay sold listings (Sep 2026): used 1TB SSDs (~5 years old) sell for 57% of new and
# 512GB SSDs (~6 years) for 43%. Used 1TB hard drives were 10-15 years old and sold for about
# what 7 years gives at that age; there wasn't enough data on newer ones to change it.
HALFLIFE_YEARS = {"hdd": 7, "ssd": 5.5}
PSU_HALFLIFE_YEARS = None  # see USED_FACTOR_PSU

RAM_SIZES_GB = [4, 8, 16, 32, 64]
# Smallest size priced per generation (there are no 4GB DDR5 sticks).
RAM_MIN_GB = {"DDR4": 4, "DDR5": 8}
RAM_URLS = [
    "https://www.newegg.com/p/pl?d=ram&N=100007611%20500000256&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?d=ram&N=100007611%20500000512&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?d=ram&N=100007611%20500001024&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?d=ram&N=100007611%20500002048&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?d=ram&N=100007611%20500004096&PageSize=96&Order=3",
]

# Standard ATX wattages; under 550W Newegg is mostly SFX and OEM replacement units.
PSU_WATTS = [550, 650, 750, 850, 1000, 1200]
PSU_MIN_LISTINGS = 5  # per wattage, or that point is left out of the fit
PSU_PAGES = 3
# Newegg's 80 Plus rating filters per tier; each page is grouped by the wattage in the title.
PSU_TIERS = {
    "low": "600037997%20600038000",   # 80 Plus / Bronze
    "mid": "600037998%20600037999",   # Silver / Gold (almost all Gold now)
    "high": "600112163%20601115166",  # Platinum / Titanium
}
PSU_URL = "https://www.newegg.com/p/pl?N=100007657%20{ids}&PageSize=96&Order=3&page={page}"
# Small-form-factor and server units cost more per watt than the ATX PSUs the site prices.
NOT_ATX_PSU = re.compile(r"\b(SFX|SFX-L|TFX|Flex|1U|2U|server|redundant|industrial|mining|DC|replacement)\b", re.I)

HDD_SIZES_GB = [500, 1000, 2000, 4000, 6000, 8000, 16000]
HDD_URLS = [
    "https://www.newegg.com/p/pl?N=100167523%20600003290%204814&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600003298&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600003300&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600217643&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600490667&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600376735&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100167523%204814%20601334339&PageSize=96&Order=3",
]

SSD_SIZES_GB = [124, 250, 500, 1000, 2000, 4000]
SSD_URLS = [
    "https://www.newegg.com/p/pl?N=100011693%204814%20600038484%20600038478&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100011693%204814%20600038500%20600038485%20600038487&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100011693%204814%20600038491%20600038492%20600038502&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100011693%204814%20600038493&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100011693%204814%20600038497&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?N=100011693%204814%20600545605&PageSize=96&Order=3",
]


def listings(s, url):
    """-> [(price, title)] for every priced product on a Newegg search page."""
    # Newegg renders listing prices client-side; the HTML only has a few. Every product's
    # price is in the JSON the page boots from: window.__initialState__.Products[].ItemCell.
    html = get(s, url).text
    m = INITIAL_STATE.search(html)
    if not m:
        raise ScrapeError(f"{url}: no prices found, page has no __initialState__ (blocked, or Newegg changed its page layout)")
    try:
        products = json.loads(m.group(1)).get("Products") or []
    except ValueError as e:
        raise ScrapeError(f"{url}: __initialState__ is not valid JSON: {e}") from e
    found = []
    for product in products:
        cell = product.get("ItemCell") or {}
        price = cell.get("FinalPrice")
        title = (cell.get("Description") or {}).get("Title") or ""
        if isinstance(price, (int, float)) and price > 0:
            found.append((float(price), title))
    return found


def median_price(url, found, title_pattern=None):
    prices = [p for p, title in found if not title_pattern or re.search(title_pattern, title)]
    if not prices:
        raise ScrapeError(f"{url}: no prices found (blocked, or Newegg changed its page layout)")
    return float(np.median(prices))


def scrape_ram(s):
    # Newegg's size filters mix DDR2-DDR5, so each page is split by the generation in the title.
    pages = {url: listings(s, url) for url in RAM_URLS}
    params = {}
    for gen, min_gb in RAM_MIN_GB.items():
        sizes = [gb for gb in RAM_SIZES_GB if gb >= min_gb]
        prices = [median_price(url, pages[url], rf"\b{gen}\b")
                  for gb, url in zip(RAM_SIZES_GB, RAM_URLS) if gb >= min_gb]
        a, b = fit(linear, sizes, prices, f"{gen} RAM", bounds=(0, 100))
        params.update({f"{gen.lower()}_a": a, f"{gen.lower()}_b": b})
    params["decay"] = decay_constant(RAM_HALFLIFE_YEARS)
    return params


def psu_watts(title):
    m = re.search(r"\b(\d{3,4})\s?W\b", title, re.I)
    return int(m.group(1)) if m and not NOT_ATX_PSU.search(title) else None


def scrape_psu(s):
    params = {}
    for tier, ids in PSU_TIERS.items():
        found = [row for page in range(1, PSU_PAGES + 1)
                 for row in listings(s, PSU_URL.format(ids=ids, page=page))]
        watts, prices = [], []
        for w in PSU_WATTS:
            at_w = [price for price, title in found if psu_watts(title) == w]
            if len(at_w) >= PSU_MIN_LISTINGS:
                watts.append(w)
                prices.append(float(np.median(at_w)))
        a, b, c = fit(ln, watts, prices, f"{tier} PSU",
                      p0=[5, 1, 0.1], bounds=([0, 0, 0], [np.inf, 1000, np.inf]))
        params.update({f"{tier}_a": a, f"{tier}_b": b, f"{tier}_c": c})
    params["decay"] = decay_constant(PSU_HALFLIFE_YEARS)
    params["used_factor"] = USED_FACTOR_PSU  # the site multiplies the new-price curve by this
    return params


def scrape_drives(s):
    params = {}
    for kind, sizes, urls in (("hdd", HDD_SIZES_GB, HDD_URLS), ("ssd", SSD_SIZES_GB, SSD_URLS)):
        prices = [median_price(url, listings(s, url)) for url in urls]
        fitted = fit(ypoly, sizes, prices, kind.upper(), bounds=(0, np.inf))
        params.update({f"{kind}_{k}": v for k, v in zip("abcd", fitted)})
        params[f"{kind}_decay"] = decay_constant(HALFLIFE_YEARS[kind])
    return params
