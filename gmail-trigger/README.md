# Waterwell Gmail Trigger

A Google Apps Script that watches your Gmail for Workiz "Has Not Received
Estimate" emails, extracts the customer address from the body, geocodes it,
and emails **you** a notification with a ready-to-paste Waterwell URL plus a
link back to the original thread.

The customer is **not** contacted automatically — you decide how/when to
respond in Workiz.

No API key needed — Apps Script's built-in Maps service handles geocoding
under Google's free quota.

## Deploy (~5 minutes, one-time)

1. Go to <https://script.google.com> while signed into the Gmail account that
   receives the estimate emails (`sam@texaswaterwell.com`).
2. Click **+ New project** (top left).
3. Rename it (top of window) from "Untitled project" to **Waterwell Email
   Trigger**.
4. Delete everything in the default `Code.gs` editor.
5. Open [`Code.gs`](Code.gs) on GitHub, click **Raw**, **Cmd+A**, **Cmd+C**.
   Paste into the Apps Script editor.
6. **Save** (⌘+S).

## Test the parser

Before letting it touch real emails:

1. In the Apps Script editor's top toolbar, set the function dropdown to
   **`testParse`**.
2. Click **Run**.
3. The first time you run anything, Google will pop up an authorization
   dialog. Click **Review permissions** → pick your Google account → "Advanced"
   → "Go to Waterwell Email Trigger (unsafe)" → **Allow**. It's labeled "unsafe"
   only because the script isn't published — it's yours, running in your
   account.
4. The **Execution log** at the bottom should print the extracted address,
   the geocoded result, and a preview of the notification email that would
   land in your inbox.

## Dry-run against your real inbox

This confirms the script picks up the right emails without sending anything:

1. Set the function dropdown to **`dryRunOnce`** → **Run**.
2. The Execution log prints one block per matching thread:
   ```
   [DRY RUN] Would email sam@texaswaterwell.com:
     Subject: Waterwell URL ready: Lenore Hampton — Livingston, TX
   Customer: Lenore Hampton
   Address:  239 Triple Creek Loop, Livingston, TX 77351, USA
   ...
   ```
3. No emails are sent. No labels are applied.

If real emails are being matched and parsed correctly, you're ready.

## Turn it on

1. Function dropdown → **`installTrigger`** → **Run**.
2. Execution log: `Installed 5-minute trigger.`
3. Done. Every 5 minutes the script runs `processNewEstimateEmails`. Each
   matching Workiz thread:
   - Gets parsed for customer name + address
   - Generates a Waterwell URL
   - Triggers a notification email to `NOTIFY_EMAIL` (default
     `sam@texaswaterwell.com`)
   - Gets a `Waterwell-Processed` label so it isn't handled twice

Threads where parsing fails get a `Waterwell-Needs-Review` label instead —
worth scanning that label occasionally to catch any unusual email formats.

## Tuning

All the knobs live in the `CONFIG` object at the top of `Code.gs`:

| Setting              | What it does |
|----------------------|----|
| `SUBJECT_PATTERN`    | Phrase the email subject must contain |
| `LOOKBACK_DAYS`      | Only scan threads from the last N days |
| `LABEL_PROCESSED`    | Threads already handled get this label |
| `LABEL_NEEDS_REVIEW` | Threads where parsing failed — check these manually |
| `SHARE_URL_BASE`     | URL prefix for the report |
| `NOTIFY_EMAIL`       | Address that receives the URL notification |
| `DRY_RUN`            | `true` = log only, no notification sent |

After editing, save (⌘+S) — no redeploy needed.

## Watch what happens

- Apps Script editor → **Executions** (left sidebar) shows every run's log.
- Gmail → search `label:Waterwell-Needs-Review` for any threads it couldn't
  parse. Open one, share the body text, and we'll tune the parser.

## Turn it off

Run **`uninstallTrigger`** once. The script stays in your account but no
longer runs on a schedule.
