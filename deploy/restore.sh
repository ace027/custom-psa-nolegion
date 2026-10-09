#!/bin/sh
# Restore an encrypted dump into the RUNNING db container. DESTRUCTIVE: replaces current data.
#   AGE_IDENTITY=/path/to/age-key.txt ./deploy/restore.sh /var/backups/psa/psa-XXXX.dump.age
# If psa-XXXX.attachments.tar.age sits next to the dump, the attachments are restored too.
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
att="${file%.dump.age}.attachments.tar.age"
if [ -f "$att" ]; then
  echo "restoring attachments from $att"
  docker compose run --rm --no-deps -T --user root --entrypoint sh worker -c 'rm -rf /data/attachments/* /data/attachments/.[!.]* 2>/dev/null; true'
  age -d -i "$AGE_IDENTITY" "$att" | docker compose run --rm --no-deps -T --user root --entrypoint sh worker -c 'tar -C /data/attachments -xf - && chown -R psa /data/attachments'
fi
docker compose start api worker
echo "restore complete"
