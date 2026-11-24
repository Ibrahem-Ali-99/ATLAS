# Sample workspace population

ATLAS includes an explicit, reversible population command for a separately
designated sample organization. It is disabled by default and refuses any
organization whose slug does not begin with `sample-`.

Create the sample organization and its administrator through the normal
identity/bootstrap process first. Then, from `apps/api` with the API settings
pointing at a disposable database, run:

```powershell
.venv\Scripts\python.exe -m app.scripts.populate_workspace `
  --organization-slug sample-atlas `
  --confirm-sample-workspace
```

The command is idempotent. It creates a small linked B2B workspace with three
companies, three contacts, five leads spanning the supported pipeline stages,
three inquiries, follow-up interactions, and one persisted assistant
conversation. Rows are marked as demo-origin and use a stable `Sample
workspace ·` marker.

To remove only rows created by this command, use the same explicit confirmation:

```powershell
.venv\Scripts\python.exe -m app.scripts.populate_workspace `
  --organization-slug sample-atlas `
  --confirm-sample-workspace `
  --purge
```

The command does not seed at application startup, does not reset passwords,
does not modify other organizations, and does not create provider credentials,
email deliveries, agent executions, or claims of completed external actions.
Run it only against a disposable or explicitly authorized sample organization.
