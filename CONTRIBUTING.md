# Contributing

Easy welcomes focused fixes and improvements.

Before opening a pull request:

- Keep public language centered on Easy and its own features.
- Do not commit secrets, `.env`, uploaded media, database dumps, or generated backups.
- Run `python manage.py check` and `python manage.py test`.
- Add or update tests for behavior changes.
- Keep changes small and explain the user-visible impact.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py test
```
