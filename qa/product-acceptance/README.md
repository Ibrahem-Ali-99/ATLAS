# Independent product acceptance

This suite evaluates ATLAS as a product. It does not replace the regression tests, and a green regression run is not product approval.

The runner creates a disposable database, starts its own API and web server on free ports, and leaves the shared processes on ports 8000 and 3000 running. Billing is forced to sandbox. Live email, live campaigns, live WhatsApp, n8n dispatch, and Stripe credentials are cleared for that process. SMTP points at a closed local port so a mistaken send cannot reach the shared mailbox. The browser session is separate from the shared app.

Assistant evaluation prompts live only in `sealed/`. Do not open that directory from the assistant implementation session before its architecture is complete. The defect register cites case ids and observed failures, not the prompts.

```powershell
.\qa\product-acceptance\run.ps1
```

Evidence for each run is written under `var/product-acceptance/<timestamp>/`, including screenshots, integration classification, assistant scores, and a machine defect list. The reviewed register is `qa/product-acceptance/DEFECT_REGISTER.md`. The runner does not replace that review.

The run covers Overview, CRM, Inbox, Assistant, Knowledge, Approvals, Workflows, Agent Runs, Analytics, Campaigns, Monitoring, Integrations, Billing, and Settings. It creates and reloads CRM records, saves an inactive workflow and a campaign draft, and does not schedule delivery, approve a send, connect Google, or start checkout.
