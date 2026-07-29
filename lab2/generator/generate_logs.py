#!/usr/bin/env python3
"""Lab 2 — ShopFast log generator.

Writes three interleaved log sources into ../logs/ (next to this script's
parent directory):
  - access.log  : nginx combined format (public client IPs, /healthz noise)
  - app.log     : 2026-07-26T14:03:11Z|payment|ERROR|order=1234|amount=59.90|msg=...
  - orders.csv  : order_id,ts,customer_country,items,amount

~2% of lines in each source are deliberately malformed. This is a feature.

Usage:
    python3 generate_logs.py               # continuous mode: ~5 lines/s, Ctrl-C to stop
    python3 generate_logs.py --batch 500   # write 500 events immediately and exit

Deterministic content (seed 2026); timestamps are wall-clock (batch mode
spreads them over the last hour).
"""
import argparse
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

random.seed(2026)

LOGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")

# Public IPs (incl. documentation/demo ranges known to the GeoLite2 test set)
PUBLIC_IPS = ["81.2.69.142", "81.2.69.160", "8.8.8.8", "1.1.1.1",
              "212.27.48.10", "90.85.12.34", "62.210.16.62",       # FR
              "216.160.83.56", "34.120.10.5", "67.43.156.1",       # US/CA
              "210.140.92.183", "133.242.0.3",                     # JP
              "213.180.204.3", "77.88.55.77",                      # RU
              "200.160.2.3", "186.202.153.66",                     # BR
              "41.231.21.1", "196.25.255.250"]                     # TN/ZA

PATHS = ["/", "/product/1042", "/product/887", "/product/2210", "/cart",
         "/checkout", "/api/v1/stock", "/static/app.js", "/static/style.css"]
UAS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
       "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Safari/605.1.15",
       "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Mobile/15E148",
       "curl/8.5.0"]
REFERRERS = ["-", "https://www.google.com/", "https://shopfast.example/",
             "https://twitter.com/"]

SERVICES = ["checkout", "payment", "stock"]
LEVELS = ["INFO", "INFO", "INFO", "INFO", "WARN", "ERROR"]
MSGS = {
    "INFO":  ["checkout started", "payment captured", "stock reserved",
              "order confirmed", "invoice generated"],
    "WARN":  ["retrying gateway call", "slow response from bank",
              "stock level low", "payment failed, cart preserved"],
    "ERROR": ["card declined", "gateway timeout after 30s",
              "stock service unreachable", "order rollback"],
}
COUNTRIES = ["FR", "US", "GB", "JP", "DE", "BR", "ES", "IT"]

MALFORMED_RATE = 0.02
HEALTHZ_RATE = 0.10


def apache_ts(dt):
    return dt.strftime("%d/%b/%Y:%H:%M:%S +0000")


def iso_ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def nginx_line(dt):
    if random.random() < MALFORMED_RATE:
        return random.choice([
            "corrupted write: @@@ %d" % random.randint(1000, 9999),
            '81.2.69.142 - - [26/Jul/2026 "GET /cart HTTP',   # truncated
            '- - - [] "" xx yy',
        ])
    ip = random.choice(PUBLIC_IPS)
    path = "/healthz" if random.random() < HEALTHZ_RATE else random.choice(PATHS)
    status = random.choices([200, 301, 404, 500, 502], [88, 3, 5, 2, 2])[0]
    return (f'{ip} - - [{apache_ts(dt)}] "GET {path} HTTP/1.1" {status} '
            f'{random.randint(180, 42000)} "{random.choice(REFERRERS)}" '
            f'"{random.choice(UAS)}"')


def app_line(dt):
    if random.random() < MALFORMED_RATE:
        return random.choice([
            f"{iso_ts(dt)}|payment|ERROR|order=|msg=",
            f"{iso_ts(dt)}|payment|FATAL-OOM",
            "null",
        ])
    service = random.choice(SERVICES)
    level = random.choice(LEVELS)
    return (f"{iso_ts(dt)}|{service}|{level}|order={random.randint(10000, 99999)}"
            f"|amount={random.uniform(5, 400):.2f}|msg={random.choice(MSGS[level])}")


def csv_line(dt):
    if random.random() < MALFORMED_RATE:
        return random.choice([
            f"{random.randint(10000, 99999)},{iso_ts(dt)},FR",          # short row
            f"{random.randint(10000, 99999)},{iso_ts(dt)},FR,two,N/A",  # bad types
        ])
    return (f"{random.randint(10000, 99999)},{iso_ts(dt)},"
            f"{random.choice(COUNTRIES)},{random.randint(1, 8)},"
            f"{random.uniform(5, 600):.2f}")


def emit(dt):
    """Return (filename, line) for one event."""
    kind = random.choices(["nginx", "app", "csv"], [6, 3, 1])[0]
    if kind == "nginx":
        return "access.log", nginx_line(dt)
    if kind == "app":
        return "app.log", app_line(dt)
    return "orders.csv", csv_line(dt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, metavar="N",
                    help="write N events spread over the last hour, then exit")
    args = ap.parse_args()

    os.makedirs(LOGS, exist_ok=True)
    files = {n: open(os.path.join(LOGS, n), "a", buffering=1)
             for n in ("access.log", "app.log", "orders.csv")}
    written = 0
    try:
        if args.batch:
            start = datetime.now(timezone.utc) - timedelta(hours=1)
            step = timedelta(hours=1) / args.batch
            for i in range(args.batch):
                name, line = emit(start + i * step)
                files[name].write(line + "\n")
                written += 1
            print(f"wrote {written} events into {os.path.abspath(LOGS)}/")
        else:
            print(f"streaming ~5 events/s into {os.path.abspath(LOGS)}/ "
                  "(Ctrl-C to stop)")
            while True:
                name, line = emit(datetime.now(timezone.utc))
                files[name].write(line + "\n")
                written += 1
                if written % 100 == 0:
                    print(f"  {written} events...", file=sys.stderr)
                time.sleep(random.uniform(0.1, 0.3))
    except KeyboardInterrupt:
        print(f"\nstopped after {written} events")
    finally:
        for f in files.values():
            f.close()


if __name__ == "__main__":
    main()
