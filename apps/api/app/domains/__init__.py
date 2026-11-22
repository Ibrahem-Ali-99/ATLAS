"""Domain packages for the ATLAS modular monolith.

Implemented:
- identity: users, organizations, memberships, sessions, and authorization.
- crm: companies, contacts, leads, inquiries, and interaction history.
- knowledge: document ingestion, chunking, and hybrid retrieval.
- assistant: grounded chat over documents and read-only CRM records.
- agents: LangGraph inquiry workflow over CRM and knowledge.
- approvals: human decisions required before an agent writes CRM records.
- automation: webhooks, execution intents, sandbox email, and simulated calendar bookings.
- ml: synthetic lead scoring. Predictions are advisory.
- analytics: organization-scoped counts from persisted records.
- observability: local operation traces, with optional Langfuse export.
- evaluation: deterministic benchmark checks. They are not live-model accuracy.
- monitoring: diagnostics assembled from stored runs and traces.
"""
