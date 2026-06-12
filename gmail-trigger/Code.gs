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

  // ---- Customer-facing email (off until verified) -------------------------
  /** Master switch: also email the customer using their parsed email. */
  SEND_TO_CUSTOMER: false,

  /** Even with SEND_TO_CUSTOMER on, log what would be sent and don't send.
   *  Flip to false once you've watched a few real notifications and confirmed
   *  the customer email + phone are being parsed correctly. */
  CUSTOMER_DRY_RUN: true,

  /** CC'd on every customer-facing email — keeps a copy in your inbox. */
  CUSTOMER_CC: 'sam@texaswaterwell.com',
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

  const contact = extractCustomerContact_(body);
  const url = buildShareUrl_(geo.formatted, geo.lat, geo.lng);

  // Customer email — gated by SEND_TO_CUSTOMER + CUSTOMER_DRY_RUN.
  const customerStatus = maybeSendCustomerEmail_(extracted, contact, geo, url);

  const notif = buildNotification_(extracted, contact, geo, url, customerStatus);

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

function buildNotification_(extracted, contact, geo, url, customerStatus) {
  const fullName = extracted.customerFullName || '(see original email)';
  const subjectName = extracted.customerFullName || 'New lead';
  const shortLocation = shortAddr_(geo.formatted);
  const confidenceNote = extracted.confident
    ? ''
    : '[!] Address was parsed via fuzzy fallback — double-check before using.';

  // Compute the same recommendation as the website by hitting the public tile
  // data and running the clustering algorithm here.
  let analysisLines = [];
  try {
    const analysis = buildAnalysis_(geo.lat, geo.lng);
    if (analysis) analysisLines = formatAnalysis_(analysis);
  } catch (e) {
    console.warn('Analysis build failed:', e);
  }

  const lines = [`Customer: ${fullName}`];
  if (contact.email) lines.push(`  Email:  ${contact.email}`);
  if (contact.phone) lines.push(`  Phone:  ${contact.phone}`);
  lines.push(`Address:  ${geo.formatted}`);
  if (confidenceNote) lines.push(confidenceNote);
  if (analysisLines.length) {
    lines.push('');
    lines.push.apply(lines, analysisLines);
  }
  lines.push('');
  lines.push('Full report:');
  lines.push(url);
  if (customerStatus) {
    lines.push('');
    lines.push(`Customer email: ${customerStatus}`);
  }

  return {
    subject: `Waterwell URL ready: ${subjectName} — ${shortLocation}`,
    body: lines.join('\n'),
  };
}

// ----------------------------------------------------------------------------
// Customer contact extraction
// ----------------------------------------------------------------------------

function extractCustomerContact_(body) {
  let email = null;
  let phone = null;

  // Email — try labeled lines first
  const labeledEmail = body.match(
    /\b(?:client\s+email|customer\s+email|e[- ]?mail|email)\s*[:|]\s*([^\s<>"']+@[^\s<>"']+\.[A-Za-z]{2,})/i
  );
  if (labeledEmail) {
    email = labeledEmail[1].trim().toLowerCase();
  } else {
    // Fall back to any email in the body that isn't a Workiz/internal address.
    const anyEmail = body.match(/[\w.+-]+@[\w-]+\.[\w.-]+/g);
    if (anyEmail) {
      for (const candidate of anyEmail) {
        const lower = candidate.toLowerCase();
        if (!isInternalEmail_(lower)) { email = lower; break; }
      }
    }
  }

  // Phone — labeled first; fall back to anything that looks like a US phone.
  const labeledPhone = body.match(
    /\b(?:client\s+phone|customer\s+phone|phone|tel)\s*[:|]\s*([+\d()\-\s.]{7,30})/i
  );
  if (labeledPhone) {
    phone = labeledPhone[1].replace(/\s+/g, ' ').trim();
  } else {
    const m = body.match(/\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}/);
    if (m) phone = m[0].trim();
  }
  return { email: email, phone: phone };
}

function isInternalEmail_(addr) {
  return (
    /@(workiz|texaswaterwell|google|gmail|mailgun|mailchimp)\.com$/i.test(addr) ||
    /@.*\.(workiz|mailgun)\.(com|net)$/i.test(addr) ||
    /^bounce\+/i.test(addr) ||
    /^notifications@/i.test(addr)
  );
}

// ----------------------------------------------------------------------------
// Customer-facing email
// ----------------------------------------------------------------------------

/**
 * Returns a status string suitable for the Sam notification, or '' if the
 * feature is off entirely. Examples:
 *   "Sent to jane@example.com (CC: sam@texaswaterwell.com)"
 *   "[DRY RUN] Would send to jane@example.com"
 *   "Skipped — no valid email found"
 *   "Skipped — low-confidence address match"
 */
function maybeSendCustomerEmail_(extracted, contact, geo, url) {
  if (!CONFIG.SEND_TO_CUSTOMER) return '';

  if (!extracted.confident) {
    return 'Skipped — low-confidence address match';
  }
  if (!contact.email || isInternalEmail_(contact.email)) {
    return 'Skipped — no valid customer email parsed';
  }
  if (CONFIG.DRY_RUN) {
    return '[GLOBAL DRY RUN] Would send to ' + contact.email;
  }

  const msg = buildCustomerEmail_(extracted, geo, url);

  if (CONFIG.CUSTOMER_DRY_RUN) {
    console.log(`[CUSTOMER DRY RUN] Would send to ${contact.email}`);
    console.log(`  Subject: ${msg.subject}`);
    console.log(msg.body);
    return '[DRY RUN] Would send to ' + contact.email;
  }

  GmailApp.sendEmail(contact.email, msg.subject, msg.body, {
    cc: CONFIG.CUSTOMER_CC,
    name: 'Ballard Water Well Company',
  });
  return `Sent to ${contact.email} (CC: ${CONFIG.CUSTOMER_CC})`;
}

function buildCustomerEmail_(extracted, geo, url) {
  const greeting = extracted.customerFirstName ? `Hi ${extracted.customerFirstName},` : 'Hi,';
  return {
    subject: `Your water well depth estimate for ${shortAddr_(geo.formatted)}`,
    body: [
      greeting,
      '',
      `Thanks for reaching out to Ballard Water Well Company about your project at ${geo.formatted}.`,
      '',
      "Based on the 10 nearest registered water wells in the Texas Water Development Board database, here's a preliminary look at what drilling depth makes sense for your property:",
      '',
      url,
      '',
      "The report shows the closest historical wells with their depths and our recommended target depth based on actual local drilling history. The final number for your site depends on a walk-through — call or reply to this email when you're ready and we'll get on the calendar.",
      '',
      'Sam Ballard',
      'Ballard Water Well Company',
      '(832) 479-3557  ·  info@texaswaterwell.com',
      'texaswaterwell.com',
    ].join('\n'),
  };
}

// ----------------------------------------------------------------------------
// Well-depth analysis (same algorithm as the website)
// ----------------------------------------------------------------------------

const TILE_SIZE = 0.25;
const TILES_BASE_URL = 'https://sambww.github.io/waterwell/data';

function buildAnalysis_(lat, lng) {
  const wells = fetchNearestWells_(lat, lng, 10);
  if (!wells || wells.length === 0) return null;
  return { wells, rec: recommendClusters_(wells) };
}

function fetchNearestWells_(lat, lng, k) {
  // Expand the tile-grid radius until we have enough candidates.
  for (let radius = 1; radius <= 4; radius++) {
    const tlat = Math.floor(lat / TILE_SIZE);
    const tlon = Math.floor(lng / TILE_SIZE);
    const candidates = [];
    for (let dy = -radius; dy <= radius; dy++) {
      for (let dx = -radius; dx <= radius; dx++) {
        const tileId = `${tlat + dy}_${tlon + dx}`;
        try {
          const resp = UrlFetchApp.fetch(
            `${TILES_BASE_URL}/${tileId}.json`,
            { muteHttpExceptions: true }
          );
          if (resp.getResponseCode() !== 200) continue;
          const tile = JSON.parse(resp.getContentText());
          tile.forEach((w) => {
            candidates.push({ w: w, d: haversineMi_(lat, lng, w[1], w[2]) });
          });
        } catch (e) { /* tile missing, skip */ }
      }
    }
    if (candidates.length >= k * 3 || radius === 4) {
      candidates.sort((a, b) => a.d - b.d);
      return candidates.slice(0, k);
    }
  }
  return [];
}

function haversineMi_(lat1, lon1, lat2, lon2) {
  const R = 3958.7613;
  const p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
  const dp = (lat2 - lat1) * Math.PI / 180;
  const dl = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function recommendClusters_(wells) {
  const depths = wells.map((x) => x.w[3]).slice().sort((a, b) => a - b);
  const clusters = [];
  let i = 0;
  while (i < depths.length) {
    let end = i;
    while (end + 1 < depths.length && depths[end + 1] - depths[i] <= 50) end++;
    const count = end - i + 1;
    if (count >= 3) {
      clusters.push({ min: depths[i], max: depths[end], count: count });
      i = end + 1;
    } else {
      i++;
    }
  }
  clusters.sort((a, b) => b.max - a.max);

  if (clusters.length === 0) {
    const deepest = depths[depths.length - 1];
    return {
      mode: 'deepest',
      primary: { depth: deepest, count: 1, min: deepest, max: deepest },
      alternatives: [],
    };
  }
  const p = clusters[0];
  return {
    mode: 'cluster',
    primary: { depth: p.max, count: p.count, min: p.min, max: p.max },
    alternatives: clusters.slice(1).map((c) => ({
      depth: c.max, count: c.count, min: c.min, max: c.max,
    })),
  };
}

function formatAnalysis_(analysis) {
  const { rec, wells } = analysis;
  const fmt = (n) => Math.round(n);
  const lines = [];
  if (rec.mode === 'cluster') {
    lines.push(
      `Recommended depth: ${fmt(rec.primary.depth)} ft  ` +
      `(${rec.primary.count} wells in ${fmt(rec.primary.min)}–${fmt(rec.primary.max)} ft band)`
    );
    rec.alternatives.forEach((a, i) => {
      const lbl = rec.alternatives.length > 1 ? `Alternative #${i + 1}` : 'Alternative';
      lines.push(
        `${lbl}: ${fmt(a.depth)} ft  ` +
        `(${a.count} wells in ${fmt(a.min)}–${fmt(a.max)} ft band)`
      );
    });
  } else {
    lines.push(
      `Recommended depth: ${fmt(rec.primary.depth)} ft  ` +
      `(deepest of 10; no cluster of 3+ within 50 ft)`
    );
  }
  const minD = Math.min.apply(Math, wells.map((x) => x.w[3]));
  const maxD = Math.max.apply(Math, wells.map((x) => x.w[3]));
  lines.push(`Range observed: ${fmt(minD)}–${fmt(maxD)} ft across ${wells.length} wells`);
  return lines;
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
 * Mark every currently-matching thread as already-handled, with NO emails
 * sent. Use this once after deployment if you want to ignore the backlog and
 * only get notifications for new emails going forward.
 */
function markBacklogProcessed() {
  const processed = getOrCreateLabel_(CONFIG.LABEL_PROCESSED);
  const query = [
    `subject:"${CONFIG.SUBJECT_PATTERN}"`,
    `-label:"${CONFIG.LABEL_PROCESSED}"`,
    `-label:"${CONFIG.LABEL_NEEDS_REVIEW}"`,
    `newer_than:${CONFIG.LOOKBACK_DAYS}d`,
  ].join(' ');
  const threads = GmailApp.search(query, 0, 100);
  threads.forEach((t) => t.addLabel(processed));
  console.log(`Marked ${threads.length} backlog thread(s) as processed (no emails sent).`);
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
  // Includes the new client email + phone fields so you can see the parse.
  const SAMPLE_SUBJECT = 'Has Not Received Estimate';
  const SAMPLE_BODY = [
    'JANE DOE located at 1234 Triple Creek Loop, Livingston, Texas 77351 would like an estimate for a Residential Well Install',
    '',
    'Client Email: jane.doe@example.com',
    'Client Phone: (555) 555-1234',
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
  console.log('Address extracted:', JSON.stringify(extracted));
  if (!extracted) return;

  const contact = extractCustomerContact_(SAMPLE_BODY);
  console.log('Contact extracted:', JSON.stringify(contact));

  const geo = geocodeInTexas_(extracted.address);
  console.log('Geocoded:', JSON.stringify(geo));
  if (!geo) return;

  const url = buildShareUrl_(geo.formatted, geo.lat, geo.lng);
  const customerStatus = maybeSendCustomerEmail_(extracted, contact, geo, url);
  const notif = buildNotification_(extracted, contact, geo, url, customerStatus);
  console.log('--- Sam notification ---');
  console.log(`To:      ${CONFIG.NOTIFY_EMAIL}`);
  console.log(`Subject: ${notif.subject}`);
  console.log('Body:');
  console.log(notif.body);

  // Always show what the customer email would look like, regardless of flags.
  console.log('--- Customer-facing email (preview, never sent from testParse) ---');
  const customer = buildCustomerEmail_(extracted, geo, url);
  console.log(`Subject: ${customer.subject}`);
  console.log('Body:');
  console.log(customer.body);
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
