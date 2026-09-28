"""RAM, PSU and drive prices from Newegg search listings.

Each URL is a Newegg search filtered to one size or tier. We take the median
listed price per URL and fit the curve the frontend uses for that part type.
"""
import numpy as np
from bs4 import BeautifulSoup

from common import ScrapeError, fit, get, linear, ln, ypoly

# Share of the new price a used part sells for.
USED_FACTOR_PSU = 0.75

RAM_SIZES_GB = [4, 8, 16, 32, 64]
RAM_URLS = [
    "https://www.newegg.com/p/pl?d=ram&N=100007611%20500000256&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?d=ram&N=100007611%20500000512&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?d=ram&N=100007611%20500001024&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?d=ram&N=100007611%20500002048&PageSize=96&Order=3",
    "https://www.newegg.com/p/pl?d=ram&N=100007611%20500004096&PageSize=96&Order=3",
]

PSU_WATTS = [250, 500, 650, 750, 850, 1000, 1200]
# One URL per wattage above, per rating tier. None = no listing for that combination.
PSU_URLS = {
    "low": [  # 80 Plus / Bronze
        "https://www.newegg.com/p/pl?N=100007657%20600014038%20600014039%20600355193%20600014040&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600037997%20600038000%20600014066%20600014061%20600014060&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014078%20600014085%20600037997%20600038000&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014094%20600037997%20600038000&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014100%20600038000&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014107%20600038000&PageSize=96&Order=3",
        None,
    ],
    "mid": [  # Silver / Gold
        None,
        "https://www.newegg.com/p/pl?N=100007657%20600014066%20600014072%20600037998&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014078%20600014085%20600037999%20600037998&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014094%20600037998&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014100%20600037998&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014107%20600037999%20600037998&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014113%20600037998%20600037999&PageSize=96&Order=3",
    ],
    "high": [  # Platinum / Titanium
        None,
        "https://www.newegg.com/p/pl?N=100007657%20600112163%20601115166%20600014066%20600014072&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600479295%20600112163%20601115166&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014094%20600112163%20601115166&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600112163%20601115166%20600014100&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600014107%20600112163%20601115166&PageSize=96&Order=3",
        "https://www.newegg.com/p/pl?N=100007657%20600112163%20601115166%20600014113%20600014006%20600014002&PageSize=96&Order=3",
    ],
}

HDD_SIZES_GB = [500, 1000, 2000, 3000, 4000, 6000, 8000, 16000]
HDD_URLS = [
    "https://www.newegg.com/p/pl?N=100167523%20600003290%204814&PageSize=96",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600003298&PageSize=96",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600003300&PageSize=96",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600361769&PageSize=96",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600217643&PageSize=96",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600490667&PageSize=96",
    "https://www.newegg.com/p/pl?N=100167523%204814%20600376735&PageSize=96",
    "https://www.newegg.com/p/pl?N=100167523%204814%20601334339&PageSize=96",
]

SSD_SIZES_GB = [124, 250, 500, 1000, 2000, 4000]
SSD_URLS = [
    "https://www.newegg.com/p/pl?N=100011693%204814%20600038484%20600038478&PageSize=96",
    "https://www.newegg.com/p/pl?N=100011693%204814%20600038500%20600038485%20600038487&PageSize=96",
    "https://www.newegg.com/p/pl?N=100011693%204814%20600038491%20600038492%20600038502&PageSize=96",
    "https://www.newegg.com/p/pl?N=100011693%204814%20600038493&PageSize=96",
    "https://www.newegg.com/p/pl?N=100011693%204814%20600038497&PageSize=96",
    "https://www.newegg.com/p/pl?N=100011693%204814%20600545605&PageSize=96",
]


def listing_prices(s, url):
    soup = BeautifulSoup(get(s, url).text, "html.parser")
    prices = []
    for li in soup.select("li.price-current"):
        strong = li.find("strong")
        if strong is None:
            continue
        dollars = strong.get_text().replace(",", "").strip()
        if not dollars.isdigit():
            continue
        sup = li.find("sup")
        cents = sup.get_text().strip() if sup else ""
        prices.append(float(dollars + cents) if cents[1:].isdigit() else float(dollars))
    if not prices:
        raise ScrapeError(f"{url}: no prices found (blocked, or Newegg changed its page layout)")
    return prices


def median_price(s, url):
    return float(np.median(listing_prices(s, url)))


def scrape_ram(s):
    prices = [median_price(s, url) for url in RAM_URLS]
    a, b = fit(linear, RAM_SIZES_GB, prices, "DDR4 RAM", bounds=(0, 100))
    return {"ddr4_a": a, "ddr4_b": b}


def scrape_psu(s):
    params = {}
    for tier, urls in PSU_URLS.items():
        watts, prices = [], []
        for w, url in zip(PSU_WATTS, urls):
            if url is not None:
                watts.append(w)
                prices.append(USED_FACTOR_PSU * median_price(s, url))
        a, b, c = fit(ln, watts, prices, f"{tier} PSU",
                      p0=[5, 1, 0.1], bounds=([0, 0, 0], [np.inf, 1000, np.inf]))
        params.update({f"{tier}_a": a, f"{tier}_b": b, f"{tier}_c": c})
    return params


def scrape_drives(s):
    params = {}
    for kind, sizes, urls in (("hdd", HDD_SIZES_GB, HDD_URLS), ("ssd", SSD_SIZES_GB, SSD_URLS)):
        prices = [median_price(s, url) for url in urls]
        fitted = fit(ypoly, sizes, prices, kind.upper(), bounds=(0, np.inf))
        params.update({f"{kind}_{k}": v for k, v in zip("abcd", fitted)})
    return params
