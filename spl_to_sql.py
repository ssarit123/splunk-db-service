"""
spl_to_sql.py
Translates SPL patterns → SQLite SQL.
Covers all platforms: vercel, akamai_summary, akamai (raw), sfcc, moovweb.
"""

import re


# ─── Time window ──────────────────────────────────────────────────────────────

def _minutes(earliest: str) -> int:
    m = re.match(r"-(\d+)([hdm])", earliest.strip())
    if not m:
        return 60
    n, u = int(m.group(1)), m.group(2)
    return {"h": 60, "d": 1440, "m": 1}[u] * n


# ─── Clause extractors ────────────────────────────────────────────────────────

def _extract_index(spl: str) -> str:
    m = re.search(r'index\s*=\s*["\']?(\w+)["\']?', spl, re.IGNORECASE)
    return m.group(1) if m else "vercel_prod"

def _time_clause(spl: str, col: str = "_time") -> str:
    m = re.search(r'earliest\s*=\s*(-[\w@]+)', spl, re.IGNORECASE)
    if not m:
        return ""
    mins = _minutes(m.group(1))
    return f"{col} >= datetime('now', '-{mins} minutes')"

def _hostname_clause(spl: str, col: str = "hostname") -> str:
    for field in ("hostname", "Request_host"):
        m = re.search(rf'{field}\s*=\s*["\']?([\w.\-]+)["\']?', spl, re.IGNORECASE)
        if m:
            return f"{col} = '{m.group(1)}'"
    return ""

def _brand_clause(spl: str) -> str:
    m = re.search(r'brand\s*=\s*["\']?([\w\-]+)["\']?', spl, re.IGNORECASE)
    return f"brand = '{m.group(1)}'" if m else ""

def _site_id_clause(spl: str) -> str:
    m = re.search(r'site_id\s*=\s*["\']?([\w\-]+)["\']?', spl, re.IGNORECASE)
    return f"site_id = '{m.group(1)}'" if m else ""

def _statuscode_clause(spl: str) -> str:
    m = re.search(r'statusCode\s*=\s*["\']?(\d)\*["\']?', spl, re.IGNORECASE)
    if m:
        return f"statusCode LIKE '{m.group(1)}%'"
    if re.search(r'statusCode.*4\*.*OR.*statusCode.*5\*', spl, re.IGNORECASE):
        return "(statusCode LIKE '4%' OR statusCode LIKE '5%')"
    return ""

def _source_clause(spl: str) -> str:
    m = re.search(r'source\s*=\s*["\']?([\w\-_/]+)["\']?', spl, re.IGNORECASE)
    return f"source = '{m.group(1)}'" if m else ""

def _sourcetype_clause(spl: str) -> str:
    m = re.search(r'sourcetype\s*=\s*["\']?([\w\-_:]+)["\']?', spl, re.IGNORECASE)
    return f"sourcetype = '{m.group(1)}'" if m else ""

def _where(clauses: list) -> str:
    v = [c for c in clauses if c]
    return "WHERE " + " AND ".join(v) if v else ""

def _span(spl: str):
    m = re.search(r'span\s*=\s*(\d+)([hdm])', spl, re.IGNORECASE)
    if not m:
        return "strftime('%Y-%m-%dT%H:00:00', _time)", "_bucket"
    n, u = int(m.group(1)), m.group(2)
    if u == "m":
        return (
            f"strftime('%Y-%m-%dT%H:', _time) || "
            f"printf('%02d',(CAST(strftime('%M',_time) AS INT)/{n})*{n}) || ':00'",
            "_bucket"
        )
    if u == "h":
        return "strftime('%Y-%m-%dT%H:00:00', _time)", "_bucket"
    return "strftime('%Y-%m-%d', _time)", "_bucket"

def _is_timechart(spl: str) -> bool:
    return bool(re.search(r'\|\s*timechart', spl, re.IGNORECASE))

def _is_stats(spl: str) -> bool:
    return bool(re.search(r'\|\s*stats', spl, re.IGNORECASE))


# ─── Per-platform SQL builders ─────────────────────────────────────────────────

def _vercel(spl: str, table: str) -> str:
    tc = _time_clause(spl)
    hc = _hostname_clause(spl)
    sc = _statuscode_clause(spl) or "(statusCode LIKE '4%' OR statusCode LIKE '5%')"

    if _is_timechart(spl):
        fmt, bkt = _span(spl)
        return f"""
SELECT {fmt} AS {bkt},
       SUM(CASE WHEN statusCode LIKE '4%' THEN 1 ELSE 0 END) AS client_errors,
       SUM(CASE WHEN statusCode LIKE '5%' THEN 1 ELSE 0 END) AS server_errors,
       COUNT(*) AS total_requests
FROM {table}
{_where([tc, hc, sc])}
GROUP BY {bkt} ORDER BY {bkt} LIMIT 200""".strip()

    if _is_stats(spl):
        return f"""
SELECT COUNT(*) AS total_failures,
       SUM(CASE WHEN CAST(statusCode AS INT)>=500 THEN 1 ELSE 0 END) AS server_errors,
       SUM(CASE WHEN CAST(statusCode AS INT)>=400
                AND CAST(statusCode AS INT)<500  THEN 1 ELSE 0 END) AS client_errors
FROM {table}
{_where([tc, hc, sc])}""".strip()

    return f"SELECT * FROM {table} {_where([tc, hc])} ORDER BY _time DESC LIMIT 500"


def _akamai_summary(spl: str, table: str) -> str:
    tc = _time_clause(spl)
    fc = _brand_clause(spl) or _hostname_clause(spl, "hostname")

    if _is_timechart(spl):
        fmt, bkt = _span(spl)
        return f"""
SELECT {fmt} AS {bkt},
       SUM(Total_Count) AS total_requests,
       SUM(Count_4xx)   AS client_errors,
       SUM(Count_5xx)   AS server_errors,
       AVG(Availability) AS availability
FROM {table}
{_where([tc, fc])}
GROUP BY {bkt} ORDER BY {bkt} LIMIT 200""".strip()

    if _is_stats(spl):
        return f"""
SELECT SUM(Total_Count)   AS total_requests,
       SUM(Success_Count) AS success_requests,
       SUM(Count_4xx)     AS client_errors,
       SUM(Count_5xx)     AS server_errors,
       AVG(Availability)  AS availability,
       AVG(Stability)     AS stability
FROM {table}
{_where([tc, fc])}""".strip()

    return f"SELECT * FROM {table} {_where([tc, fc])} ORDER BY _time DESC LIMIT 200"


def _akamai_raw(spl: str, table: str) -> str:
    tc  = _time_clause(spl)
    hc  = _hostname_clause(spl, "Request_host")
    src = _sourcetype_clause(spl)
    sc  = "Status_code > 400" if re.search(r'Status_code\s*>', spl) else ""

    if _is_timechart(spl):
        fmt, bkt = _span(spl)
        return f"""
SELECT {fmt} AS {bkt},
       SUM(CASE WHEN Status_code>=500 THEN 1 ELSE 0 END) AS server_errors,
       SUM(CASE WHEN Status_code>=400 AND Status_code<500 THEN 1 ELSE 0 END) AS client_errors,
       COUNT(*) AS total_failures
FROM {table}
{_where([tc, hc, src, sc or "Status_code > 400"])}
GROUP BY {bkt} ORDER BY {bkt} LIMIT 200""".strip()

    if _is_stats(spl):
        return f"""
SELECT COUNT(*) AS total_failures,
       SUM(CASE WHEN Status_code>=500 THEN 1 ELSE 0 END) AS server_errors,
       SUM(CASE WHEN Status_code>=400 AND Status_code<500 THEN 1 ELSE 0 END) AS client_errors
FROM {table}
{_where([tc, hc, src])}""".strip()

    return f"SELECT * FROM {table} {_where([tc, hc, src])} ORDER BY _time DESC LIMIT 500"


def _sfcc(spl: str, table: str) -> str:
    tc   = _time_clause(spl, "creation_date")
    sc   = _site_id_clause(spl)
    src  = _source_clause(spl)

    if _is_timechart(spl):
        fmt, bkt = _span(spl)
        fmt = fmt.replace("_time", "creation_date")
        return f"""
SELECT {fmt} AS {bkt},
       COUNT(DISTINCT order_no) AS total_orders,
       SUM(order_total)         AS revenue
FROM {table}
{_where([tc, sc, src])}
GROUP BY {bkt} ORDER BY {bkt} LIMIT 200""".strip()

    if _is_stats(spl):
        if re.search(r'by\s+status', spl, re.IGNORECASE):
            return f"""
SELECT status, COUNT(DISTINCT order_no) AS total_orders
FROM {table}
{_where([tc, sc, src])}
GROUP BY status ORDER BY total_orders DESC""".strip()
        return f"""
SELECT COUNT(DISTINCT order_no) AS total_orders,
       SUM(order_total)         AS total_revenue,
       AVG(order_total)         AS avg_order_value,
       MIN(order_total)         AS min_order,
       MAX(order_total)         AS max_order
FROM {table}
{_where([tc, sc, src])}""".strip()

    return f"SELECT * FROM {table} {_where([tc, sc, src])} ORDER BY creation_date DESC LIMIT 500"


def _moovweb(spl: str, table: str) -> str:
    tc = _time_clause(spl)
    hc = _hostname_clause(spl)
    bc = _brand_clause(spl)

    if "summary" in table:
        if _is_stats(spl):
            return f"""
SELECT SUM(Total_Count) AS total_requests,
       SUM(Count_4xx)   AS client_errors,
       SUM(Count_5xx)   AS server_errors,
       AVG(Availability) AS availability
FROM {table}
{_where([tc, bc])}""".strip()
        if _is_timechart(spl):
            fmt, bkt = _span(spl)
            return f"""
SELECT {fmt} AS {bkt},
       SUM(Total_Count) AS requests,
       SUM(Count_4xx)   AS client_errors,
       SUM(Count_5xx)   AS server_errors
FROM {table}
{_where([tc, bc])}
GROUP BY {bkt} ORDER BY {bkt} LIMIT 200""".strip()
        return f"SELECT * FROM {table} {_where([tc, bc])} ORDER BY _time DESC LIMIT 200"

    if _is_stats(spl):
        return f"""
SELECT COUNT(*) AS total_requests,
       SUM(CASE WHEN Status_code>=500 THEN 1 ELSE 0 END) AS server_errors,
       SUM(CASE WHEN Status_code>=400 AND Status_code<500 THEN 1 ELSE 0 END) AS client_errors
FROM {table}
{_where([tc, hc or bc])}""".strip()

    return f"SELECT * FROM {table} {_where([tc, hc or bc])} ORDER BY _time DESC LIMIT 500"


def _meta_query(spl: str) -> tuple | None:
    table = _resolve_table(_extract_index(spl))
    if re.search(r'fieldsummary', spl, re.IGNORECASE):
        return table, f"PRAGMA table_info({table})"
    if re.search(r'stats\s+min\(_time\)', spl, re.IGNORECASE):
        col = "creation_date" if "sfcc" in table else "_time"
        return table, f"SELECT MIN({col}) AS min_t, MAX({col}) AS max_t FROM {table}"
    return None


_ALIAS = {
    "akamai_json": "akamai", "akamai_perf": "akamai",
    "sfcc_kpi": "sfcc_business_kpis", "sfcc_logs": "sfcc_business_kpis",
    "sfcc_ecdn_logs": "sfcc_business_kpis",
    "moovweb_perf": "moovweb",
    "master_summary": "akamai_summary", "new_master_summary": "akamai_summary",
    "stability_summary": "akamai_summary",
    "cdn": "akamai", "ecdn_logs": "akamai",
}

def _resolve_table(index: str) -> str:
    return _ALIAS.get(index, index)


# ─── Public entry point ───────────────────────────────────────────────────────

def spl_to_sql(spl: str) -> tuple:
    """Returns (table_name, sql_string)."""
    spl = spl.strip()
    meta = _meta_query(spl)
    if meta:
        return meta

    table = _resolve_table(_extract_index(spl))

    if "vercel" in table:
        return table, _vercel(spl, table)
    if table == "akamai_summary":
        return table, _akamai_summary(spl, table)
    if "akamai" in table:
        return table, _akamai_raw(spl, table)
    if "sfcc" in table:
        return table, _sfcc(spl, table)
    if "moovweb" in table:
        return table, _moovweb(spl, table)

    return table, f"SELECT * FROM {table} ORDER BY _time DESC LIMIT 200"
