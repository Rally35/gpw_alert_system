#!/bin/bash
# Database backup script

# Set variables
BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/gpw_stocks_$TIMESTAMP.sql"

# Ensure backup directory exists
mkdir -p $BACKUP_DIR

# Run backup
docker exec gpw_alert_system_database_1 pg_dump -U user stocks > $BACKUP_FILE

# Compress backup
gzip $BACKUP_FILE

echo "Backup completed: $BACKUP_FILE.gz"

# Delete backups older than 30 days
find $BACKUP_DIR -name "gpw_stocks_*.sql.gz" -mtime +30 -delete