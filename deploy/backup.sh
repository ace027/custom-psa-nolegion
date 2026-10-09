#!/bin/sh
# Nightly backup: database dump + email attachments, encrypted with age, written to $BACKUP_DIR.
# Copy the result OFF this VM (see docs/BACKUP_RESTORE.md). Run from the repo root via cron.
#   BACKUP_DIR=/var/backups/psa AGE_RECIPIENT=age1... ./deploy/backup.sh
set -eu
: "${BACKUP_DIR:?set BACKUP_DIR}"
: "${AGE_RECIPIENT:?set AGE_RECIPIENT (age public key)}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
umask 077
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$BACKUP_DIR/psa-$stamp.dump.age"
docker compose exec -T db pg_dump -U psa_owner -d psa --format=custom | age -r "$AGE_RECIPIENT" > "$out.partial"
mv "$out.partial" "$out"

# Email attachments live in a volume, not the database: back them up too (same stamp = one set).
att="$BACKUP_DIR/psa-$stamp.attachments.tar.age"
docker compose exec -T worker tar -C /data/attachments -cf - . | age -r "$AGE_RECIPIENT" > "$att.partial"
mv "$att.partial" "$att"

find "$BACKUP_DIR" -name 'psa-*.age' -mtime +"$RETAIN_DAYS" -delete
echo "backup written: $out and $att"
