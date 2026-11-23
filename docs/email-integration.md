# Organization-scoped email configuration

Phase 1 stores transactional SMTP settings per organization without enabling live delivery.

The integration type is `email` with provider `smtp`. Safe metadata is stored in `integration_configs.config`:

```json
{
  "host": "smtp.example.test",
  "port": 587,
  "starttls": true,
  "use_tls": false,
  "from_address": "noreply@example.test",
  "display_name": "ATLAS",
  "reply_to": "support@example.test"
}
```

Credentials are supplied as a JSON object containing `username` and `password`, then sealed with the existing integration-secret Fernet key before persistence. They are never returned by metadata APIs or audit events.

The admin verification endpoint opens the SMTP connection, negotiates TLS when configured, and authenticates without sending a message. A successful connection does not prove that the sender domain is verified by the provider. Verification records a timestamp and safe detail; configuration changes clear that result.

Organization-scoped email configuration is not a live transport switch. During sandbox delivery, the approved action's organization is checked for a disabled or malformed email override, but the message is always sent through the environment-backed local Mailpit transport. An external SMTP host in the organization record can never replace that transport.

Agent-created customer-response approvals include the organization-owned contact ID and a normalized recipient snapshot. Execution re-reads that contact under the approval organization and fails closed if the contact is missing, belongs to another organization, or its email changed after approval. Legacy approvals without a contact snapshot retain their existing sandbox behavior for compatibility.

This phase still does not enable live delivery or claim exactly-once external SMTP delivery. SMTP timeouts remain outcome-uncertain and require the existing recovery workflow.
