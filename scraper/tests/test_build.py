"""Runs the whole pipeline against fake PassMark / Newegg responses (no network)."""
import datetime
import json
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import build  # noqa: E402
import common  # noqa: E402
import newegg  # noqa: E402
import passmark  # noqa: E402

TODAY = datetime.date(2026, 9, 28)
SITE_DATA = pathlib.Path(__file__).resolve().parents[2] / "data.json"


class FakeResponse:
    def __init__(self, text="", payload=None):
        self.status_code = 200
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def passmark_rows(n, bench_key, brand_names):
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n):
        bench = int(rng.uniform(500, 60000))
        rows.append({
            "id": i,
            "name": f"{brand_names[i % len(brand_names)]} Part {i} @ 3.0GHz",
            "price": f"${0.01 * bench + 20:,.2f}*" if i % 7 else "NA",
            bench_key: f"{bench:,}",
            "date": ["Jan 2026", "Jun 2025", "Mar 2019"][i % 5 % 3] if i % 11 else "NA",
            "samples": str(int(rng.uniform(1, 500))),
            "cat": "Desktop" if i % 4 else "Laptop",
        })
    return rows


def newegg_html(price):
    items = "".join(
        f'<li class="price-current">$<strong>{int(p):,}</strong><sup>.99</sup></li>'
        for p in (price * 0.9, price, price * 1.1))
    return f"<ul>{items}</ul>"


def url_prices():
    prices = {}
    for size, url in zip(newegg.RAM_SIZES_GB, newegg.RAM_URLS):
        prices[url] = 3 * size + 5
    for urls in newegg.PSU_URLS.values():
        for watts, url in zip(newegg.PSU_WATTS, urls):
            if url:
                prices[url] = 30 + 0.12 * watts
    for size, url in zip(newegg.HDD_SIZES_GB, newegg.HDD_URLS):
        prices[url] = 40 + 0.015 * size
    for size, url in zip(newegg.SSD_SIZES_GB, newegg.SSD_URLS):
        prices[url] = 15 + 0.06 * size
    return prices


class FakeSession:
    def __init__(self, prices, cpu_rows, gpu_rows):
        self.prices = prices
        self.cpu_rows = cpu_rows
        self.gpu_rows = gpu_rows

    def get(self, url, **kwargs):
        if url == passmark.CPU_DATA:
            return FakeResponse(payload={"data": self.cpu_rows})
        if url == passmark.GPU_DATA:
            return FakeResponse(payload={"data": self.gpu_rows})
        if url in (passmark.CPU_PAGE, passmark.GPU_PAGE):
            return FakeResponse("<html></html>")
        return FakeResponse(newegg_html(self.prices[url]))


@pytest.fixture(autouse=True)
def no_delay(monkeypatch):
    monkeypatch.setattr(common, "DELAY", (0, 0))


def fake_session(**overrides):
    args = dict(prices=url_prices(),
                cpu_rows=passmark_rows(3000, "cpumark", ["AMD Ryzen", "Intel Core", "Qualcomm"]),
                gpu_rows=passmark_rows(1500, "g3d", ["GeForce"]))
    args.update(overrides)
    return FakeSession(**args)


def test_output_has_every_field_the_site_reads():
    data = build.build(fake_session(), TODAY)
    current = json.loads(SITE_DATA.read_text())

    for section in ("params", "ram", "driveparams"):
        assert set(current[section]) <= set(data[section]), section
    for tier in ("low", "mid", "high"):
        for k in "abc":
            assert f"{tier}_{k}" in data["psu"]
    assert set(data["cpu"][0]) == set(current["cpu"][0])
    assert set(data["gpu"][0]) >= {"idp", "name", "bench", "age"}
    assert data["mobo"] == current["mobo"] and data["cases"] == current["cases"]
    assert {c["brand"] for c in data["cpu"]} == {"AMD", "Intel", "Unknown"}
    assert all("@" not in c["name"] for c in data["cpu"])


def test_curves_track_the_scraped_prices():
    data = build.build(fake_session(), TODAY)
    ram, drives, psu = data["ram"], data["driveparams"], data["psu"]
    assert common.linear(16, ram["ddr4_a"], ram["ddr4_b"]) == pytest.approx(3 * 16 + 5, rel=0.1)
    ssd = [drives[f"ssd_{k}"] for k in "abcd"]
    assert common.ypoly(1000, *ssd) == pytest.approx(15 + 60, rel=0.15)
    mid = [psu[f"mid_{k}"] for k in "abc"]
    assert common.ln(750, *mid) == pytest.approx(0.75 * (30 + 90), rel=0.15)


def test_blocked_newegg_page_fails_the_run():
    prices = url_prices()
    s = fake_session(prices=prices)
    s.get = lambda url, **kw: FakeResponse("<html>Are you a human?</html>") \
        if url == newegg.SSD_URLS[0] else FakeSession.get(s, url, **kw)
    with pytest.raises(common.ScrapeError, match="no prices found"):
        build.build(s, TODAY)


def test_passmark_returning_html_fails_the_run():
    s = fake_session()
    s.get = lambda url, **kw: FakeResponse("<html>captcha</html>")
    with pytest.raises(common.ScrapeError, match="not JSON"):
        build.build(s, TODAY)


def test_truncated_passmark_list_fails_the_run():
    with pytest.raises(common.ScrapeError, match="looks incomplete"):
        build.build(fake_session(cpu_rows=passmark_rows(200, "cpumark", ["AMD", "Intel"])), TODAY)


def test_main_leaves_files_untouched_on_failure(tmp_path, monkeypatch):
    out = tmp_path / "data.json"
    out.write_text("old")
    monkeypatch.setattr(build, "session", lambda: FakeSession({}, [], []))
    monkeypatch.setattr(sys, "argv", ["build.py", "--out", str(out), "--history", str(tmp_path / "h")])
    assert build.main() == 1
    assert out.read_text() == "old"
    assert not (tmp_path / "h").exists()


def test_main_writes_data_and_history(tmp_path, monkeypatch):
    out = tmp_path / "data.json"
    monkeypatch.setattr(build, "session", fake_session)
    monkeypatch.setattr(sys, "argv", ["build.py", "--out", str(out), "--history", str(tmp_path / "h")])
    assert build.main() == 0
    assert json.loads(out.read_text())["cpu"]
    assert sorted(p.name for p in (tmp_path / "h").iterdir()) == \
        ["cpugpu.csv", "drives.csv", "psu.csv", "ram.csv"]
