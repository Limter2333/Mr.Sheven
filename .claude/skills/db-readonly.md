---
name: db-readonly
description: Run safe read-only queries against MySQL or PostgreSQL for data inspection, reporting, and troubleshooting
user_invocable: true
---

# Database Read-Only Query

Run safe read-only queries against MySQL or PostgreSQL. Only SELECT/WITH/EXPLAIN are allowed; all write SQL is blocked.

## Connection

Set environment variables before running:

**PostgreSQL:** `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`
**MySQL:** `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`

## Usage

```bash
# PostgreSQL
bash .claude/skills/scripts/db_readonly.sh postgres "SELECT * FROM employees LIMIT 10"

# MySQL
bash .claude/skills/scripts/db_readonly.sh mysql "SELECT COUNT(*) FROM employees"

# With output format
bash .claude/skills/scripts/db_readonly.sh mysql "SELECT * FROM employees" --format json
bash .claude/skills/scripts/db_readonly.sh mysql "SELECT * FROM employees" --format csv --out /tmp/report.csv
```

Formats: `table` (default), `csv`, `tsv`, `json`

## Safety Rules

- Only `SELECT`, `WITH`, `EXPLAIN` statements allowed
- Blocked keywords: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, REPLACE, MERGE, CALL, DO
- No write operations of any kind
- Always use `LIMIT` for exploratory queries

## Query Cookbook

| Task | Query |
|------|-------|
| Show tables | `SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()` |
| Count rows | `SELECT COUNT(*) AS cnt FROM <table>` |
| Sample rows | `SELECT * FROM <table> LIMIT 10` |
| Top values | `SELECT <col>, COUNT(*) AS freq FROM <table> GROUP BY <col> ORDER BY freq DESC LIMIT 20` |
| Date trends | `SELECT DATE(<col>) AS d, COUNT(*) FROM <table> GROUP BY d ORDER BY d DESC LIMIT 30` |
