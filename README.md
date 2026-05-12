# splunk-db-service

First deployment

Second-deployment

Thirld develpment while demo to siva 11127

ehudeheiuhe

11 May 9:000

worked 12 may

Standalone REST API that wraps a local SQLite mock Splunk database.  
The MCP server calls this service instead of hitting a real Splunk Cloud instance.

```
splunk-mcp-server  ──HTTP──►  splunk-db-service  ──►  mock_splunk.db
(port 8001)                   (port 8002)              (SQLite)
```

---

## Project Structure

```
splunk-db-service/
├── main.py          ← FastAPI REST API (7 endpoints)
├── spl_to_sql.py    ← SPL → SQLite SQL translator
├── seed_db.py       ← Run once to create the database
├── requirements.txt
├── .gitignore
└── mock_splunk.db   ← Generated (gitignored)
```

---

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Seed the database (once)
python seed_db.py

# 3. Start
uvicorn main:app --port 8002 --reload
```

Swagger UI: `http://localhost:8002/docs`

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Liveness check + table list |
| `GET`  | `/indexes` | List all available indexes |
| `GET`  | `/indexes/{name}` | Min/max time, event count, fields |
| `GET`  | `/indexes/{name}/metadata?type=sources` | sources / sourcetypes / hosts |
| `POST` | `/query` | Run SPL query → rows (translated to SQL) |
| `POST` | `/sql` | Run raw SQL (debug only, read-only) |
| `GET`  | `/tables` | All SQLite tables + row counts |

### POST /query — example

```bash
curl -X POST http://localhost:8002/query \
  -H "Content-Type: application/json" \
  -d '{"spl": "index=vercel_prod hostname=kate-spade-outlet.vercel.app earliest=-1h | stats count as total_failures"}'
```

Response:
```json
{
  "table": "vercel_prod",
  "sql": "SELECT COUNT(*) AS total_failures ...",
  "results": [{"total_failures": 142, "server_errors": 23, "client_errors": 119}],
  "count": 1
}
```

---

## Mock Data

| Table | Rows | Platforms |
|-------|------|-----------|
| `vercel_prod` | 3 000 | Vercel production |
| `vercel_non_prod` | 500 | Vercel staging |
| `akamai_summary` | 500 | Akamai pre-aggregated |
| `akamai` | 2 000 | Akamai raw events |
| `sfcc_business_kpis` | 800 | SFCC orders |
| `moovweb` | 1 000 | Moovweb raw |
| `moovweb_summary` | 200 | Moovweb aggregated |

---

## Custom DB Path

```bash
export DB_PATH=/path/to/your/mock_splunk.db
uvicorn main:app --port 8002
```


# Go into the project
cd splunk-db-service

# Create virtual env
python3 -m venv venv

# Activate it
source venv/bin/activate          # Mac / Linux
# venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Seed the database (only once)
python seed_db.py

# Start the server
uvicorn main:app --port 8002 --reload
