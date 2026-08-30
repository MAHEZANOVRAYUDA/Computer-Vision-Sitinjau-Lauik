#!/bin/bash
# Script untuk backup database PostgreSQL secara otomatis (cron job)
# Contoh cron: 0 2 * * * /path/to/backup_db.sh

# Konfigurasi
DB_NAME="sitinjau_lauik_db"
DB_USER="postgres"
BACKUP_DIR="/app/data/backups"
DATE=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_backup_${DATE}.sql.gz"

mkdir -p "$BACKUP_DIR"

# Lakukan backup dan compress
pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

# Hapus backup yang lebih lama dari 7 hari
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +7 -exec rm {} \;

echo "Backup berhasil disimpan di: $BACKUP_FILE"
