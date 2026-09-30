#!/bin/sh
# Restore an encrypted dump into the RUNNING db container. DESTRUCTIVE: replaces current data.
#   AGE_IDENTITY=/path/to/age-key.txt ./deploy/restore.sh /var/backups/psa/psa-XXXX.dump.age
# For a safe drill, restore into a scratch database instead: see docs/BACKUP_RESTORE.md.
set -eu
file="${1:?usage: restore.sh <backup.dump.age>}"
: "${AGE_IDENTITY:?set AGE_IDENTITY (path to age private key)}"
TARGET_DB="${TARGET_DB:-psa}"
echo "About to REPLACE database '$TARGET_DB' with $file. Type the database name to continue:"
read -r answer
[ "$answer" = "$TARGET_DB" ] || { echo "aborted"; exit 1; }
docker compose stop api
age -d -i "$AGE_IDENTITY" "$file" | docker compose exec -T db pg_restore -U psa_owner -d "$TARGET_DB" --clean --if-exists --no-owner --role=psa_owner
docker compose start api
echo "restore complete"
