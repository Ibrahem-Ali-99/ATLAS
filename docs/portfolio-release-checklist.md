# Portfolio release checklist

Prepared 27 November 2026. This is the gate for the public Upwork site. It does not purchase a host, a domain, or a paid model. It does not publish the site. Personal acceptance comes before either of those.

The procedure is [portfolio-deployment.md](portfolio-deployment.md). The private provider demonstration stays on [harbor-demonstration.md](harbor-demonstration.md) and is not this stack.

## What is ready in the tree

- The public pages are `/`, `/demo`, and `/case-study` in `apps/web-rebuild`. The workspace is `/login`. The portfolio image sets `ATLAS_PUBLIC_SITE=1`. A local product server leaves that flag unset, so `/` stays the workspace.
- Product pictures in `apps/web-rebuild/public/portfolio/` are viewport captures of that client reading the Harbor & Co. workspace. They are not drawings. The integrations picture is the private review. It does not show a secret, and the public stack does not mount that database.
- `infrastructure/compose.portfolio.yaml` builds `apps/web-rebuild`. The file still points visitor chat at Ollama `llama3.2:1b`. That model was measured on 27 November 2026 and is not an acceptable public assistant. Leave the paid key empty until a Groq-backed change is explicitly accepted. Visitor retrieval stays on the deterministic stand-in. Live email, campaigns, WhatsApp, Stripe, Google Calendar, and n8n stay off.
- Public replies are off unless `ATLAS_PUBLIC_INFERENCE_ENABLED` is set. The portfolio file sets it. Limits are 8 replies per session and 200 per process inside one hour, 2 seconds apart, 2 at a time, 256 output tokens, and 2,000 input characters. Abuse patterns are rejected before the model is called. A non-visitor cannot use that client. A keyless call to a public model host is refused.

## Qualification recorded on 27 November 2026

`infrastructure/portfolio/prove.py` exited 0 for project `atlas-portfolio-proof`. The detail is in [portfolio-deployment.md](portfolio-deployment.md). The proof stack was removed afterward. The private Harbor API was still answering `/api/v1/health` on port 8014.

- [x] Caddy served the public site, `/demo`, `/case-study`, `/login`, and the overview capture. Hidden API docs returned 404. Anonymous auth routes returned 401 without a session cookie.
- [x] Every long-running service became healthy, and the model pull completed before the API started.
- [x] A visitor launch was isolated from Atlas Demo, refused integration configuration and checkout, stopped at eight replies, refused a second immediate reply, and was deleted after the session expired.
- [x] Resident memory with the model loaded was about 2.0 GiB. Ollama used 1.65 GiB of its 1.75 GiB cap. The 8 GB host recommendation stands for this compose file.
- [ ] Do not rent a host for `llama3.2:1b` as the public assistant. The replacement, if accepted, is Groq `openai/gpt-oss-20b` behind the same budgets and a key that is not the Harbor key. That path is not implemented: a public demo still refuses a paid key.

## Before a machine is rented

- [ ] The working tree you intend to publish is committed. Other sessions' uncommitted files are not part of this commit.
- [ ] `uv run --project apps/api --locked python infrastructure/portfolio/compose_contract.py` exits 0.
- [ ] From `infrastructure/portfolio`, `uv run --project apps/api --locked pytest test_portfolio_compose.py test_portfolio_preflight.py` exits 0. From `apps/api`, `uv run --locked pytest tests/test_inference_guard.py tests/test_settings.py` exits 0.
- [ ] You have read the site and the case study and accepted the pictures, including the private Harbor integrations frame.
- [ ] You have decided the public hostname. No name was registered for this preparation.

## On the host, still before traffic

- [ ] One amd64 Ubuntu LTS machine, 2 vCPU, 8 GB RAM, 40 GB disk. Ports 22, 80, and 443 only.
- [ ] One A record, and an AAAA record only if the host has a reachable IPv6 address.
- [ ] Three generated secrets in `infrastructure/portfolio/.env`: `PORTFOLIO_SECRET_KEY`, the credential key after `demo-01=`, and `PORTFOLIO_POSTGRES_PASSWORD`. The password is letters and digits only. None of them are committed.
- [ ] `PORTFOLIO_HOST`, the CORS origin, and `PORTFOLIO_CAMPAIGN_PUBLIC_URL` are `https://` plus that hostname. HTTP and HTTPS ports are 80 and 443.
- [ ] Provider, Stripe, and Google values stay empty. `PORTFOLIO_ENVIRONMENT=development` and `PORTFOLIO_PUBLIC_DEMO=true`.
- [ ] `python3 infrastructure/portfolio/preflight.py --env-file infrastructure/portfolio/.env` exits 0.
- [ ] `sh infrastructure/portfolio/up.sh` becomes healthy. The first boot pulls `llama3.2:1b` from the Ollama library. That pull is a download, not a paid API.
- [ ] Seed passwords are the ones already used for local development, exported only for `python3 infrastructure/portfolio/apply_demo.py`, then unset. They are not written into the env file or the site.
- [ ] `python3 infrastructure/portfolio/smoke.py --base-url https://HOST` prints `{"ok": true}` and does not sign in.

## Confirm a visitor cannot cross a tenant

- [ ] `/api/v1/auth/me` without a cookie is 401 and sets no session cookie.
- [ ] A failed login is 401 and sets no session cookie.
- [ ] `/docs`, `/openapi.json`, and `/redoc` are 404.
- [ ] Launch creates an organization whose slug starts with `harbor-visitor-`. That session's CRM, knowledge, and assistant calls do not return rows from Atlas Demo, Northwind, or `atlas_harbor`.
- [ ] Approving a customer message or a new appointment from the visitor session returns a refusal and does not stage a send.
- [ ] Billing checkout, invitations, provider connect, and campaign scheduling return a refusal.
- [ ] The Harbor review on ports 8014 and 3040 is still the private database after the public stack starts. Its password is not on the public site.

## Still in this working tree

- The rest of `apps/web-rebuild` — layout, workspace page, presentation modules, and package files — was left uncommitted. It is being edited in this checkout. `infrastructure/portfolio/up.sh` cannot build the image from commit `73eccfb` alone. Commit that client before renting a host.

## Still external

- A hostname and DNS. Not purchased.
- The virtual machine. Not rented.
- The first Ollama pull needs outbound network on that machine once.
- Personal acceptance of the pictures and the copy.
- A clean `.\scripts\verify-release.ps1` on a tree with no other session's uncommitted files. The 26 November counts were not a clean checkout. This checklist does not replace that run.
- The private Harbor WhatsApp callback still cannot move onto this public host. Meta allows one callback URL per app. That demonstration stays on the Harbor review.

## Do not do these yet

- Do not run `prove.py` against a machine that is already serving visitors. It creates and deletes a proof project. It is the rehearsal, not the publication.
- Do not set a paid model key, a live email flag, a Stripe live key, or an n8n URL on the portfolio env file. Preflight and process startup both refuse them.
- Do not publish the administrator or staff password.
