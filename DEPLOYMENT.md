# Live Smart Inbox deployment

The production app has two Render services:

1. The existing Vite static site serves the marketing pages and portal UI.
2. A private-key-holding Python web service receives email, calls OpenAI, and
   returns authorized account data and draft status to the portal.

`render.yaml` defines the API service and Postgres database. It intentionally
does not replace the existing static site.

## 1. Create the API service

In Render, create a Blueprint from this repository's `render.yaml`, or create a
Python Web Service manually with:

- Build command: `pip install -r requirements.txt`
- Pre-deploy command: `alembic upgrade head`
- Start command: `uvicorn server.app:app --host 0.0.0.0 --port $PORT`
- Health check: `/healthz`
- Plan: Starter or higher. A sleeping free service cannot poll email in real time.
- Database: Render Postgres, exposed to the service as `DATABASE_URL`

Set these secrets on the API service:

- `OPENAI_API_KEY`
- `SOLVD_ACCOUNT_USERNAME`
- `SOLVD_ACCOUNT_PASSWORD`
- `SOLVD_ALLOWED_ORIGINS=https://getsolvd.io,https://www.getsolvd.io`
- `SOLVD_IMAP_HOST=imap.gmail.com`
- `SOLVD_IMAP_USERNAME` to the connected mailbox address
- `SOLVD_IMAP_PASSWORD` to a mailbox-specific password or credential

Until a mailbox exists, leave `SOLVD_IMAP_USERNAME` and
`SOLVD_IMAP_PASSWORD` empty. `SOLVD_EMAIL_SOURCE=auto` then selects the
temporary `accounts/test/messages.json` input, and
`SOLVD_FIXTURE_AI_MODE=process` sends its actionable messages through OpenAI.
The results are stored in Postgres, so service restarts do not repeat calls for
unchanged messages.

`SOLVD_ACCOUNT_ID`, `SOLVD_ACCOUNT_USERNAME`, and
`SOLVD_ACCOUNT_PASSWORD` bootstrap the first owner into Postgres. They are not
the permanent account store and should remain set for safe recovery.

Render generates `SOLVD_SESSION_SECRET`, `SOLVD_EMAIL_WEBHOOK_SECRET`, and
`SOLVD_ADMIN_SECRET` when the Blueprint first creates the service. For an
existing service, set all three to separate long random values in the dashboard.

## 2. Point the static site at the API

On the existing Render Static Site, add this build-time environment variable:

```text
VITE_API_BASE_URL=https://<your-api-service>.onrender.com
```

Save, rebuild, and deploy the static site. Also include its exact public origin
in `SOLVD_ALLOWED_ORIGINS` on the API service.

## 3. Choose email ingestion

### Temporary JSON input

With no complete IMAP credentials, the deployed service automatically loads:

```text
accounts/test/messages.json
```

Each entry uses the same normalized message structure as the webhook example
below. Edit or add an entry, commit it, and redeploy. A changed content
fingerprint is queued for a fresh AI pass; unchanged entries keep their stored
result. `accounts/test/inbox-ai.json` is only a local-development cache and is
not used as the production answer.

The health endpoint reports `"emailSource":"fixture"` in this mode.

### IMAP

IMAP polling is enabled when all three `SOLVD_IMAP_*` credentials are present.
The service checks unread messages every 15 seconds, reads them without marking
them as read, deduplicates by Message-ID and content fingerprint, and schedules
only actionable human messages for AI. These environment credentials belong to
the bootstrap account only. Additional production tenants should use their
account-scoped webhook until per-tenant Google OAuth connections are added; do
not add multiple mailbox passwords to Render environment variables.

### Webhook

Alternatively, an email provider can send a normalized event to:

```text
POST /api/v1/webhooks/email
Authorization: Bearer <SOLVD_EMAIL_WEBHOOK_SECRET>
Content-Type: application/json
```

```json
{
  "id": "provider-message-id",
  "thread_id": "provider-thread-id",
  "from": {"name": "Member Name", "email": "member@example.com"},
  "to": "front@examplegym.com",
  "subject": "Freeze next month?",
  "body_text": "Can I freeze my membership next month?",
  "received_at": "2026-08-07T23:00:00Z",
  "labels": ["INBOX", "UNREAD"],
  "headers": {}
}
```

## 4. Add tenants and users

The API stores tenants, identities, and roles in Postgres. Each identity is
assigned to exactly one gym account; there is no dashboard account switcher.
Passwords are Argon2id hashes. The environment-configured login is imported as
the initial owner of `SOLVD_ACCOUNT_ID` on every deployment, which migrates the
existing test login without resetting the database.

The web service runs `alembic upgrade head` as its pre-deploy command. This
creates only missing versioned schema and preserves the existing inbox records.
Do not delete or recreate the Render database for this deployment.

While account data is still fixture-backed, add a tenant by committing a new
`accounts/<account-id>/` directory with the same required JSON files as
`accounts/test/`. The `id` in `account.json` must match the directory name.
Deployment automatically registers every valid fixture directory as a separate
tenant and seeds its messages under that tenant ID.

Create the tenant's first user with the admin endpoint. Keep the admin secret
out of browser code and shell history:

```text
POST /api/v1/admin/accounts/<account-id>/users
Authorization: Bearer <SOLVD_ADMIN_SECRET>
Content-Type: application/json

{
  "username": "owner@examplegym.com",
  "password": "a-long-unique-password",
  "role": "owner"
}
```

Create a distinct login identity for each gym. Usernames are unique across the
service, and a login cannot be reassigned or switched to another tenant through
the browser.

For per-tenant email-provider webhooks, rotate a secret once:

```text
POST /api/v1/admin/accounts/<account-id>/webhook-secret
Authorization: Bearer <SOLVD_ADMIN_SECRET>
```

The returned secret is shown only in that response. Send that tenant's email to
`POST /api/v1/webhooks/<account-id>/email` with the returned Bearer secret.

## When OpenAI is called

The server calls OpenAI only when all of these are true:

- The message is inbound, unread, and in the inbox.
- It is not spam, trash, sent mail, a draft, an auto-response, a bulk/list
  message, or mail from the gym itself.
- It has a human sender and a non-empty body.
- It is not a short acknowledgement such as “Sounds good, thank you.”
- The same Message-ID and content fingerprint have not already been processed.

Ambiguous human-written messages are drafted rather than silently skipped.
Skipped or failed messages show a **Draft with AI** control so the owner can
override the prefilter. OpenAI calls happen only in the API service; the key and
mailbox credentials never reach the browser.
