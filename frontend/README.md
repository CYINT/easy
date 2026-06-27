# Easy Frontend

This directory is the frontend boundary for Easy. It is a static API-driven board client for the `/api/v1/` backend. The Django template UI remains available as a compatibility surface.

Frontend work should use `src/api.js` instead of reaching into Django templates or model URLs directly. The backend contract lives under `/api/v1/` and is documented in `docs/agent-api.md`.

## Local Usage

Open `index.html` from a browser session that is already signed in to the Django backend, or serve this directory with any static file server. The client uses same-origin session cookies and CSRF headers.

```powershell
python -m http.server 5173 -d frontend
```

For a separate frontend origin, configure Django `CSRF_TRUSTED_ORIGINS` and CORS support before relying on browser writes.

## QA

```powershell
npm run qa:frontend
```

The smoke test serves this directory, mocks `/api/v1/`, and verifies board/list/card/checklist/attachment rendering with no desktop horizontal overflow.
