# Easy Backup And Restore

## Database Backup

```powershell
docker compose exec db pg_dump -U easy easy > easy-db-backup.sql
```

## Database Restore

```powershell
Get-Content .\easy-db-backup.sql | docker compose exec -T db psql -U easy easy
```

## Attachment Backup

```powershell
docker run --rm -v easy_easy_media:/media -v ${PWD}:/backup alpine tar czf /backup/easy-media-backup.tgz -C /media .
```

## Attachment Restore

```powershell
docker run --rm -v easy_easy_media:/media -v ${PWD}:/backup alpine sh -c "cd /media && tar xzf /backup/easy-media-backup.tgz"
```

## Restore Test

At least once before public use:

- create a board, card, comment, checklist, and image attachment;
- create database and media backups;
- restore into a clean local stack;
- confirm the board and attachment still load;
- record the restore evidence in CYINT planning records.
