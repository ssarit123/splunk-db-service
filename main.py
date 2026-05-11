"""
splunk-db-service  —  REST API over a local SQLite mock Splunk database.
Port : 8002  (set DB_SERVICE_PORT env var to override)

Endpoints:
  GET  /health                          liveness check
  GET  /indexes                         list all indexes
  GET  /indexes/{index_name}            info (min/max time, event count, fields)
  GET  /indexes/{index_name}/metadata   sources / sourcetypes / hosts
  POST /query                           run SPL → returns rows as JSON
  POST /sql                             run raw SQL (dev/debug only)
  GET  /tables                          list all SQLite tables + row counts
"""

import json
import os
import re
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from spl_to_sql import spl_to_sql

# ─── Config ───────────────────────────────────────────────────────────────────

_HERE   = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(_HERE, "mock_splunk.db"))

app = FastAPI(
    title="Splunk DB Service",
    description="REST API over a local SQLite mock Splunk database",
    version="1.0.0",
)

# ─── Metadata catalogue ───────────────────────────────────────────────────────

INDEX_CATALOGUE = {
    "vercel_prod": {
        "disabled": "0", "data_type": "event", "retention": 90,
        "sources":     ["vercel-prod-logs"],
        "sourcetypes": ["vercel:request"],
        "hosts":       ["kate-spade-outlet.vercel.app",
                        "coach.vercel.app",
                        "stuart-weitzman.vercel.app"],
    },
    "vercel_non_prod": {
        "disabled": "0", "data_type": "event", "retention": 30,
        "sources":     ["vercel-non-prod-logs"],
        "sourcetypes": ["vercel:request"],
        "hosts":       ["staging.kate-spade.vercel.app"],
    },
    "akamai_summary": {
        "disabled": "0", "data_type": "event", "retention": 365,
        "sources":     ["akamai-summary-feed"],
        "sourcetypes": ["akamai:summary"],
        "hosts":       ["www.coach.com", "www.katespade.com",
                        "www.stuartweitzman.com"],
    },
    "akamai": {
        "disabled": "0", "data_type": "event", "retention": 90,
        "sources":     ["akamai-raw-feed"],
        "sourcetypes": ["akamai:v2"],
        "hosts":       ["www.coach.com", "www.katespade.com",
                        "www.stuartweitzman.com"],
    },
    "sfcc_business_kpis": {
        "disabled": "0", "data_type": "event", "retention": 365,
        "sources":     ["created_orders", "updated_orders",
                        "inventory", "job_statuses"],
        "sourcetypes": ["sfcc:order"],
        "hosts":       ["coach-us", "kate-spade-us", "stuart-weitzman-us"],
    },
    "moovweb": {
        "disabled": "0", "data_type": "event", "retention": 60,
        "sources":     ["moovweb-access"],
        "sourcetypes": ["moovweb:access"],
        "hosts":       ["m.coach.com", "m.katespade.com"],
    },
    "moovweb_summary": {
        "disabled": "0", "data_type": "event", "retention": 180,
        "sources":     ["moovweb-summary"],
        "sourcetypes": ["moovweb:summary"],
        "hosts":       ["m.coach.com", "m.katespade.com"],
    },
}

_ALIAS = {
    "akamai_json": "akamai", "akamai_perf": "akamai",
    "sfcc_kpi": "sfcc_business_kpis", "sfcc_logs": "sfcc_business_kpis",
    "sfcc_ecdn_logs": "sfcc_business_kpis",
    "moovweb_perf": "moovweb",
    "master_summary": "akamai_summary",
    "new_master_summary": "akamai_summary",
    "stability_summary": "akamai_summary",
    "cdn": "akamai", "ecdn_logs": "akamai",
}

def _resolve(name: str) -> str:
    return _ALIAS.get(name, name)


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        raise HTTPException(
            status_code=503,
            detail=f"Database not found at {DB_PATH}. Run: python seed_db.py",
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _run(sql: str) -> list[dict]:
    conn = _get_conn()
    try:
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
        return rows
    except sqlite3.Error as e:
        raise HTTPException(status_code=400, detail=f"SQLite error: {e}")
    finally:
        conn.close()


# ─── Request models ───────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    spl: str

class SqlRequest(BaseModel):
    sql: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    exists = os.path.exists(DB_PATH)
    tables = []
    if exists:
        try:
            tables = [r["name"] for r in _run(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )]
        except Exception:
            pass
    return {
        "status":   "ok" if exists else "db_missing",
        "db_path":  DB_PATH,
        "tables":   tables,
    }


@app.get("/indexes")
def list_indexes(row_limit: int = 200):
    """List all available Splunk indexes."""
    results = [
        {
            "title":    name,
            "disabled": meta["disabled"],
            "datatype": meta["data_type"],
        }
        for name, meta in list(INDEX_CATALOGUE.items())[:row_limit]
    ]
    return {"results": results}


@app.get("/indexes/{index_name}")
def get_index_info(index_name: str):
    """Return min/max event time, total events, field list for one index."""
    table = _resolve(index_name)
    meta  = INDEX_CATALOGUE.get(index_name) or INDEX_CATALOGUE.get(table, {})

    # time range + count
    time_col = "creation_date" if "sfcc" in table else "_time"
    try:
        row = _run(
            f"SELECT MIN({time_col}) AS min_t, MAX({time_col}) AS max_t, "
            f"COUNT(*) AS total FROM {table}"
        )[0]
    except Exception:
        row = {"min_t": "", "max_t": "", "total": 0}

    # field list
    try:
        cols = _run(f"PRAGMA table_info({table})")
        fields = ", ".join(c["name"] for c in cols)
    except Exception:
        fields = ""

    return {
        "name":              index_name,
        "title":             index_name,
        "disabled":          meta.get("disabled", "0"),
        "minTime":           row.get("min_t", ""),
        "maxTime":           row.get("max_t", ""),
        "totalEventCount":   str(row.get("total", 0)),
        "currentDBSizeMB":   "128",
        "frozenTimePeriodInSecs": meta.get("retention", 90) * 86400,
        "datatype":          meta.get("data_type", "event"),
        "fields":            fields,
    }


@app.get("/indexes/{index_name}/metadata")
def get_metadata(index_name: str, type: str = "sources"):
    """
    Return sources / sourcetypes / hosts for one index.
    type must be one of:  sources | sourcetypes | hosts
    """
    lookup = _resolve(index_name)
    meta   = INDEX_CATALOGUE.get(lookup, {})
    values = meta.get(type, [])
    return {"results": [{"value": v, "count": 0} for v in values]}


@app.post("/query")
def run_query(body: QueryRequest):
    """
    Execute an SPL query against the SQLite database.
    SPL is translated to SQL internally via spl_to_sql.py.
    """
    spl = body.spl.strip()
    if not spl:
        raise HTTPException(status_code=400, detail="spl must not be empty")

    try:
        table, sql = spl_to_sql(spl)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SPL translation error: {e}")

    # PRAGMA returns column-info rows — reshape to field list
    if "PRAGMA" in sql.upper():
        rows = _run(sql)
        rows = [{"field": r.get("name", "")} for r in rows]
    else:
        rows = _run(sql)

    return {
        "table":   table,
        "sql":     sql,
        "results": rows,
        "count":   len(rows),
    }


@app.post("/sql")
def run_raw_sql(body: SqlRequest):
    """Run raw SQL directly (development / debugging only)."""
    sql = body.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="sql must not be empty")

    # Basic safety guard — read-only
    if re.match(r'\s*(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE)', sql, re.IGNORECASE):
        raise HTTPException(status_code=403,
                            detail="Only SELECT and PRAGMA statements are allowed")
    rows = _run(sql)
    return {"results": rows, "count": len(rows)}


@app.get("/tables")
def list_tables():
    """List all SQLite tables and their row counts."""
    tables = _run("SELECT name FROM sqlite_master WHERE type='table'")
    out = []
    for t in tables:
        name = t["name"]
        try:
            count = _run(f"SELECT COUNT(*) AS n FROM {name}")[0]["n"]
        except Exception:
            count = -1
        out.append({"table": name, "rows": count})
    return {"tables": out}
