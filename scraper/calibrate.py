"""Checks the site's GPU prices against eBay sold listings and fits the GPU half-life.

The site prices a GPU as poly(bench) * exp(age^2 / w). poly comes from new prices
(passmark.py), so the only free number is the half-life in w. For each card with eBay
sales, ln(ebay / poly) = age^2 / w, and w is fitted to all cards by least squares.

Input is eBay search result pages saved from the browser (Ctrl+S, "Webpage, HTML only")
with "Sold items" ticked. Each page is one card; the search words pick the PassMark part.
Later the Marketplace Insights API can replace load_saved_page: everything after it only
needs (title, price, condition, sold date) rows.

usage: python calibrate.py "../Rtx 3090 for sale _ eBay.htm" ... [--data ../data.json]
"""
import argparse
import datetime
import html
import json
import math
import pathlib
import re
import statistics
import sys
from urllib.parse import parse_qs, urlparse

from common import poly

# Conditions that count as a used sale. Brand New / Open Box sell near retail and
# "Parts Only" cards are broken.
USED = re.compile(r"^(Pre-Owned|Used|(Excellent|Very Good|Good) - Refurbished)$")
# Listings that aren't one stock working card: whole PCs, bundles, broken or modded cards,
# loose parts. ("Triple Fan" or "Water Block" alone are real cards, so those words stay.)
JUNK = re.compile(r"\b(for parts|parts only|broken|not working|faulty|as[- ]is|no display|artifact\w*|"
                  r"lot|bundle|bracket|backplate|shroud|box only|empty box|heatsink only|mod(ded)?|"
                  r"desktop|gaming pc|computer|laptop|mobile|i[579]-?\d{4,5}\w*|ryzen)\b", re.I)
# Words that make it a different card when they follow the model number (RTX 3090 Ti, 4090 D...).
VARIANT = re.compile(r"^\s*(ti|super|d|xt|xtx|gre|m)\b", re.I)
# Sales older than this before the newest sale on the page are ignored.
MAX_SALE_AGE_DAYS = 90


def text(fragment):
    plain = html.unescape(re.sub(r"<[^>]+>", "", fragment))
    return re.sub(r"[​-‏﻿]", "", plain).replace("\xa0", " ").strip()


def load_saved_page(path):
    """-> (search words, [listing]) from an eBay search page saved from the browser."""
    page = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    canonical = re.search(r'rel="canonical" href="([^"]+)"', page)
    if not canonical:
        raise ValueError(f"{path}: not a saved eBay search page")
    query = parse_qs(urlparse(html.unescape(canonical.group(1))).query)["_nkw"][0]

    listings = []
    for card in page.split('<li class="s-card')[1:]:
        sold = re.search(r's-card__caption">([\s\S]*?)</div>', card)
        title = re.search(r's-card__title">([\s\S]*?)</div>', card)
        price = re.search(r's-card__price">([\s\S]*?)</span>', card)  # first one is the sale price
        subtitles = re.findall(r'<div class="s-card__subtitle">([\s\S]*?)</div>', card)
        if not (sold and title and price and subtitles):
            continue  # ads and "Shop on eBay" tiles
        date = re.search(r"Sold\s+(\w{3} \d{1,2}, \d{4})", text(sold.group(1)))
        amount = re.fullmatch(r"\$([\d,]+\.\d\d)", text(price.group(1)))
        if not (date and amount):
            continue  # unsold, or a price range for multi-variation listings
        listings.append({
            "title": text(title.group(1)).removesuffix("Opens in a new window or tab"),
            "price": float(amount.group(1).replace(",", "")),
            "condition": text(subtitles[-1]),
            "sold": datetime.datetime.strptime(date.group(1), "%b %d, %Y").date(),
        })
    return query, listings


def model_pattern(query):
    """'rtx 3090' -> regex for RTX 3090 / RTX3090 / RTX-3090, remembering where it ends."""
    return re.compile(r"\b" + r"[\s-]?".join(map(re.escape, query.lower().split())) + r"\b", re.I)


def is_this_card(title, pattern):
    m = pattern.search(title)
    return bool(m) and not VARIANT.match(title[m.end():]) and not JUNK.search(title)


def used_sales(query, listings):
    pattern = model_pattern(query)
    kept = [l for l in listings if USED.match(l["condition"]) and is_this_card(l["title"], pattern)]
    if kept:
        newest = max(l["sold"] for l in kept)
        kept = [l for l in kept if (newest - l["sold"]).days <= MAX_SALE_AGE_DAYS]
    return kept


def find_part(query, parts):
    """PassMark part whose name is exactly the search words (ignoring 'GeForce'/'Radeon')."""
    want = re.sub(r"[\s-]", "", query.lower())
    for p in parts:
        name = re.sub(r"^(geforce|radeon)\s+", "", p["name"].lower())
        if re.sub(r"[\s-]", "", name) == want:
            return p
    return None


def fit_decay(cards):
    """Least-squares w in ln(ratio) = age^2 / w, through the origin."""
    k = sum(c["age"] ** 2 * math.log(c["ratio"]) for c in cards) / sum(c["age"] ** 4 for c in cards)
    return 1 / k if k < 0 else None


def halflife_years(w):
    return math.sqrt(-w * math.log(2)) / 365


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", nargs="+")
    ap.add_argument("--data", default=pathlib.Path(__file__).resolve().parents[1] / "data.json")
    ap.add_argument("--min-sales", type=int, default=5)
    args = ap.parse_args()

    data = json.loads(pathlib.Path(args.data).read_text())
    coeffs = [data["params"][f"gpu_{k}"] for k in "abcd"]
    decay_now = data["params"]["gpu_decay"]

    cards = []
    print(f"{'card':<18}{'sales':>6}{'eBay p25':>10}{'median':>9}{'p75':>9}{'age':>6}"
          f"{'new':>8}{'site':>8}{'site err':>10}{'implied half-life':>19}")
    for path in args.pages:
        query, listings = load_saved_page(path)
        sales = used_sales(query, listings)
        part = find_part(query, data["gpu"])
        if part is None:
            print(f"{query:<18} no PassMark part named {query!r}, skipped")
            continue
        if len(sales) < args.min_sales:
            print(f"{query:<18} only {len(sales)} usable sales of {len(listings)}, skipped")
            continue
        prices = sorted(l["price"] for l in sales)
        q1, median, q3 = statistics.quantiles(prices, n=4)
        new = poly(part["bench"], *coeffs)
        site = new * math.exp(part["age"] ** 2 / decay_now)
        ratio = median / new
        implied = part["age"] / 365 * math.sqrt(math.log(2) / -math.log(ratio)) if ratio < 1 else None
        cards.append({"name": part["name"], "age": part["age"], "ratio": ratio, "median": median, "new": new})
        print(f"{query:<18}{len(sales):>6}{q1:>10.0f}{median:>9.0f}{q3:>9.0f}{part['age'] / 365:>5.1f}y"
              f"{new:>8.0f}{site:>8.0f}{site / median - 1:>+10.0%}"
              + (f"{implied:>17.1f}y" if implied else f"{'sells above new':>19}"))

    # Decay can only lower a price, so cards selling above what their performance costs new
    # (e.g. high-VRAM cards bought for AI) are something else and would drag the fit.
    below = [c for c in cards if c["ratio"] < 1]
    above = [c for c in cards if c["ratio"] >= 1]
    if above:
        print("\nselling above new-price curve (not fitted): "
              + ", ".join(f"{c['name']} {c['ratio']:.2f}x" for c in above))
    if not below:
        return 1
    w = fit_decay(below)
    print(f"\ncurrent half-life {halflife_years(decay_now):.1f}y, best fit {halflife_years(w):.1f}y "
          f"from {len(below)} cards")
    for c in below:
        fitted = c["new"] * math.exp(c["age"] ** 2 / w)
        print(f"  {c['name']:<24} eBay {c['median']:>6.0f}  fitted {fitted:>6.0f}  {fitted / c['median'] - 1:>+5.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
