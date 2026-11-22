# ATLAS web

Next.js dashboard for ATLAS. Setup, seed accounts, and the API URL are in the repository [README](../../README.md).

Run the dev server on the same loopback host as `NEXT_PUBLIC_API_URL`:

```powershell
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000. Browsers treat `localhost` and `127.0.0.1` as different sites, so the page host and the API host must match.
