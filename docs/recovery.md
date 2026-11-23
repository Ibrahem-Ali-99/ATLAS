# Staging backup and recovery

The backup is a logical Postgres dump plus the upload, model, and n8n directories. It is not a copy of the Postgres data volume. Ollama weights are not included. `nomic-embed-text:v1.5` is pulled again by the embedding provision command. Mailpit mail and Caddy certificates are not included. Let's Encrypt issues a new certificate when Caddy starts with the public name.

The archive does not contain `infrastructure/staging/.env`. Keep that file, or the same values, in a password manager:

- `STAGING_SECRET_KEY` opens sealed webhook secrets. A database restore cannot replace it.
- `STAGING_POSTGRES_PASSWORD` is the role password the new Postgres container starts with. The dump is taken with `--no-role-passwords`.
- `STAGING_N8N_ENCRYPTION_KEY` must be the key from the backed-up n8n volume. n8n also stores that key in its settings file inside the volume. The off-host copy is encrypted so that file is not readable in the bucket.
- `ATLAS_BACKUP_PASSPHRASE` decrypts the archive. It is not inside the archive.

## Schedule and recovery point

Install the timer once on the VPS. Enabling it again does not add a second schedule.

```bash
sudo install -m 600 infrastructure/staging/backup.env.example /etc/atlas/backup.env
sudo cp infrastructure/staging/atlas-backup.service /etc/systemd/system/
sudo cp infrastructure/staging/atlas-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now atlas-backup.timer
```

Edit `/etc/atlas/backup.env` before enabling the timer. The timer runs at 02:15 UTC every day. `Persistent=true` runs a missed backup after the host has been off. A second run that overlaps the first exits `backup_refused backup_busy` and does not write a partial archive. The recovery point is the last successful run. With a healthy daily timer that is at most 24 hours, plus the time the dump itself takes. This is not Postgres point-in-time recovery.

The command exits 0 on success and 2 when the dump, archive, encryption, or upload fails. systemd records a non-zero exit as a failed service. The success line includes the archive size, free disk space, how many old archives were deleted, and whether the off-host copy ran.

Fourteen daily archives are kept. Older names that match `atlas-YYYYMMDDTHHMMSSZ.tar.gz.enc` are deleted. Files that do not match that name are left alone.

## What a backup contains

| Path | Contents |
| --- | --- |
| `postgres-*.dump` | `pg_dump -Fc` of each non-template database |
| `globals.sql` | Roles and tablespaces, without role passwords |
| `uploads.tar` | `/var/lib/atlas/storage` |
| `models.tar` | `/var/lib/atlas/models` |
| `n8n.tar` | `/home/node/.n8n`, taken while n8n is stopped |
| `manifest.json` | Sizes and SHA-256 for those files |

n8n is stopped only for the file archive, then started again. Postgres stays up. The dump is a consistent snapshot from `pg_dump`.

## Encryption and off-host storage

Set `ATLAS_BACKUP_PASSPHRASE` in `/etc/atlas/backup.env`. The archive is encrypted with AES-GCM. The key is derived with PBKDF2-HMAC-SHA256 and 200,000 iterations. Encryption runs in the API image, which already provides the cryptography library. The plaintext tar is removed. An empty passphrase leaves a local `.tar.gz` and refuses an upload.

Set `ATLAS_BACKUP_S3_URI` to an `s3://bucket/prefix` value, plus `ATLAS_BACKUP_S3_ENDPOINT` for an S3-compatible service. `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` stay in the same root-only env file. The upload uses the `amazon/aws-cli:2.22.35` image on the private Docker network. No backup port is published.

Hetzner Object Storage lists a base price of €6.49 per month, excluding VAT, which includes 1 TB of storage and 1 TB of egress (checked November 2026). Fourteen small staging archives fit in that included terabyte. Backblaze B2 lists $6.95 per TB-month, with the first 10 GB free. Either is enough. Do not buy the bucket until the restore drill below has been read.

A manual run from the repository root:

```bash
set -a
. /etc/atlas/backup.env
set +a
python3 infrastructure/staging/backup.py
```

On Windows, for a drill, set `ATLAS_BACKUP_PASSPHRASE` in the process environment and pass `--project`, `--env-file`, and `--backup-dir`.

## Restore onto a fresh host

1. Install Docker and clone the same git revision.
2. Restore `/etc/atlas/backup.env` and `infrastructure/staging/.env` from the password manager. The Postgres password and the n8n encryption key must match the backed-up environment.
3. Copy one encrypted archive to the host. Do not restore it over the project names `atlas` or `atlas-staging`.
4. Start only the data services by running the restore command. It decrypts the archive, checks every SHA-256, loads each dump with `pg_restore`, and extracts the three directories.

```bash
python3 infrastructure/staging/restore.py \
  --project atlas-restore \
  --env-file infrastructure/staging/.env \
  --archive /var/backups/atlas/atlas-YYYYMMDDTHHMMSSZ.tar.gz.enc
```

5. Start the stack. The embedding service pulls `nomic-embed-text:v1.5` when the Ollama volume is empty. `/api/v1/ready` becomes healthy after that pull. Search needs the model. The restored vectors are already in `chunks.embedding_768`.
6. Sign in with the administrator password from the password manager. Open the restored company and search for a sentence from a restored document. Export n8n workflows and confirm they load with the original encryption key. A different key must not decrypt stored credentials.
7. Confirm the Caddy certificate and the webhook secret. The secret remains sealed with `STAGING_SECRET_KEY`. n8n workflows stay inactive until an operator activates them.

## Drill

`infrastructure/staging/accept_restore.py` builds a disposable project, uploads a document, creates a company and an n8n credential, backs up, deletes those volumes, restores onto new volumes, and checks the rows, file bytes, 768-wide vectors, login, organization isolation, and the n8n key. It does not attach to the `atlas` or `atlas-staging` projects.
