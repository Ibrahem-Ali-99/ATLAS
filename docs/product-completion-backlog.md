# ATLAS product-completion backlog

## Phase 1 — first-run experience

- [x] Truthful readiness checklist for organization, providers, embeddings, knowledge, CRM, delivery modes, n8n, assistant, and approvals.
- [x] Link every checklist item to an existing supported action.
- [x] Distinguish `Not configured`, `Needs attention`, `Ready`, and `Verified`.
- [x] Keep provider credentials operator-managed when runtime persistence is unavailable.
- [ ] Add a clean-install acceptance flow that uploads a safe fixture and verifies a grounded answer in the disposable environment.

## Remaining limitations

- [ ] Add a secure operator-managed provider configuration path with explicit restart/apply semantics; do not add a browser save button until secrets can be stored safely.
- [ ] Add knowledge onboarding progress and a citation-focused test-question flow after a document is indexed.
- [ ] Add explicit demo-data loading controls that remain separate from operational records.
- [ ] Add n8n webhook-key provisioning and activation checks without exposing the signing secret.
- [ ] Add a clear sandbox Mailpit test action and a clearly simulated calendar test action.
- [ ] Add a first-run path for creating the first operational company, contact, lead, and inquiry.
- [ ] Add an approval-controlled agent demonstration that stops before external side effects in sandbox mode.
- [ ] Add integration failure, invalid-credential, network-failure, and cross-organization acceptance coverage for the checklist state.
- [ ] Add onboarding persistence or dismiss/revisit behavior if product discovery confirms it is needed.
- [ ] Add public deployment readiness checks for TLS, Groq/OpenAI credentials, webhook activation, and off-host backups.

The product is not complete until the unsupported items are either implemented or explicitly documented as operator-only deployment steps.
