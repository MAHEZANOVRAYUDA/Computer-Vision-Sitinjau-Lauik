#!/bin/bash
# Script untuk backup database sitinjau_lauik_db
# Disarankan dijalankan harian via crontab

DB_NAME="sitinjau_lauik_db"
DB_USER="postgres"
BACKUP_DIR="data/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_${DB_NAME}_${DATE}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "Memulai backup database $DB_NAME..."
pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "Backup berhasil: $BACKUP_FILE"
    
    # Simpan hanya 7 hari terakhir
    echo "Membersihkan backup yang lebih tua dari 7 hari..."
    find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +7 -delete
else
    echo "Backup gagal!"
    exit 1
fi
