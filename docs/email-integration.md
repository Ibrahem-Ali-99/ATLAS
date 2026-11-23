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

Organization-scoped email configuration is foundation-only in this phase. Existing Mailpit sandbox delivery and environment-backed email behavior remain active. The delivery path does not read this integration record until a later phase adds explicit live-mode activation, recipient safeguards, and durable delivery reconciliation.
