# Waterwell Gmail Trigger

A Google Apps Script that watches your Gmail for emails whose subject contains
"has not received an estimate", extracts the customer address from the body,
and creates a draft reply with a Waterwell URL pre-filled.

No API key needed — Apps Script's built-in Maps service handles geocoding
under Google's free quota.

## Deploy (~5 minutes, one-time)

1. Go to <https://script.google.com> while signed into the Gmail account that
   receives the estimate emails.
2. Click **+ New project** (top left).
3. Rename it (top of window) from "Untitled project" to **Waterwell Email
   Trigger**.
4. Delete everything in the default `Code.gs` editor.
5. Open [`Code.gs`](Code.gs) on GitHub, click **Raw**, **Cmd+A**, **Cmd+C**.
   Paste into the Apps Script editor.
6. **Save** (⌘+S).

## Test the parser

Before letting it touch real emails:

1. In the Apps Script editor's top toolbar, the function dropdown defaults to
   `processNewEstimateEmails`. Change it to **`testParse`**.
2. Click **Run**.
3. The first time you run anything, Google will pop up an authorization
   dialog. Click **Review permissions** → pick your Google account → "Advanced"
   → "Go to Waterwell Email Trigger (unsafe)" → **Allow**. (It's labeled "unsafe"
   only because the script isn't published — it's yours, running in your
   account.)
4. The **Execution log** at the bottom should show:
   ```
   Extracted address: 1234 County Road 200, Liberty Hill, TX 78642
   Geocoded: {"lat":30.66...,"lng":-97.92...,"formatted":"..."}
   URL: https://sambww.github.io/waterwell/?address=...
   --- Draft body ---
   Hi, …
   ```

If the URL looks right, the parser works.

## Dry-run against your real inbox

This lets you confirm the script picks up the right emails without writing
anything yet:

1. Change the function dropdown to **`dryRunOnce`**.
2. Click **Run**.
3. The Execution log will print one line per matching thread:
   `Processed: <subject> -> <URL>` or `No address found in "..."`.
4. No drafts are created. No labels are applied.

If real emails are being matched and parsed correctly, you're ready.

## Turn it on

1. Function dropdown → **`installTrigger`** → **Run**.
2. Execution log: `Installed 5-minute trigger.`
3. Done. From now on, every 5 minutes the script runs `processNewEstimateEmails`
   in the background. Matching threads get a Gmail draft reply with the URL,
   and a `Waterwell-Processed` label so the same thread isn't handled twice.

## Tuning

All the knobs live in the `CONFIG` object at the top of `Code.gs`:

| Setting              | What it does |
|----------------------|----|
| `SUBJECT_PATTERN`    | The phrase the email subject must contain |
| `LOOKBACK_DAYS`      | Only scan threads from the last N days |
| `LABEL_PROCESSED`    | Threads already handled get this label |
| `LABEL_NEEDS_REVIEW` | Threads where parsing failed get this — check these manually |
| `SHARE_URL_BASE`     | The URL prefix for the report |
| `SIGNATURE`          | Text appended to every draft reply |
| `DRY_RUN`            | `true` = log only, don't create drafts |

After editing, save (⌘+S) — no redeploy needed.

## Watch what happens

- Apps Script editor → **Executions** (left sidebar) shows every run's log.
- Gmail → label `Waterwell-Needs-Review` is where the trigger sends threads it
  couldn't parse. Open one, tell me what's in the body, and I'll tune the
  parser.

## Turn it off

Run **`uninstallTrigger`** once. The script stays in your account but won't
run on a schedule.
