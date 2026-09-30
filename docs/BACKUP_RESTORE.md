# Backups and restore

**What must be backed up:** the PostgreSQL database, **and** the `attachments` volume (files received by
email; the database only stores their names). `.env` holds secrets: store it separately in your
password manager / secret store, *not* alongside the database backups.

## Nightly backup
`deploy/backup.sh` runs `pg_dump` inside the db container and tars the attachments volume, encrypts both with
[age](https://age-encryption.org) and writes `psa-<timestamp>.dump.age` + `psa-<timestamp>.attachments.tar.age`,
deleting files older than 14 days.

One-time setup on the VM:
```sh
sudo apt install age
age-keygen -o ~/psa-backup-key.txt        # KEEP THIS KEY OFF THE VM (password manager + offline copy)
grep 'public key' ~/psa-backup-key.txt     # the age1... value is AGE_RECIPIENT
```
Only the *public* key needs to live on the VM. Without the private key a backup cannot be read,
so store it somewhere else and test that you can find it.

Cron (as the user that runs docker compose), e.g. 02:15 nightly:
```
15 2 * * * cd /opt/psa && BACKUP_DIR=/var/backups/psa AGE_RECIPIENT=age1xxxx ./deploy/backup.sh >> /var/log/psa-backup.log 2>&1
```
**Copy `BACKUP_DIR` off the VM** (rsync/rclone/SMB to another host or cloud bucket). A backup on the
same disk is not a backup. Suggested retention: 14 daily on the VM, 8 weekly + 12 monthly offsite.

## Restore drill (do this quarterly, and once before go-live)
Restore into a scratch database; production is untouched:
```sh
docker compose exec -T db psql -U psa_owner -d postgres -c "CREATE DATABASE psa_drill OWNER psa_owner"
age -d -i ~/psa-backup-key.txt /var/backups/psa/psa-XXXX.dump.age \
  | docker compose exec -T db pg_restore -U psa_owner -d psa_drill --no-owner --role=psa_owner --exit-on-error
docker compose exec db psql -U psa_owner -d psa_drill -c "SELECT count(*) FROM organizations; SELECT max(occurred_at) FROM audit_log;"
docker compose exec -T db psql -U psa_owner -d postgres -c "DROP DATABASE psa_drill"
```
Check the row counts and the newest audit timestamp look right. The test suite also runs an automated
dump→restore drill (`backend/tests/test_backup_restore.py`) so the *mechanism* is verified on every change.

## Real restore (disaster recovery)
1. Provision the VM, install Docker, clone the repo, restore `.env` from your secret store.
2. `docker compose up -d db` (creates roles; the fresh DB is empty).
3. `AGE_IDENTITY=~/psa-backup-key.txt ./deploy/restore.sh /path/to/psa-XXXX.dump.age` (asks you to
   type the database name; stops the API and worker during the restore; if the matching
   `.attachments.tar.age` is next to the dump, attachments are restored too).
4. `docker compose up -d --build`; migrations are no-ops if the restored DB is already current.
5. Sign in, spot-check recent records and the audit log.

## Notes
- `pg_dump` runs as `psa_owner`, which bypasses row-level security. Do **not** use
  `--enable-row-security`: that silently omits rows.
- Restores keep the row-level-security policies and the append-only audit-log grants (verified by
  the automated drill).
