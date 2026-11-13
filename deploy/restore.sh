#!/bin/sh
set -eu
export PGCONNECT_TIMEOUT=5
export PGPASSWORD="$(sed 's/\r$//' /run/secrets/pg_admin_password)"
export CEVAMI_WEB_PASSWORD="$(sed 's/\r$//' /run/secrets/web_db_password)"
if [ "${#CEVAMI_WEB_PASSWORD}" -lt 48 ] || [ "${#PGPASSWORD}" -lt 48 ]; then
  echo 'Secret files are missing or too short.' >&2; exit 1
fi
schema_count=$(psql -X -A -t -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM pg_namespace WHERE nspname='hadis'")
role_count=$(psql -X -A -t -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM pg_roles WHERE rolname='cevami_web'")
if [ "$schema_count" != "0" ] || [ "$role_count" != "0" ]; then
  echo 'Existing schema or reader role found; nothing was replaced.' >&2; exit 1
fi
workdir=$(mktemp -d /tmp/cevami-restore.XXXXXXXX)
trap 'rm -f "$workdir/begin.sql" "$workdir/schema.sql" "$workdir/reader.sql"; rmdir "$workdir"' EXIT HUP INT TERM
# Finish and check SQL generation before opening the transaction. A failed
# producer must never let psql commit a truncated stream of restore commands.
pg_restore --no-owner --no-privileges --schema=hadis --file="$workdir/schema.sql" /workspace/data/postgres/working.dump
printf '%s\n' 'CREATE SCHEMA hadis;' > "$workdir/begin.sql"
cat > "$workdir/reader.sql" <<'SQL'
\getenv reader_password CEVAMI_WEB_PASSWORD
CREATE ROLE cevami_web LOGIN PASSWORD :'reader_password' CONNECTION LIMIT 20;
REVOKE ALL ON DATABASE cevami FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE cevami TO cevami_web;
GRANT USAGE ON SCHEMA hadis TO cevami_web;
GRANT SELECT ON ALL TABLES IN SCHEMA hadis TO cevami_web;
ALTER DEFAULT PRIVILEGES FOR ROLE cevami_owner IN SCHEMA hadis GRANT SELECT ON TABLES TO cevami_web;
ALTER ROLE cevami_web SET default_transaction_read_only=on;
ALTER ROLE cevami_web SET statement_timeout='5s';
ALTER ROLE cevami_web SET lock_timeout='1s';
ALTER ROLE cevami_web SET idle_in_transaction_session_timeout='5s';
SQL
psql -X --single-transaction -v ON_ERROR_STOP=1 -f "$workdir/begin.sql" -f "$workdir/schema.sql" -f "$workdir/reader.sql"
unset PGPASSWORD CEVAMI_WEB_PASSWORD
echo 'Working schema restored; reader role has SELECT only.'
