"""
seed_db.py — Run once to create mock_splunk.db with realistic dummy data.
Data is generated around NOW so all time windows (-1h, -24h, -7d) return results.

Usage:  python seed_db.py
"""

import sqlite3
import random
import os
from datetime import datetime, timedelta

_HERE   = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "mock_splunk.db")


def rand_time(hours_ago_max: int, hours_ago_min: int = 0) -> str:
    """Random timestamp between now-hours_ago_max and now-hours_ago_min."""
    seconds = random.randint(hours_ago_min * 3600, hours_ago_max * 3600)
    t = datetime.now() - timedelta(seconds=seconds)
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def seed():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    status_mix = (["200"] * 60 + ["201"] * 5 + ["301"] * 5 +
                  ["404"] * 15 + ["500"] * 10 + ["503"] * 5)
    status_raw = ([200] * 60 + [301] * 5 + [400] * 5 +
                  [404] * 10 + [500] * 12 + [503] * 8)
    regions    = ["us-east-1", "eu-west-1", "ap-southeast-1"]
    hostnames  = ["kate-spade-outlet.vercel.app",
                  "coach.vercel.app",
                  "stuart-weitzman.vercel.app"]
    urls       = ["/api/checkout", "/api/product", "/api/cart",
                  "/api/search",   "/api/user",    "/api/orders"]
    brands     = ["coach", "kate-spade", "stuart-weitzman"]
    ak_hosts   = ["www.coach.com", "www.katespade.com", "www.stuartweitzman.com"]
    sites      = ["coach-us", "kate-spade-us", "stuart-weitzman-us",
                  "coach-eu", "kate-spade-eu"]
    statuses   = (["COMPLETED"] * 55 + ["NEW"] * 20 +
                  ["FAILED"]    * 10 + ["CANCELLED"] * 10 + ["PROCESSING"] * 5)

    # ── vercel_prod ────────────────────────────────────────────────────────────
    cur.execute("DROP TABLE IF EXISTS vercel_prod")
    cur.execute("""
        CREATE TABLE vercel_prod (
            _time TEXT, hostname TEXT, statusCode TEXT, url TEXT,
            method TEXT, duration INTEGER, region TEXT,
            deploymentId TEXT, projectName TEXT
        )
    """)
    rows = []
    # Heavy recent data — last 1h (300 rows guaranteed per hostname)
    for h in hostnames:
        for _ in range(300):
            rows.append((
                rand_time(1),               # within last 1 hour
                h,
                random.choice(status_mix),
                random.choice(urls),
                random.choice(["GET", "POST", "PUT"]),
                random.randint(40, 5000),
                random.choice(regions),
                f"dpl_{random.randint(10000,99999)}",
                h.split(".")[0],
            ))
    # Last 24h (500 rows)
    for _ in range(500):
        h = random.choice(hostnames)
        rows.append((
            rand_time(24, 1),
            h, random.choice(status_mix), random.choice(urls),
            random.choice(["GET", "POST"]), random.randint(40, 5000),
            random.choice(regions), f"dpl_{random.randint(10000,99999)}",
            h.split(".")[0],
        ))
    # Last 7d (1000 rows)
    for _ in range(1000):
        h = random.choice(hostnames)
        rows.append((
            rand_time(168, 24),
            h, random.choice(status_mix), random.choice(urls),
            "GET", random.randint(40, 5000), random.choice(regions),
            f"dpl_{random.randint(10000,99999)}", h.split(".")[0],
        ))
    cur.executemany("INSERT INTO vercel_prod VALUES (?,?,?,?,?,?,?,?,?)", rows)

    # ── vercel_non_prod ────────────────────────────────────────────────────────
    cur.execute("DROP TABLE IF EXISTS vercel_non_prod")
    cur.execute("""
        CREATE TABLE vercel_non_prod (
            _time TEXT, hostname TEXT, statusCode TEXT, url TEXT,
            method TEXT, duration INTEGER, region TEXT,
            deploymentId TEXT, projectName TEXT
        )
    """)
    np = []
    for _ in range(200):
        np.append((
            rand_time(24),
            "staging.kate-spade.vercel.app",
            random.choice(status_mix), random.choice(urls),
            "GET", random.randint(40, 3000), "us-east-1",
            f"dpl_{random.randint(10000,99999)}", "kate-spade-staging",
        ))
    cur.executemany("INSERT INTO vercel_non_prod VALUES (?,?,?,?,?,?,?,?,?)", np)

    # ── akamai_summary ─────────────────────────────────────────────────────────
    cur.execute("DROP TABLE IF EXISTS akamai_summary")
    cur.execute("""
        CREATE TABLE akamai_summary (
            _time TEXT, brand TEXT, hostname TEXT,
            Total_Count INTEGER, Success_Count INTEGER,
            Count_2xx INTEGER, Count_3xx INTEGER,
            Count_4xx INTEGER, Count_5xx INTEGER,
            Availability REAL, Stability REAL,
            "4xx_perc" REAL, "5xx_perc" REAL
        )
    """)
    ak = []
    # Last 1h — 20 rows per brand
    for bi in range(3):
        for _ in range(20):
            total = random.randint(2000, 10000)
            c4 = random.randint(20, 200); c5 = random.randint(5, 80)
            c3 = random.randint(10, 100); c2 = total - c4 - c5 - c3
            ak.append((rand_time(1), brands[bi], ak_hosts[bi],
                       total, c2, c2, c3, c4, c5,
                       round(c2/total*100, 2), round((c2+c4)/total*100, 2),
                       round(c4/total*100, 2), round(c5/total*100, 2)))
    # Last 24h — 50 rows per brand
    for bi in range(3):
        for _ in range(50):
            total = random.randint(2000, 10000)
            c4 = random.randint(20, 200); c5 = random.randint(5, 80)
            c3 = random.randint(10, 100); c2 = total - c4 - c5 - c3
            ak.append((rand_time(24, 1), brands[bi], ak_hosts[bi],
                       total, c2, c2, c3, c4, c5,
                       round(c2/total*100, 2), round((c2+c4)/total*100, 2),
                       round(c4/total*100, 2), round(c5/total*100, 2)))
    # Last 7d — 100 rows per brand
    for bi in range(3):
        for _ in range(100):
            total = random.randint(2000, 10000)
            c4 = random.randint(20, 200); c5 = random.randint(5, 80)
            c3 = random.randint(10, 100); c2 = total - c4 - c5 - c3
            ak.append((rand_time(168, 24), brands[bi], ak_hosts[bi],
                       total, c2, c2, c3, c4, c5,
                       round(c2/total*100, 2), round((c2+c4)/total*100, 2),
                       round(c4/total*100, 2), round(c5/total*100, 2)))
    cur.executemany("INSERT INTO akamai_summary VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", ak)

    # ── akamai raw ─────────────────────────────────────────────────────────────
    cur.execute("DROP TABLE IF EXISTS akamai")
    cur.execute("""
        CREATE TABLE akamai (
            _time TEXT, Request_host TEXT, Status_code INTEGER,
            url TEXT, brand TEXT, method TEXT,
            response_time INTEGER, client_ip TEXT, sourcetype TEXT
        )
    """)
    ak_raw = []
    for _ in range(300):   # last 1h
        bi = random.randint(0, 2)
        ak_raw.append((rand_time(1), ak_hosts[bi], random.choice(status_raw),
                       random.choice(["/","/products","/checkout","/cart"]),
                       brands[bi], random.choice(["GET","POST"]),
                       random.randint(50, 4000),
                       f"192.168.{random.randint(1,255)}.{random.randint(1,255)}",
                       "akamai:v2"))
    for _ in range(700):   # last 24h
        bi = random.randint(0, 2)
        ak_raw.append((rand_time(24, 1), ak_hosts[bi], random.choice(status_raw),
                       random.choice(["/","/products","/checkout"]),
                       brands[bi], "GET", random.randint(50, 4000),
                       f"192.168.{random.randint(1,255)}.{random.randint(1,255)}",
                       "akamai:v2"))
    cur.executemany("INSERT INTO akamai VALUES (?,?,?,?,?,?,?,?,?)", ak_raw)

    # ── sfcc_business_kpis ─────────────────────────────────────────────────────
    cur.execute("DROP TABLE IF EXISTS sfcc_business_kpis")
    cur.execute("""
        CREATE TABLE sfcc_business_kpis (
            creation_date TEXT, site_id TEXT, order_no TEXT,
            order_total REAL, currency_code TEXT,
            status TEXT, customer_no TEXT, source TEXT
        )
    """)
    sfcc = []
    order_num = 10000
    # Last 1h — 50 orders per site
    for site in sites:
        for _ in range(50):
            sfcc.append((
                rand_time(1),
                site, f"ORD-{order_num}",
                round(random.uniform(30, 1200), 2), "USD",
                random.choice(statuses),
                f"CUST-{random.randint(1000,9999)}", "created_orders",
            ))
            order_num += 1
    # Last 24h — 100 orders per site
    for site in sites:
        for _ in range(100):
            sfcc.append((
                rand_time(24, 1),
                site, f"ORD-{order_num}",
                round(random.uniform(30, 1200), 2), "USD",
                random.choice(statuses),
                f"CUST-{random.randint(1000,9999)}", "created_orders",
            ))
            order_num += 1
    # Last 7d — 200 orders per site
    for site in sites:
        for _ in range(200):
            sfcc.append((
                rand_time(168, 24),
                site, f"ORD-{order_num}",
                round(random.uniform(30, 1200), 2), "USD",
                random.choice(statuses),
                f"CUST-{random.randint(1000,9999)}", "created_orders",
            ))
            order_num += 1
    cur.executemany("INSERT INTO sfcc_business_kpis VALUES (?,?,?,?,?,?,?,?)", sfcc)

    # ── moovweb raw ────────────────────────────────────────────────────────────
    cur.execute("DROP TABLE IF EXISTS moovweb")
    cur.execute("""
        CREATE TABLE moovweb (
            _time TEXT, hostname TEXT, Status_code INTEGER,
            url TEXT, brand TEXT, method TEXT,
            duration INTEGER, sourcetype TEXT
        )
    """)
    mv = []
    for _ in range(200):   # last 1h
        mv.append((rand_time(1),
                   random.choice(["m.coach.com","m.katespade.com"]),
                   random.choice(status_raw),
                   random.choice(["/","/products","/checkout"]),
                   random.choice(["coach","kate-spade"]),
                   "GET", random.randint(100, 3000), "moovweb:access"))
    for _ in range(500):   # last 24h
        mv.append((rand_time(24, 1),
                   random.choice(["m.coach.com","m.katespade.com"]),
                   random.choice(status_raw),
                   random.choice(["/","/products","/checkout"]),
                   random.choice(["coach","kate-spade"]),
                   "GET", random.randint(100, 3000), "moovweb:access"))
    cur.executemany("INSERT INTO moovweb VALUES (?,?,?,?,?,?,?,?)", mv)

    # ── moovweb_summary ────────────────────────────────────────────────────────
    cur.execute("DROP TABLE IF EXISTS moovweb_summary")
    cur.execute("""
        CREATE TABLE moovweb_summary (
            _time TEXT, brand TEXT,
            Total_Count INTEGER, Count_4xx INTEGER,
            Count_5xx INTEGER, Availability REAL
        )
    """)
    ms = []
    for b in ["coach", "kate-spade"]:
        for _ in range(24):   # one row per hour for last 24h
            total = random.randint(500, 3000)
            c4 = random.randint(5, 60); c5 = random.randint(2, 30)
            ms.append((rand_time(24), b, total, c4, c5,
                       round((total-c4-c5)/total*100, 2)))
    cur.executemany("INSERT INTO moovweb_summary VALUES (?,?,?,?,?,?)", ms)

    conn.commit()
    conn.close()

    # Print summary
    conn2 = sqlite3.connect(DB_PATH)
    cur2  = conn2.cursor()
    tables = ["vercel_prod","vercel_non_prod","akamai_summary",
              "akamai","sfcc_business_kpis","moovweb","moovweb_summary"]
    print(f"\n✅  Seeded: {DB_PATH}\n")
    print(f"  {'Table':<25} {'Total':>7}  {'Last 1h':>8}  {'Last 24h':>9}")
    print(f"  {'-'*25} {'-'*7}  {'-'*8}  {'-'*9}")
    for t in tables:
        time_col = "creation_date" if t == "sfcc_business_kpis" else "_time"
        total = cur2.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        h1    = cur2.execute(
            f"SELECT COUNT(*) FROM {t} WHERE {time_col} >= datetime('now','-1 hours')"
        ).fetchone()[0]
        h24   = cur2.execute(
            f"SELECT COUNT(*) FROM {t} WHERE {time_col} >= datetime('now','-24 hours')"
        ).fetchone()[0]
        print(f"  {t:<25} {total:>7}  {h1:>8}  {h24:>9}")
    conn2.close()
    print()


if __name__ == "__main__":
    seed()
