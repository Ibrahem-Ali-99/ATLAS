# Engineering evidence

Numbers below are from commands run on this workstation. They are not a hosted load test.

## Quality checks

`.\scripts\check.ps1` runs Ruff, format, mypy, pytest, ESLint, the Next.js production build, TypeScript, and gitleaks. On 22 Nov 2026 that script reported 90 pytest tests passed, mypy clean for 94 files, and gitleaks with no leaks. The browser test is not part of that script. An earlier `npm run e2e` run passed in 17.8 seconds and was not repeated in this pass.

`npm run e2e` in `apps/web` is the browser test. It uses database `atlas_e2e`, ports 8010 and 3010, and deterministic providers. It does not call a paid model.

GitHub Actions contains jobs for the API, the web build, the browser test, the container builds, and gitleaks. A green local run is not a green GitHub run.

## Benchmark

`uv run python scripts/benchmark.py` from `apps/api` times health, a CRM list, retrieval, and an agent run against `atlas_test` with deterministic providers. The printed JSON includes `"live_model": false`. One run on this Windows host recorded health 4.33 ms, CRM list 24.66 ms, retrieval 15.47 ms, and agent-to-approval 3232.72 ms. The agent figure includes starting the MCP process. It is not live provider latency. Repeat the script before calling a difference a regression.

HTTP timings against `http://127.0.0.1:8000/api/v1/health` include the client. They are separate from the in-process figure.

## Evaluation

The stored evaluation method is `deterministic_double`. It checks the agent path with stand-ins. It is not live-model accuracy. The lead-score report keeps the held-out comparison from the synthetic training set. The served explanation matches the served model.

A later configuration check read the local settings and printed only whether keys were present. `ATLAS_LLM_API_KEY`, `ATLAS_EMBEDDING_API_KEY`, and both Langfuse keys were unset. No live embedding or chat request was sent.

## Failure handling

An interrupted agent run is marked failed with `interrupted` on startup. An email whose send result is unknown is not sent again. An SMTP timeout and an n8n timeout are not retried. A missing n8n callback stays incomplete. A Langfuse export failure keeps the local trace. Empty model keys fail the call instead of inventing an answer.
