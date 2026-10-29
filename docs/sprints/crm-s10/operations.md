# CRM-S10 operations

Date: 20 October 2026. Original roadmap Sprint 8. Repository: `aadi-crm` only.

## Migration

`backend/migrations/006` must already be applied. The CRM process applies `007_reminders.sql` on startup through the existing migration runner. The script creates `reminder_deliveries` and indexes. It does not drop a table or delete rows. Applying it twice does not insert a second migration row.

Do not point `CRM_DATABASE_PATH` at the Control Plane database. The CRM process refuses a path whose name contains `aadi_platform`.

## Delivery

There is no background daemon. A project manager opens Reminders and uses **Deliver pending reminders**. That run delivers pending rows for projects they manage. A person who manages no project can run it for rows addressed to them.

One run attempts each due row once. A later run does not create another row for the same follow-up, owner, channel, and due instant.

## Email mode

`CRM_REMINDER_EMAIL_MODE` defaults to `test`.

- `test`: the adapter records the email intent. The row state is `recorded`. The screen says it was not delivered. `email_provider_confirmed` stays false.
- `live`: no provider is configured. The row becomes `failed` with `provider_not_configured` on the first attempt. It is not retried automatically, because another attempt cannot succeed until the platform notification port exists.

The header `X-CRM-Reminder-Test-Outcome` is honored only in test mode. Allowed values are `recorded`, `retryable`, and `terminal`. It cannot mark a row sent.

## Retry

Automatic email retry allows 3 attempts. In live mode the waits are 60, 300, and 900 seconds. In test mode the next attempt is eligible immediately, but not twice in the same run. After 3 temporary failures the state is `failed` and `last_error` is `provider_temporary`.

A project manager can use **Retry delivery** on a retryable or stopped email row. That keeps the same row and starts a new 3-attempt cycle. It does not insert a second reminder.

## How to read a failure

| What you see | Meaning |
|---|---|
| Recorded by the test adapter. Not delivered. | Test mode stored the intent. No mailbox accepted it. |
| The email attempt failed and can be retried. Attempts below 3. | Temporary failure. Another run can retry it. |
| Attempts 3 and no next retry | The automatic limit was reached. |
| No email provider is configured. | Live mode is selected and the platform port is absent. |
| The organization directory did not provide an email | The server did not have a directory address for that user. It did not guess one. |

The failure list does not show provider payloads or secrets. Customer names are omitted unless the manager can still open the record, and even then the list shows the record number only.

## Audit

The Control Plane audit route is read-only. CRM does not append to it. Operational history for these reminders is the `reminder_deliveries` row.

## Guarantee

If a future provider accepts a message and the process stops before the sent state is stored, a later run can attempt that message again. This sprint does not claim exactly-once external delivery. The current test adapter never reaches that case because it does not hand the message to a provider.
