/**
 * Waterwell — Gmail Trigger (Google Apps Script)
 *
 * Polls Gmail for emails whose subject contains a configured phrase (default:
 * "Has Not Received Estimate"), extracts the customer address from the body,
 * builds a shareable URL pointing at the Waterwell depth-report page, and
 * emails a notification to you with the URL + customer info + a link back to
 * the original thread. (The customer is NOT contacted automatically.)
 *
 * See README.md (same folder) for setup instructions.
 *
 * No API keys needed — Apps Script's built-in Maps service handles geocoding
 * under Google's free quota (1,000 geocodes/day).
 */

const CONFIG = {
  /** Match any email with this phrase in the subject (case-insensitive). */
  SUBJECT_PATTERN: 'Has Not Received Estimate',

  /** Only look at threads from the last N days. */
  LOOKBACK_DAYS: 14,

  /** Label applied to processed threads (also used to exclude on next run). */
  LABEL_PROCESSED: 'Waterwell-Processed',

  /** Label applied if processing failed — surfaces issues for you to handle. */
  LABEL_NEEDS_REVIEW: 'Waterwell-Needs-Review',

  /** Where the report lives. */
  SHARE_URL_BASE: 'https://sambww.github.io/waterwell/',

  /** Restrict geocoding to Texas to avoid junk matches. */
  GEOCODE_REGION: 'us',
  GEOCODE_BOUNDS: { sw: { lat: 25.0, lng: -107.0 }, ne: { lat: 37.0, lng: -93.0 } },

  /** When a matching email is parsed, send a notification here with the URL. */
  NOTIFY_EMAIL: 'sam@texaswaterwell.com',

  /** Set to true to log what would happen without sending any notification. */
  DRY_RUN: false,
};

// ----------------------------------------------------------------------------
// Main loop — call this on a 5-minute time trigger.
// ----------------------------------------------------------------------------
function processNewEstimateEmails() {
  const processed = getOrCreateLabel_(CONFIG.LABEL_PROCESSED);
  const needsReview = getOrCreateLabel_(CONFIG.LABEL_NEEDS_REVIEW);

  const query = [
    `subject:"${CONFIG.SUBJECT_PATTERN}"`,
    `-label:"${CONFIG.LABEL_PROCESSED}"`,
    `-label:"${CONFIG.LABEL_NEEDS_REVIEW}"`,
    `newer_than:${CONFIG.LOOKBACK_DAYS}d`,
  ].join(' ');

  const threads = GmailApp.search(query, 0, 25);
  console.log(`Found ${threads.length} new matching thread(s).`);

  threads.forEach((thread) => {
    try {
      handleThread_(thread, processed, needsReview);
    } catch (err) {
      console.error(`Thread "${thread.getFirstMessageSubject()}" failed:`, err);
      thread.addLabel(needsReview);
    }
  });
}

function handleThread_(thread, processed, needsReview) {
  const msg = thread.getMessages().slice(-1)[0]; // newest in thread
  const subject = msg.getSubject();
  const body = msg.getPlainBody();

  const extracted = extractAddress_(subject, body);
  if (!extracted) {
    console.log(`No address found in "${subject}".${CONFIG.DRY_RUN ? '' : ' Labeling for review.'}`);
    if (!CONFIG.DRY_RUN) thread.addLabel(needsReview);
    return;
  }

  const geo = geocodeInTexas_(extracted.address);
  if (!geo) {
    console.log(`Geocoding failed for "${extracted.address}".${CONFIG.DRY_RUN ? '' : ' Labeling for review.'}`);
    if (!CONFIG.DRY_RUN) thread.addLabel(needsReview);
    return;
  }

  const url = buildShareUrl_(geo.formatted, geo.lat, geo.lng);
  const notif = buildNotification_(thread, extracted, geo, url);

  if (CONFIG.DRY_RUN) {
    console.log(`[DRY RUN] Would email ${CONFIG.NOTIFY_EMAIL}:`);
    console.log(`  Subject: ${notif.subject}`);
    console.log(notif.body);
    return;  // dry run = no side effects
  }
  GmailApp.sendEmail(CONFIG.NOTIFY_EMAIL, notif.subject, notif.body);
  thread.addLabel(processed);
  console.log(`Notified ${CONFIG.NOTIFY_EMAIL}: ${notif.subject}`);
}

function buildNotification_(thread, extracted, geo, url) {
  const fullName = extracted.customerFullName || '(see original email)';
  const subjectName = extracted.customerFullName || 'New lead';
  const shortLocation = shortAddr_(geo.formatted);
  const threadUrl = `https://mail.google.com/mail/u/0/#inbox/${thread.getId()}`;
  const confidenceNote = extracted.confident
    ? ''
    : '\n[!] Address was parsed via fuzzy fallback — double-check before sending.\n';

  return {
    subject: `Waterwell URL ready: ${subjectName} — ${shortLocation}`,
    body: [
      `Customer: ${fullName}`,
      `Address:  ${geo.formatted}`,
      confidenceNote.trim(),
      '',
      'Waterwell report:',
      url,
      '',
      'Original Workiz email:',
      threadUrl,
    ].filter(line => line !== '').join('\n'),
  };
}

function shortAddr_(formatted) {
  // "239 Triple Creek Loop, Livingston, TX 77351, USA" → "Livingston, TX"
  const parts = formatted.split(',').map(s => s.trim());
  if (parts.length >= 3) return parts[1] + ', ' + parts[2].split(' ')[0];
  if (parts.length === 2) return parts[1];
  return formatted;
}

// ----------------------------------------------------------------------------
// Address extraction
// ----------------------------------------------------------------------------

/**
 * Tries several strategies, in order of confidence:
 *   1. Lines labeled "Address: ..." (or similar) — most reliable
 *   2. The subject line itself (if it looks like an address)
 *   3. Any line in the body that looks like a US street + city + TX
 */
/**
 * Returns { address, confident, customerFirstName } or null if no address.
 *   confident: true only for the high-confidence Workiz pattern; controls
 *              whether the notification flags the parse for manual review.
 *   customerFirstName: e.g. "Lenore" — used for the email greeting; may be null.
 */
function extractAddress_(subject, body) {
  // Collapse whitespace so the regex works across line wraps and the HTML-to-text
  // conversion Gmail does (which can sprinkle line breaks anywhere).
  const flat = body.replace(/\s+/g, ' ');

  // 1. Workiz-style "[Name] located at [ADDRESS] would like an estimate ..."
  const workizMatch = flat.match(
    /\b([A-Za-z][A-Za-z .'\-]{1,60}?)\s+located at\s+(.+?)\s+would like an estimate/i
  );
  if (workizMatch) {
    const candidate = cleanCandidate_(workizMatch[2]);
    if (looksLikeAddress_(candidate)) {
      const customerFirstName = firstNameFrom_(workizMatch[1]);
      const customerFullName = titleCase_(workizMatch[1].trim());
      return { address: candidate, confident: true, customerFirstName, customerFullName };
    }
  }

  // 2. "Service Address:" / "Property Address:" / "Address:" labeled line
  const labelPatterns = [
    /\b(?:property\s+address|service\s+address|site\s+address|job\s+address)\s*[:|]\s*([^\n\r]+)/i,
    /\b(?:address|location|property|site)\s*[:|]\s*([^\n\r]+)/i,
  ];
  for (const pattern of labelPatterns) {
    const m = body.match(pattern);
    if (m) {
      const candidate = cleanCandidate_(m[1]);
      if (looksLikeAddress_(candidate)) {
        return { address: candidate, confident: false, customerFirstName: null, customerFullName: null };
      }
    }
  }

  // 3. Subject sometimes has the address tacked on
  const subjectCandidate = cleanCandidate_(stripSubjectPrefix_(subject));
  if (looksLikeAddress_(subjectCandidate)) {
    return { address: subjectCandidate, confident: false, customerFirstName: null };
  }

  // 4. Any body line that looks like a US street address
  const lines = body.split(/\r?\n/);
  for (const raw of lines) {
    const candidate = cleanCandidate_(raw);
    if (looksLikeAddress_(candidate)) {
      return { address: candidate, confident: false, customerFirstName: null, customerFullName: null };
    }
  }

  // 5. Two-line addresses ("123 Main St\nCity, TX 12345")
  for (let i = 0; i < lines.length - 1; i++) {
    const combined = cleanCandidate_(lines[i] + ', ' + lines[i + 1]);
    if (looksLikeAddress_(combined)) {
      return { address: combined, confident: false, customerFirstName: null, customerFullName: null };
    }
  }

  return null;
}

function firstNameFrom_(rawName) {
  if (!rawName) return null;
  const titled = titleCase_(rawName);
  const first = titled.trim().split(/\s+/)[0] || '';
  // Reject anything that doesn't look like a real name (numbers, etc.)
  return /^[A-Z][A-Za-z'\-]{1,30}$/.test(first) ? first : null;
}

function titleCase_(s) {
  if (!s) return '';
  return s.toLowerCase().replace(/(?:^|[\s\-'])\S/g, c => c.toUpperCase());
}

function stripSubjectPrefix_(subject) {
  // "Lead 1234 has not received an estimate — 123 Main St, ..." → "123 Main St, ..."
  let s = subject || '';
  s = s.replace(new RegExp(CONFIG.SUBJECT_PATTERN, 'i'), '');
  s = s.replace(/^\s*[:\-—–|]\s*/, '');
  return s.trim();
}

function cleanCandidate_(text) {
  if (!text) return '';
  return text
    .replace(/\s+/g, ' ')
    .replace(/^[\s,;|*•\-–—]+|[\s,;|*•\-–—]+$/g, '')
    .trim();
}

function looksLikeAddress_(text) {
  if (!text || text.length < 8 || text.length > 200) return false;
  if (!/\d/.test(text)) return false;                              // must contain a digit
  if (/^\d+$/.test(text)) return false;                            // not just a number (e.g. lead ID)
  if (!/[A-Za-z]{3,}/.test(text)) return false;                    // some letters
  const hasState = /\b(TX|Tex|Texas)\b/i.test(text);
  const hasZip = /\b\d{5}(-\d{4})?\b/.test(text);
  const hasComma = text.includes(',');
  const looksStreetlike = /\b(rd|road|st|street|dr|drive|ln|lane|hwy|highway|ave|avenue|blvd|boulevard|cir|circle|ct|court|trl|trail|pl|place|cr|fm|county\s+road|farm[- ]to[- ]market)\b/i.test(text);
  // Need at least two of: TX/Texas, comma, zip, street-type word
  let score = 0;
  if (hasState) score++;
  if (hasZip) score++;
  if (hasComma) score++;
  if (looksStreetlike) score++;
  return score >= 2;
}

// ----------------------------------------------------------------------------
// Geocoding (Apps Script's built-in Maps service — free, no API key)
// ----------------------------------------------------------------------------

function geocodeInTexas_(address) {
  const b = CONFIG.GEOCODE_BOUNDS;
  let response;
  try {
    response = Maps.newGeocoder()
      .setRegion(CONFIG.GEOCODE_REGION)
      .setBounds(b.sw.lat, b.sw.lng, b.ne.lat, b.ne.lng)
      .geocode(address);
  } catch (e) {
    console.error('Maps.geocode threw:', e);
    return null;
  }
  if (response.status !== 'OK' || !response.results.length) return null;
  const r = response.results[0];
  return {
    lat: r.geometry.location.lat,
    lng: r.geometry.location.lng,
    formatted: r.formatted_address,
  };
}

// ----------------------------------------------------------------------------
// URL + draft body
// ----------------------------------------------------------------------------

function buildShareUrl_(address, lat, lng) {
  const params =
    'address=' + encodeURIComponent(address) +
    '&lat=' + lat.toFixed(6) +
    '&lng=' + lng.toFixed(6);
  return CONFIG.SHARE_URL_BASE + '?' + params;
}


// ----------------------------------------------------------------------------
// Labels
// ----------------------------------------------------------------------------

function getOrCreateLabel_(name) {
  return GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
}

// ----------------------------------------------------------------------------
// One-time setup — run this once to install the 5-minute time trigger.
// ----------------------------------------------------------------------------
function installTrigger() {
  ScriptApp.getProjectTriggers().forEach((t) => {
    if (t.getHandlerFunction() === 'processNewEstimateEmails') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('processNewEstimateEmails')
    .timeBased()
    .everyMinutes(5)
    .create();
  console.log('Installed 5-minute trigger.');
}

/**
 * Remove the `Waterwell-Processed` and `Waterwell-Needs-Review` labels from
 * every thread that has them. Use this if you want to reprocess everything
 * (e.g. after fixing a bug). Doesn't delete the labels, just unlabels.
 */
function clearWaterwellLabels() {
  let removed = 0;
  [CONFIG.LABEL_PROCESSED, CONFIG.LABEL_NEEDS_REVIEW].forEach((name) => {
    const label = GmailApp.getUserLabelByName(name);
    if (!label) return;
    let threads;
    do {
      threads = label.getThreads(0, 100);
      threads.forEach((t) => { t.removeLabel(label); removed++; });
    } while (threads.length > 0);
  });
  console.log(`Removed Waterwell labels from ${removed} thread(s).`);
}

function uninstallTrigger() {
  ScriptApp.getProjectTriggers().forEach((t) => {
    if (t.getHandlerFunction() === 'processNewEstimateEmails') {
      ScriptApp.deleteTrigger(t);
    }
  });
  console.log('Removed triggers.');
}

// ----------------------------------------------------------------------------
// Test helpers — try these before turning on the trigger.
// ----------------------------------------------------------------------------

/**
 * Paste a real (or made-up) email's subject + body here, then run this from
 * the Apps Script editor. It logs what would happen — no Gmail writes.
 */
function testParse() {
  // A real-shape Workiz auto-reply body (PII swapped for fake details).
  const SAMPLE_SUBJECT = 'Has Not Received Estimate';
  const SAMPLE_BODY = [
    'JANE DOE located at 1234 Triple Creek Loop, Livingston, Texas 77351 would like an estimate for a Residential Well Install',
    '',
    'POLK',
    'Just Planning & Getting Quotes',
    'Residential Home & Irrigation',
    'No, this will be the only water well',
    'No, there is no community water available',
    '',
    '50gpm - 5Hp - Large Estate & Irrigation (15 heads/zone)',
  ].join('\n');

  const extracted = extractAddress_(SAMPLE_SUBJECT, SAMPLE_BODY);
  console.log('Extracted:', JSON.stringify(extracted));
  if (!extracted) return;

  const geo = geocodeInTexas_(extracted.address);
  console.log('Geocoded:', JSON.stringify(geo));
  if (!geo) return;

  const url = buildShareUrl_(geo.formatted, geo.lat, geo.lng);
  // testParse doesn't have a real thread, so fake a thread-like object for the
  // notification preview.
  const fakeThread = { getId: () => 'FAKE_THREAD_ID' };
  const notif = buildNotification_(fakeThread, extracted, geo, url);
  console.log('--- Notification email ---');
  console.log(`To:      ${CONFIG.NOTIFY_EMAIL}`);
  console.log(`Subject: ${notif.subject}`);
  console.log('Body:');
  console.log(notif.body);
}

/**
 * Runs the full loop once but only logs — no Gmail writes anywhere.
 * Useful to confirm parsing works against your actual inbox before going live.
 */
function dryRunOnce() {
  const original = CONFIG.DRY_RUN;
  CONFIG.DRY_RUN = true;
  try { processNewEstimateEmails(); }
  finally { CONFIG.DRY_RUN = original; }
}
