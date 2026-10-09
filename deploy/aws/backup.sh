#!/bin/bash
# SHIP-8: incremental backup of the shipmentlabel server to S3 (runs as root on the host, not in a container).
#   - database: gzipped pg_dump -> s3://BUCKET/db/shipmentlabel-<UTC stamp>.sql.gz (kept 90 days by the lifecycle rule)
#     and a local copy (.backup/db-latest.sql.gz) for "Download full backup" in the app
#   - files: `aws s3 sync` of the label storage volume -> s3://BUCKET/files/ (only new/changed files are uploaded;
#     no --delete, so files deleted in the app stay in S3; the bucket is versioned, old versions kept 90 days)
#   - result: .backup/status.json, shown on the app's Files page
# Triggers: systemd timer (nightly) and the app's "Back up now" button (writes .backup/request -> systemd path unit).
# AWS access: the instance role shipmentlabel-ec2-ssm (put/get/list on this bucket only, no delete). No keys on disk.
set -uo pipefail
APP=/opt/shipmentlabel/app
BUCKET=${BACKUP_BUCKET:-shipmentlabel-backup-463946129264}
export AWS_DEFAULT_REGION=ap-south-1
VOL=$(docker volume inspect -f '{{.Mountpoint}}' app_label_storage)
B="$VOL/.backup"
mkdir -p "$B"

exec 9>/run/shipmentlabel-backup.lock
flock -n 9 || { echo "another backup is running"; exit 0; }
TRIGGER=$([ -f "$B/request" ] && echo "button" || echo "schedule")
rm -f "$B/request"

START=$(date -u +%FT%TZ)
STAMP=$(date -u +%Y%m%d-%H%M%S)
ERR=""
DB_KEY=""

set -a; . "$APP/.env"; set +a
cd "$APP"
if docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-shipmentlabel}" "${POSTGRES_DB:-shipmentlabel}" | gzip -9 > "$B/db-new.sql.gz" \
   && [ "$(gzip -dc "$B/db-new.sql.gz" | head -c 200 | wc -c)" -gt 0 ]; then
  mv "$B/db-new.sql.gz" "$B/db-latest.sql.gz"
  DB_KEY="db/shipmentlabel-$STAMP.sql.gz"
  aws s3 cp "$B/db-latest.sql.gz" "s3://$BUCKET/$DB_KEY" --only-show-errors || ERR="database copy could not be uploaded to S3"
else
  rm -f "$B/db-new.sql.gz"; ERR="database copy failed"
fi

SYNC_OUT=$(aws s3 sync "$VOL" "s3://$BUCKET/files/" --exclude ".backup/*" --exclude ".*" --exclude "*/.*" --no-progress 2>&1)
RC=$?
UPLOADED=$(printf '%s\n' "$SYNC_OUT" | grep -c '^upload:' || true)
[ $RC -ne 0 ] && ERR="${ERR:+$ERR; }file upload failed: $(printf '%s' "$SYNC_OUT" | tail -1 | cut -c1-200)"
TOTAL_FILES=$(find "$VOL" -path "$B" -prune -o -type f ! -name '.*' -print | wc -l)
TOTAL_BYTES=$(du -sb --exclude=.backup "$VOL" | cut -f1)
DB_BYTES=$(stat -c %s "$B/db-latest.sql.gz" 2>/dev/null || echo 0)

python3 - "$B/status.json" <<EOF
import json, sys
json.dump({"started_at": "$START", "finished_at": "$(date -u +%FT%TZ)", "ok": not "$ERR", "error": "$ERR" or None,
           "trigger": "$TRIGGER", "bucket": "$BUCKET", "db_key": "$DB_KEY" or None, "db_copy_bytes": int("$DB_BYTES"),
           "uploaded_files": int("$UPLOADED"), "total_files": int("$TOTAL_FILES"), "total_bytes": int("$TOTAL_BYTES")},
          open(sys.argv[1], "w"), indent=1)
EOF
echo "backup $([ -z "$ERR" ] && echo OK || echo "FAILED: $ERR"): uploaded $UPLOADED of $TOTAL_FILES files, db $DB_BYTES bytes"
[ -z "$ERR" ]
