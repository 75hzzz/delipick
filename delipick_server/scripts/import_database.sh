#!/usr/bin/env bash
set -eu
if [ "$DATASET_MODE" = demo ]; then
  echo 'Demo mode: no private SQL import.'
  exit 0
fi
[ "$DATASET_MODE" = existing ] || { echo 'DATASET_MODE must be existing or demo.' >&2; exit 1; }
[[ "$DB_NAME" =~ ^[A-Za-z0-9_]+$ ]] || { echo 'Invalid database name.' >&2; exit 1; }
tables=$(mysql --host="$DB_HOST" --user="$DB_USER" --database="$DB_NAME" --batch --skip-column-names \
  --execute='SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()')
if [ "$tables" != 0 ]; then
  marker=$(mysql --host="$DB_HOST" --user="$DB_USER" --database="$DB_NAME" --batch --skip-column-names \
    --execute="SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='delipick_import_state'")
  if [ "$marker" = 1 ]; then
    status=$(mysql --host="$DB_HOST" --user="$DB_USER" --database="$DB_NAME" --batch --skip-column-names --execute='SELECT status FROM delipick_import_state WHERE id=1')
    [ "$status" = complete ] || { echo 'Incomplete SQL import: recover explicitly; no overwrite attempted.' >&2; exit 1; }
    echo 'Recognized completed import; retaining database without needing the dump.'
    exit 0
  fi
  legacy=$(mysql --host="$DB_HOST" --user="$DB_USER" --database="$DB_NAME" --batch --skip-column-names \
    --execute="SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='deployment_state'")
  if [ "$legacy" = 1 ]; then
    known=$(mysql --host="$DB_HOST" --user="$DB_USER" --database="$DB_NAME" --batch --skip-column-names \
      --execute="SELECT COUNT(*) FROM deployment_state WHERE state_key='dataset_mode' AND state_value='existing'")
    if [ "$known" = 1 ]; then
      echo 'Legacy initialized database: init must validate trusted metadata and counts before adoption.'
      exit 0
    fi
  fi
  echo 'Unrecognized nonempty database; partial import cannot be assumed complete.' >&2
  exit 1
fi
[ -s /database/database.sql ] || { echo 'Missing trusted single-database dump: database/database.sql' >&2; exit 1; }
if grep -Eiq '^[[:space:]]*((CREATE|DROP)[[:space:]]+DATABASE|USE[[:space:]])' /database/database.sql; then
  echo 'Export one database without CREATE/DROP DATABASE or USE statements.' >&2
  exit 1
fi
digest=$(sha256sum /database/database.sql | cut -d ' ' -f1)
mysql --host="$DB_HOST" --user="$DB_USER" --database="$DB_NAME" \
  --execute="CREATE TABLE delipick_import_state (id INT PRIMARY KEY,status VARCHAR(16) NOT NULL,sql_sha256 CHAR(64) NOT NULL); INSERT INTO delipick_import_state VALUES (1,'importing','$digest')"
mysql --host="$DB_HOST" --user="$DB_USER" --database="$DB_NAME" --default-character-set=utf8mb4 < /database/database.sql
mysql --host="$DB_HOST" --user="$DB_USER" --database="$DB_NAME" --execute="CREATE TABLE IF NOT EXISTS delipick_import_state (id INT PRIMARY KEY,status VARCHAR(16) NOT NULL,sql_sha256 CHAR(64) NOT NULL); REPLACE INTO delipick_import_state VALUES (1,'complete','$digest')"
echo 'Imported the trusted dump into the isolated project database.'
