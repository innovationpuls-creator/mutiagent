#!/usr/bin/env bash
set -euo pipefail

: "${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD is required}"

psql --set=ON_ERROR_STOP=1 \
  --set=app_password="$POSTGRES_APP_PASSWORD" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" <<'SQL'
SELECT format(
  'CREATE ROLE onetree_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
  :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'onetree_app') \gexec

ALTER ROLE onetree_app
  WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
SELECT format('ALTER ROLE onetree_app PASSWORD %L', :'app_password') \gexec

GRANT CONNECT ON DATABASE onetree TO onetree_app;
GRANT USAGE, CREATE ON SCHEMA public TO onetree_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO onetree_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO onetree_app;
ALTER DEFAULT PRIVILEGES FOR ROLE onetree_maintenance IN SCHEMA public
  GRANT ALL PRIVILEGES ON TABLES TO onetree_app;
ALTER DEFAULT PRIVILEGES FOR ROLE onetree_maintenance IN SCHEMA public
  GRANT ALL PRIVILEGES ON SEQUENCES TO onetree_app;
SQL
