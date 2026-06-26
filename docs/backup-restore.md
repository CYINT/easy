# Easy Backup And Restore

## Database Backup

```powershell
docker compose --env-file .env exec -T db pg_dump --clean --if-exists -U easy easy > easy-db-backup.sql
```

## Database Restore

```powershell
Get-Content .\easy-db-backup.sql | docker compose --env-file .env exec -T db psql -U easy easy
```

## Attachment Backup

```powershell
docker run --rm -v easy_easy_media:/media -v ${PWD}:/backup alpine tar czf /backup/easy-media-backup.tgz -C /media .
```

## Attachment Restore

```powershell
docker run --rm -v easy_easy_media:/media -v ${PWD}:/backup alpine sh -c "cd /media && tar xzf /backup/easy-media-backup.tgz"
```

## Local Bridge Stack

For a local bridge deployment, start the restored database first, restore the SQL and media archive, then start the app:

```powershell
$env:EASY_ENV_FILE = ".env"
docker compose up -d db
Get-Content .\easy-db-backup.sql | docker compose exec -T db psql -U easy easy
docker run --rm -v easy_easy_media:/media -v ${PWD}:/backup alpine sh -c "cd /media && tar xzf /backup/easy-media-backup.tgz"
docker compose up --build -d easy
```

## Restore Test

At least once before public use:

- create a board, card, comment, checklist, and image attachment;
- create database and media backups with the commands above;
- restore into a clean local stack;
- confirm the board and attachment still load;
- record the restore evidence in CYINT planning records.
