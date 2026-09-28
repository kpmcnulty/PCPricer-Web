"""Scrape every source and write data.json for the site.

All-or-nothing: if any source fails or returns data that doesn't pass the
checks, this exits non-zero and leaves data.json and history untouched.

    python scraper/build.py            # writes ./data.json and appends ./history/*.csv
"""
import argparse
import csv
import datetime
import json
import os
import pathlib
import sys

import newegg
import passmark
from common import ScrapeError, session

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def build(s, today):
    print("PassMark CPUs + GPUs")
    cpus, gpus, params = passmark.scrape(s, today)
    print("Newegg RAM")
    ram = newegg.scrape_ram(s)
    print("Newegg PSUs")
    psu = newegg.scrape_psu(s)
    print("Newegg drives")
    drives = newegg.scrape_drives(s)

    return {
        "updated": today.isoformat(),
        "ram": ram,
        "psu": psu,
        "params": params,
        "cpu": cpus,
        "gpu": gpus,
        "driveparams": drives,
    }


def write_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    os.replace(tmp, path)


def append_history(history_dir, data):
    """One row per run per curve, so price trends can be charted later."""
    history_dir.mkdir(exist_ok=True)
    for name, values in (("cpugpu", data["params"]), ("ram", data["ram"]),
                         ("psu", data["psu"]), ("drives", data["driveparams"])):
        path = history_dir / f"{name}.csv"
        new = not path.exists()
        with path.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["date", *values])
            w.writerow([data["updated"], *values.values()])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "data.json")
    ap.add_argument("--history", type=pathlib.Path, default=ROOT / "history")
    args = ap.parse_args()

    try:
        data = build(session(), datetime.date.today())
    except ScrapeError as e:
        print(f"::error::Scrape failed, data.json not updated: {e}", file=sys.stderr)
        return 1

    write_json(args.out, data)
    append_history(args.history, data)
    print(f"Wrote {args.out}: {len(data['cpu'])} CPUs, {len(data['gpu'])} GPUs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
