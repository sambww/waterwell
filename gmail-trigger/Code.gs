/**
 * Waterwell — Gmail Trigger (Google Apps Script)
 *
 * Polls Gmail for emails whose subject contains a configured phrase (default:
 * "has not received an estimate"), extracts the customer address from the
 * body, builds a shareable URL pointing at the waterwell depth-report page,
 * and creates a Gmail draft reply on the thread with the URL inserted.
 *
 * See README.md (same folder) for setup instructions.
 *
 * No API keys needed — Apps Script's built-in Maps service handles geocoding
 * under Google's free quota (1,000 geocodes/day).
 */

const CONFIG = {
  /** Match any email with this phrase in the subject (case-insensitive). */
  SUBJECT_PATTERN: 'has not received an estimate',

  /** Only look at threads from the last N days. */
  LOOKBACK_DAYS: 14,

  /** Label applied to processed threads (also used to exclude on next run). */
  LABEL_PROCESSED: 'Waterwell-Processed',

  /** Label applied if processing failed — surfaces issues for you to handle. */
  LABEL_NEEDS_REVIEW: 'Waterwell-Needs-Review',

  /** Where the report lives. */
  SHARE_URL_BASE: 'https://sambww.github.io/waterwell/',

  /** Signature block appended to draft replies. */
  SIGNATURE: [
    '',
    'Sam Ballard',
    'Ballard Water Well Company',
    '(832) 479-3557  ·  info@texaswaterwell.com',
    'texaswaterwell.com',
  ].join('\n'),

  /** Restrict geocoding to Texas to avoid junk matches. */
  GEOCODE_REGION: 'us',
  GEOCODE_BOUNDS: { sw: { lat: 25.0, lng: -107.0 }, ne: { lat: 37.0, lng: -93.0 } },

  /** Set to true to log what would happen without creating drafts. */
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

  const address = extractAddress_(subject, body);
  if (!address) {
    console.log(`No address found in "${subject}". Labeling for review.`);
    thread.addLabel(needsReview);
    return;
  }

  const geo = geocodeInTexas_(address);
  if (!geo) {
    console.log(`Geocoding failed for "${address}". Labeling for review.`);
    thread.addLabel(needsReview);
    return;
  }

  const url = buildShareUrl_(geo.formatted, geo.lat, geo.lng);
  const draftBody = renderDraftBody_(geo.formatted, url);

  if (CONFIG.DRY_RUN) {
    console.log(`[DRY RUN] Would draft reply with URL: ${url}`);
  } else {
    thread.createDraftReply(draftBody);
  }
  thread.addLabel(processed);
  console.log(`Processed: ${subject} -> ${url}`);
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
function extractAddress_(subject, body) {
  // 1. Labeled line
  const labelPatterns = [
    /\b(?:property\s+address|service\s+address|site\s+address|job\s+address)\s*[:|]\s*([^\n\r]+)/i,
    /\b(?:address|location|property|site)\s*[:|]\s*([^\n\r]+)/i,
  ];
  for (const pattern of labelPatterns) {
    const m = body.match(pattern);
    if (m) {
      const candidate = cleanCandidate_(m[1]);
      if (looksLikeAddress_(candidate)) return candidate;
    }
  }

  // 2. Subject
  const subjectCandidate = cleanCandidate_(stripSubjectPrefix_(subject));
  if (looksLikeAddress_(subjectCandidate)) return subjectCandidate;

  // 3. Body lines
  const lines = body.split(/\r?\n/);
  for (const raw of lines) {
    const candidate = cleanCandidate_(raw);
    if (looksLikeAddress_(candidate)) return candidate;
  }

  // 4. Two-line addresses ("123 Main St\nCity, TX 12345")
  for (let i = 0; i < lines.length - 1; i++) {
    const combined = cleanCandidate_(lines[i] + ', ' + lines[i + 1]);
    if (looksLikeAddress_(combined)) return combined;
  }

  return null;
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

function renderDraftBody_(address, url) {
  return [
    'Hi,',
    '',
    `Thanks for reaching out about ${address}. Here's a preliminary water-well depth analysis based on the 10 closest registered wells in the Texas Water Development Board database:`,
    '',
    url,
    '',
    'This gives a recommended target depth based on what\'s been drilled near you. Final pricing depends on a site visit — call (832) 479-3557 or reply to this email and we\'ll get on the calendar.',
    CONFIG.SIGNATURE,
  ].join('\n');
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
  const SAMPLE_SUBJECT = 'Lead 8412 has not received an estimate';
  const SAMPLE_BODY = [
    'A new lead has been waiting more than 48 hours for an estimate.',
    '',
    'Customer: Jane Doe',
    'Phone: (555) 555-1234',
    'Address: 1234 County Road 200, Liberty Hill, TX 78642',
    '',
    'Please follow up.',
  ].join('\n');

  const address = extractAddress_(SAMPLE_SUBJECT, SAMPLE_BODY);
  console.log('Extracted address:', address);
  if (!address) return;

  const geo = geocodeInTexas_(address);
  console.log('Geocoded:', JSON.stringify(geo));
  if (!geo) return;

  const url = buildShareUrl_(geo.formatted, geo.lat, geo.lng);
  console.log('URL:', url);
  console.log('--- Draft body ---');
  console.log(renderDraftBody_(geo.formatted, url));
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
