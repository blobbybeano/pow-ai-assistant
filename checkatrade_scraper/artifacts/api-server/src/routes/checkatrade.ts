import { Router } from "express";
import { chromium, type Browser, type Page, type BrowserContext } from "playwright";
import type { Response } from "express";
import { db, appSettings } from "@workspace/db";
import { eq, sql } from "drizzle-orm";
import { pollForLoginOtp, readRecentEnquiries, extractPostcode } from "../imap";
import { startMonitor, stopMonitor, isMonitorActive } from "../monitor";

const router = Router();

let browser: Browser | null = null;
let page: Page | null = null;
let sseClients: Response[] = [];

interface Lead {
  customerName: string;
  email: string;
  phone: string;
  address: string;
  jobTitle: string;   // bold job-type heading on the detail page
  message: string;    // customer's typed message from the "Message" section
  profile: "London" | "Midlands" | "Unknown";
  sourceUrl: string;
}

/** Determine which Checkatrade profile a lead belongs to based on its UK postcode.
 *  London profile = Greater London + Home Counties (south of Reading).
 *  Midlands profile = anything further north. */
function detectProfile(locationText: string): "London" | "Midlands" | "Unknown" {
  const match = locationText.toUpperCase().match(/\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*\d/);
  if (!match) return "Unknown";
  const area = match[1].replace(/\d+.*/, ""); // strip trailing digits → pure letter area code
  const londonOrSouth = new Set([
    // Inner London
    "E","EC","N","NW","SE","SW","W","WC",
    // Outer / Greater London
    "BR","CR","DA","EN","HA","IG","KT","RM","SM","TW","UB","WD",
    // Home Counties & South East (south/southwest of Reading)
    "AL","CM","CO","CT","GU","HP","LU","ME","MK","OX","PO","RG","RH","SL","SG","SO","SS","TN","BN",
  ]);
  return londonOrSouth.has(area) ? "London" : "Midlands";
}

let latestLeads: Lead[] = [];
/** Set to true once OTP login is complete (manual or auto) — prevents double-completion. */
let autoLoginResolved = false;
let autoFlowRunning = false;

function broadcast(event: string, data: unknown) {
  const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  sseClients = sseClients.filter((res) => !res.writableEnded);
  sseClients.forEach((res) => res.write(payload));
}

/** Parse job card summaries from the raw innerText of the /jobs page.
 *  Each card in the text follows the pattern:
 *    [Job Title]
 *    Interested          ← badge, may be on same or adjacent line
 *    [Customer Name]
 *    [City, POSTCODE]
 *    New message / You have accepted / Reply / Created ...
 *
 *  We anchor on the "City, POSTCODE" line and look backwards for name + title. */
function parseJobCards(text: string): Array<{
  title: string;
  customer: string;
  location: string;
  postcode: string;
}> {
  const locationRe = /^(.+),\s+([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\s*$/i;
  const navNoise = new Set([
    "Interested","New","New message","Reply","Respond now","Jobs","Home","Chats","Campaigns",
    "My account","My billing","Grow my business","Help & support","Preferences",
    "Sorted by recent activity","All filters","Pow Wash",
  ]);
  const noiseRe = /^(Created|Unread|You have|Member ID|Respond|\d+$|87$|99\+?$)/i;

  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const cards: Array<{ title: string; customer: string; location: string; postcode: string }> = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const locMatch = line.match(locationRe);
    if (!locMatch) continue;

    const postcode = locMatch[2].toUpperCase().replace(/\s+/, " ");
    const location = line;

    // Scan backwards (up to 6 lines) skipping noise to find customer name then job title
    let customer = "";
    let title = "";
    for (let j = i - 1; j >= Math.max(0, i - 8); j--) {
      const prev = lines[j];
      if (navNoise.has(prev) || noiseRe.test(prev)) continue;
      if (!customer) {
        customer = prev;
      } else if (!title) {
        title = prev;
        break;
      }
    }

    cards.push({ title, customer, location, postcode });
  }

  return cards;
}

/** Extract a UK phone number from plain text. */
function extractPhone(text: string): string {
  const m = text.match(/(\+44[\s-]?7\d{3}[\s-]?\d{6}|0\d{3,4}[\s-]?\d{6,7}|07\d{9})/);
  return m?.[0] ?? "";
}

/** Extract an email address from plain text. */
function extractEmail(text: string): string {
  const m = text.match(/[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/);
  return m?.[0] ?? "";
}

/** Member IDs are account-specific and must be supplied by the deployer. */
const PROFILE_MEMBER_ID: Record<"London" | "Midlands", string> = {
  London: (process.env["CHECKATRADE_LONDON_MEMBER_ID"] || "").trim(),
  Midlands: (process.env["CHECKATRADE_MIDLANDS_MEMBER_ID"] || "").trim(),
};

const MEMBER_ID_PROFILE: Record<string, "London" | "Midlands"> = Object.fromEntries(
  Object.entries(PROFILE_MEMBER_ID)
    .filter(([, memberId]) => Boolean(memberId))
    .map(([profile, memberId]) => [memberId, profile])
) as Record<string, "London" | "Midlands">;

/**
 * Hand each scraped lead off to the PowWash app, which picks a template and
 * messages the customer on WhatsApp. POSTs to POWWASH_WEBHOOK_URL (defaults to
 * the local Flask app) with an optional shared-secret header. Handoff failures
 * are reported but never block scraping.
 */
async function forwardLeadsToPowwash(leads: Lead[]): Promise<void> {
  if (!leads.length) return;
  const url =
    process.env["POWWASH_WEBHOOK_URL"] ||
    "http://127.0.0.1:5000/webhook/checkatrade";
  const token = (process.env["CHECKATRADE_WEBHOOK_TOKEN"] || "").trim();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["X-Checkatrade-Token"] = token;

  for (const lead of leads) {
    const label = lead.customerName || lead.phone || "lead";
    const payload = {
      customerName: lead.customerName,
      email: lead.email,
      phone: lead.phone,
      address: lead.address,
      jobTitle: lead.jobTitle,
      jobDescription: lead.message,
      message: lead.message,
      profile: lead.profile,
      sourceUrl: lead.sourceUrl,
      source: "checkatrade",
    };
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      const text = await resp.text().catch(() => "");
      if (resp.ok) {
        broadcast("ok", `→ PowWash received ${label} (${resp.status}).`);
      } else {
        broadcast(
          "fail",
          `PowWash rejected ${label} (${resp.status}): ${text.slice(0, 200)}`
        );
      }
    } catch (err) {
      broadcast(
        "fail",
        `PowWash handoff failed for ${label}: ${err instanceof Error ? err.message : String(err)}`
      );
    }
  }
}

// ── Proven scraping helpers (profile switching + clean detail parsing) ─────────
const CHROMIUM_PATH =
  "/nix/store/qa9cnw4v5xkxyip6mb9kxqfq1z4x2dx1-chromium-138.0.7204.100/bin/chromium";

const DETAIL_POSTCODE_RE = /\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b/i;
const DETAIL_PHONE_RE =
  /(\+44[\s\u00a0-]?\d[\s\u00a0-]?\d{4,5}[\s\u00a0-]?\d{4,6}|0\d{3,4}[\s\u00a0-]?\d{5,7}|07\d{9})/;
const DETAIL_EMAIL_RE = /[a-zA-Z][a-zA-Z0-9._%+\-]*@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,6}/;

/** Read the active "Member ID: NNN" from the page body text. */
function memberIdFromText(text: string): string {
  const m = text.match(/Member\s+ID[:\s]+(\d{5,8})/i);
  return m?.[1] ?? "";
}

/** Switch the logged-in account to a specific Member ID via the profile switcher.
 *  The "Member ID:" block top-left opens a dialog listing every profile; the label
 *  and the number live in separate spans, so we click on the bare ID number. */
async function switchProfile(p: Page, memberId: string): Promise<boolean> {
  const cur = memberIdFromText(await p.evaluate(() => document.body.innerText));
  if (cur === memberId) return true;
  broadcast("status", `Switching profile ${cur || "?"} → ${memberId}…`);
  // Land on a neutral page so no job-detail tooltip/overlay intercepts the click.
  await p.goto("https://membersapp.checkatrade.com/home", { waitUntil: "domcontentloaded", timeout: 20000 }).catch(() => {});
  await p.waitForTimeout(1500);
  await p.keyboard.press("Escape").catch(() => {});
  await p.locator(':text("Member ID:")').first().click({ timeout: 5000 }).catch(() => {});
  const dlg = p.locator('[role="dialog"]');
  await dlg.waitFor({ state: "visible", timeout: 6000 }).catch(() => {});
  await p.waitForTimeout(800);
  let opt = dlg.getByText(memberId, { exact: false }).first();
  if (!(await opt.isVisible({ timeout: 1500 }).catch(() => false))) {
    opt = p.getByText(memberId, { exact: false }).last();
  }
  await opt.click({ timeout: 5000 }).catch(() => {});
  await p.waitForTimeout(4500);
  const now = memberIdFromText(await p.evaluate(() => document.body.innerText));
  broadcast("status", `Active profile now: ${now || "?"}`);
  return now === memberId;
}

interface ParsedDetail {
  customerName: string;
  postcode: string;
  address: string;
  phone: string;
  email: string;
  jobTitle: string;
  message: string;
  timing: string;
  memberId: string;
}

/** Parse a Checkatrade job-detail page (self-contained, clean layout):
 *    Interested → [job title] → Message → [date] → [customer message] →
 *    Appointments → [timing] → … → Private note → [initials] → [name] →
 *    [City, POSTCODE] → [phone] → [email]
 *  No tel:/mailto: links exist, so contacts are matched by regex on text. */
function parseDetail(text: string): ParsedDetail {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const idxOf = (re: RegExp, from = 0) => lines.findIndex((l, i) => i >= from && re.test(l));

  let jobTitle = "";
  // The status pill differs by lead state: "Interested" (accepted), "New" /
  // "Respond now" (fresh, unclaimed), "Quoted", etc. Anchor on any of them.
  const intIdx = idxOf(/^(Interested|New|Quoted|Responded|Respond now)$/i);
  if (intIdx >= 0) {
    for (let i = intIdx + 1; i < lines.length; i++) {
      if (/^Message$/i.test(lines[i])) break;
      if (lines[i].length >= 3) { jobTitle = lines[i]; break; }
    }
  }

  let message = "";
  const SECTIONS = /^(Appointments|Quotes and invoices|Payments|Review|Private note|Quick)/i;
  const DATE_RE = /^\d{1,2} [A-Za-z]{3,} \d{2,4}/;
  const msgIdx = idxOf(/^Message$/i);
  if (msgIdx >= 0) {
    const out: string[] = [];
    for (let i = msgIdx + 1; i < lines.length; i++) {
      if (SECTIONS.test(lines[i])) break;
      if (DATE_RE.test(lines[i])) continue;
      out.push(lines[i]);
    }
    message = out.join(" ").trim();
  }

  let timing = "";
  const apptIdx = idxOf(/^Appointments$/i);
  if (apptIdx >= 0) {
    for (let i = apptIdx + 1; i < lines.length; i++) {
      if (/^(Quotes and invoices|Payments|Review)/i.test(lines[i])) break;
      if (/customer would|like the job|within|start/i.test(lines[i])) { timing = lines[i]; break; }
    }
  }

  let name = "", postcode = "", address = "", phone = "", email = "";
  const pnIdx = lines.lastIndexOf("Private note");
  const searchFrom = pnIdx >= 0 ? pnIdx + 1 : 0;
  const pcIdx = idxOf(/,\s*[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}/i, searchFrom);
  if (pcIdx >= 0) {
    address = lines[pcIdx];
    postcode = (address.match(DETAIL_POSTCODE_RE)?.[1] || "").toUpperCase();
    for (let i = pcIdx - 1; i >= searchFrom; i--) {
      if (/^[A-Z]{1,3}$/.test(lines[i])) continue; // initials avatar
      name = lines[i];
      break;
    }
    for (let i = pcIdx + 1; i < lines.length; i++) {
      const clean = lines[i].replace(/\u00a0/g, " ");
      if (!phone && DETAIL_PHONE_RE.test(clean)) phone = clean.match(DETAIL_PHONE_RE)![0].replace(/\s+/g, " ").trim();
      if (!email && DETAIL_EMAIL_RE.test(lines[i])) email = lines[i].match(DETAIL_EMAIL_RE)![0];
      if (phone && email) break;
      if (/^(Call|Chat|Keep track)/i.test(lines[i]) && i > pcIdx + 3) break;
    }
  }

  return { customerName: name, postcode, address, phone, email, jobTitle, message, timing, memberId: memberIdFromText(text) };
}

/** On the current profile's /jobs list, find and open the card matching a postcode.
 *  Returns true if it landed on a /jobs/[uuid] detail page. */
async function openCardByPostcode(p: Page, postcode: string): Promise<boolean> {
  await p.goto("https://membersapp.checkatrade.com/jobs", { waitUntil: "domcontentloaded", timeout: 20000 });
  await p.waitForTimeout(3000);
  await p.keyboard.press("Escape").catch(() => {});
  // Spacing in the list may differ from the email's postcode — match space-insensitively.
  const re = new RegExp(postcode.trim().replace(/\s+/g, "\\s*"), "i");
  // Match the WHOLE job card (aria-label="Job card"), not just "Interested" cards.
  // Brand-new leads carry a "New" pill + "Respond now" action and have no
  // "Interested" text, so the old filter silently skipped them. Clicking the
  // card itself opens the detail page WITHOUT touching the Respond/Reply button.
  let card = p.locator('button[aria-label="Job card"]').filter({ hasText: re }).first();
  if (!(await card.isVisible({ timeout: 4000 }).catch(() => false))) {
    // Fallback: any clickable element carrying the postcode (excluding action buttons).
    card = p.locator('[data-testid^="job-card-v2"], [role="button"], a[href*="/jobs/"]')
      .filter({ hasText: re })
      .filter({ hasNotText: /^(Respond now|Reply)$/i })
      .first();
    if (!(await card.isVisible({ timeout: 2000 }).catch(() => false))) return false;
  }
  await card.click().catch(() => {});
  await p.waitForTimeout(3500);
  for (const t of ["Skip", "Maybe later", "Not now", "Close", "Dismiss"]) {
    const b = p.locator("button").filter({ hasText: new RegExp(`^${t}$`, "i") }).first();
    if (await b.isVisible({ timeout: 600 }).catch(() => false)) { await b.click().catch(() => {}); await p.waitForTimeout(600); break; }
  }
  if (p.url().includes("/chats/")) {
    const jd = p.locator("a, button").filter({ hasText: /job details/i }).first();
    if (await jd.isVisible({ timeout: 3000 }).catch(() => false)) { await jd.click(); await p.waitForTimeout(2500); }
  }
  return p.url().includes("/jobs/");
}

/** Find the lead for a postcode: switch to its profile, open the card, parse details.
 *  Tries the postcode's expected profile first, then the other as a fallback. */
async function scrapeLeadByPostcode(p: Page, postcode: string): Promise<Lead | null> {
  const detected = detectProfile(postcode);
  const order: Array<"London" | "Midlands"> =
    detected === "London" ? ["London", "Midlands"] : ["Midlands", "London"];
  for (const prof of order) {
    await switchProfile(p, PROFILE_MEMBER_ID[prof]);
    const opened = await openCardByPostcode(p, postcode);
    if (!opened) {
      broadcast("status", `${prof}: no card found for ${postcode}.`);
      continue;
    }
    const d = parseDetail(await p.evaluate(() => document.body.innerText));
    if (d.customerName || d.phone || d.email) {
      return {
        customerName: d.customerName,
        email: d.email,
        phone: d.phone,
        address: d.address || `${postcode}`,
        jobTitle: d.jobTitle,
        message: d.message,
        profile: MEMBER_ID_PROFILE[d.memberId] ?? prof,
        sourceUrl: p.url(),
      };
    }
  }
  return null;
}

/** Drive the Auth0 password connection. Called on the email-code page (after
 *  the email form has been submitted). Clicks #switchConnectionButton to reach
 *  /u/login/password, fills the password, and submits.
 *  Returns true if we successfully left the Auth0 login host (logged in). */
async function tryPasswordLogin(p: Page, accountPassword: string): Promise<boolean> {
  const switchBtn = p.locator('#switchConnectionButton, button:has-text("password")').first();
  if (!(await switchBtn.isVisible({ timeout: 4000 }).catch(() => false))) return false;
  await switchBtn.click().catch(() => {});
  await p.waitForURL(/\/u\/login\/password/, { timeout: 12000 }).catch(() => {});
  const pwField = p.locator('input[name="password"], #password').first();
  if (!(await pwField.isVisible({ timeout: 6000 }).catch(() => false))) return false;
  await pwField.fill(accountPassword);
  await p.waitForTimeout(400);
  await p.locator('button[type="submit"][value="default"], button:has-text("Continue"), button[type="submit"]').first().click().catch(() => {});
  const ok = await p.waitForURL((u) => !u.toString().includes("login.trade.checkatrade.com"), { timeout: 30000 })
    .then(() => true).catch(() => false);
  if (ok) await p.waitForTimeout(3000);
  return ok;
}

/** Save the current browser session cookies to Postgres so the next run can
 *  skip authentication entirely (no email code, no password flow). */
async function saveSessionCookies(ctx: BrowserContext): Promise<void> {
  const cookies = await ctx.cookies();
  broadcast("status", `Saving session (${cookies.length} cookie(s))…`);
  if (!cookies.length) {
    broadcast("status", "Warning: cookie jar empty — session not saved.");
    return;
  }
  const json = JSON.stringify(cookies);
  await db.execute(sql`UPDATE app_settings SET session_cookies = ${json} WHERE id = 1`);
  broadcast("status", "Session saved — next login will skip authentication.");
}

/** Try to restore a previously-saved Checkatrade session. Launches a browser,
 *  injects the saved cookies, and navigates to /jobs.
 *  If still logged in, sets the module-level browser/page and returns the Page.
 *  If the session is expired or unavailable, closes the browser and returns null. */
async function trySavedSession(): Promise<Page | null> {
  let cookiesJson = "";
  try {
    const rows = await db.execute(sql`SELECT session_cookies FROM app_settings WHERE id = 1`);
    cookiesJson = ((rows.rows[0] as Record<string, unknown>)?.session_cookies as string) || "";
  } catch { return null; }
  if (!cookiesJson || cookiesJson === "[]") return null;

  let cookies: unknown[];
  try { cookies = JSON.parse(cookiesJson); } catch { return null; }
  if (!cookies.length) return null;

  if (browser) { await browser.close().catch(() => {}); browser = null; page = null; }
  const b = await chromium.launch({
    executablePath: CHROMIUM_PATH, headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote", "--no-first-run", "--disable-extensions"],
  });
  const ctx = await b.newContext({
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  });
  await ctx.addCookies(cookies as Parameters<typeof ctx.addCookies>[0]);
  const p = await ctx.newPage();
  await p.goto("https://membersapp.checkatrade.com/jobs", { waitUntil: "load", timeout: 30000 }).catch(() => {});

  if (p.url().includes("login") || p.url().includes("signin") || p.url().includes("/u/")) {
    await b.close().catch(() => {});
    return null;
  }

  browser = b;
  page = p;
  return p;
}

/** Launch a headless browser and log into Checkatrade. Prefers fast password
 *  login (Auth0 database connection); falls back to email-OTP if no account
 *  password is saved or the password path fails (e.g. 2FA).
 *  Sets the module-level `browser`/`page`. Throws on failure. */
async function launchAndLogin(loginEmail: string, loginPassword: string, accountPassword = ""): Promise<Page> {
  // 1️⃣ Saved-session fast path — no login flow, no email code ever.
  broadcast("status", "Checking saved session…");
  const restored = await trySavedSession().catch(() => null);
  if (restored) {
    broadcast("ok", "Resumed saved session — no login needed.");
    return restored;
  }

  // 2️⃣ Fresh login. Launch browser and navigate to the identifier page.
  if (browser) { await browser.close().catch(() => {}); browser = null; page = null; }
  browser = await chromium.launch({
    executablePath: CHROMIUM_PATH,
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote", "--no-first-run", "--disable-extensions"],
  });
  const ctx = await browser.newContext({
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  });
  page = await ctx.newPage();
  await page.goto("https://membersapp.checkatrade.com/login", { waitUntil: "load", timeout: 30000 });
  const cookieBtn = page.locator('button:has-text("Accept All Cookies")');
  if (await cookieBtn.isVisible({ timeout: 5000 }).catch(() => false)) { await cookieBtn.click(); await page.waitForTimeout(1200); }
  const tradeBtn = page.locator('button:has-text("Trade log in")');
  await tradeBtn.waitFor({ timeout: 10000 });
  await tradeBtn.click();
  await page.waitForURL(/login\.trade\.checkatrade\.com/, { timeout: 15000 });

  // 3️⃣ Submit email — this triggers an email code, but we'll use the password
  //    switch to bypass it (and session-save means this only happens once).
  await page.locator('input[name="username"], input[autocomplete="email"]').first().fill(loginEmail);
  const loginTime = new Date();
  await page.locator('button:has-text("Continue"), input[type="submit"][value*="Continue"]').first().click();
  await page.waitForTimeout(2500);

  // 4️⃣ Password fast path: switch from email-code page → /u/login/password.
  if (accountPassword) {
    broadcast("status", "Logging in with password…");
    const ok = await tryPasswordLogin(page, accountPassword).catch(() => false);
    if (ok) {
      broadcast("ok", "Logged in to Checkatrade (password).");
      await saveSessionCookies(page.context()).catch((e) => broadcast("status", `Cookie save warning: ${e}`));
      return page;
    }
    broadcast("status", "Password login unavailable — falling back to email code…");
  }

  // 5️⃣ OTP fallback: auto-read from inbox.
  broadcast("status", "Login code sent — auto-reading from inbox…");
  const otp = await pollForLoginOtp(loginEmail, loginPassword, loginTime, 120_000, (m) => broadcast("status", m));
  if (!otp) throw new Error("Could not auto-read the Checkatrade login code from the inbox.");
  await page.locator('input[name="code"], input[autocomplete="one-time-code"], input[placeholder*="code" i], input[id*="code" i]').first().fill(otp);
  await page.waitForTimeout(1000);
  await page.locator('button:has-text("Login"), button[type="submit"]').first().click();
  await page.waitForURL((u) => !u.toString().includes("login.trade.checkatrade.com"), { timeout: 60000 });
  await page.waitForTimeout(3000);
  broadcast("ok", "Logged in to Checkatrade.");
  await saveSessionCookies(page.context()).catch((e) => broadcast("status", `Cookie save warning: ${e}`));
  return page;
}

async function extractLeads(p: Page): Promise<Lead[]> {
  // ── Dismiss any modal/popup (e.g. "Bookable estimate") ───────────────────────
  await p.keyboard.press("Escape").catch(() => {});
  await p.waitForTimeout(400);
  const dismissSelectors = [
    '[role="dialog"] button',
    '[aria-label*="close" i]',
    '[aria-label*="dismiss" i]',
    'button:has-text("✕")',
    'button:has-text("×")',
    'button:has-text("Close")',
    'button:has-text("Skip")',
    'button:has-text("Not now")',
    'button:has-text("Maybe later")',
  ];
  for (const sel of dismissSelectors) {
    const btn = p.locator(sel).first();
    if (await btn.isVisible({ timeout: 500 }).catch(() => false)) {
      await btn.click().catch(() => {});
      await p.waitForTimeout(400);
      break;
    }
  }

  // ── Scrape newest leads from BOTH profiles (real profile switching) ──────────
  const leads: Lead[] = [];
  const PROFILES: Array<{ label: "London" | "Midlands"; take: number }> = [
    { label: "Midlands", take: 6 },
    { label: "London", take: 6 },
  ];

  for (const prof of PROFILES) {
    const switched = await switchProfile(p, PROFILE_MEMBER_ID[prof.label]);
    if (!switched) {
      broadcast("status", `Could not switch to ${prof.label} (${PROFILE_MEMBER_ID[prof.label]}) — skipping.`);
      continue;
    }

    await p.goto("https://membersapp.checkatrade.com/jobs", { waitUntil: "domcontentloaded", timeout: 20000 });
    await p.waitForTimeout(3000);
    await p.keyboard.press("Escape").catch(() => {});

    const rawText = await p.evaluate(() => document.body.innerText);
    const cards = parseJobCards(rawText).filter((c) => c.postcode);

    // De-dupe by postcode (newest first) and take the most recent N.
    const seen = new Set<string>();
    const pick = cards
      .filter((c) => {
        const k = normalisePostcode(c.postcode);
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      })
      .slice(0, prof.take);

    broadcast("status", `${prof.label}: ${cards.length} card(s) on page — scraping newest ${pick.length}.`);

    for (const card of pick) {
      const opened = await openCardByPostcode(p, card.postcode);
      if (!opened) {
        broadcast("status", `${prof.label}: couldn't open ${card.customer} (${card.postcode}).`);
        continue;
      }
      const d = parseDetail(await p.evaluate(() => document.body.innerText));
      const profile: "London" | "Midlands" | "Unknown" = MEMBER_ID_PROFILE[d.memberId] ?? prof.label;
      leads.push({
        customerName: d.customerName || card.customer,
        email: d.email,
        phone: d.phone,
        address: d.address || card.location,
        jobTitle: d.jobTitle || card.title,
        message: d.message,
        profile,
        sourceUrl: p.url(),
      });
      broadcast("status", `${prof.label}: ${d.customerName || card.customer} — phone ${d.phone || "n/a"}, email ${d.email || "n/a"}.`);
    }
  }

  broadcast("status", `Scraped ${leads.length} lead(s) across both profiles.`);
  return leads;
}

/** Normalise a postcode for comparison — strip spaces and uppercase. */
function normalisePostcode(pc: string): string {
  return pc.replace(/\s+/g, "").toUpperCase();
}

/**
 * After leads are extracted, read recent Checkatrade enquiry emails (last 7 days)
 * and broadcast each one as a dedicated "enquiry" SSE event so the UI can render it.
 */
async function matchEnquiryEmails(leads: Lead[]): Promise<void> {
  try {
    const rows = await db.select().from(appSettings).where(eq(appSettings.id, 1));
    const s = rows[0];
    if (!s?.enquiryEmail || !s?.enquiryEmailPassword) {
      broadcast("status", "No enquiry email credentials saved — skipping inbox match.");
      return;
    }

    broadcast("status", `Reading Checkatrade emails from enquiry inbox (last 7 days)…`);
    const emails = await readRecentEnquiries(
      s.enquiryEmail,
      s.enquiryEmailPassword,
      (msg) => broadcast("status", msg)
    );

    if (emails.length === 0) {
      broadcast("status", "No Checkatrade emails found in the enquiry inbox in the last 7 days.");
      return;
    }

    // Build normalised postcode → lead map
    const leadByPostcode = new Map<string, Lead>();
    for (const lead of leads) {
      const pc = extractPostcode(lead.address);
      if (pc) leadByPostcode.set(normalisePostcode(pc), lead);
    }

    let matchCount = 0;
    for (const em of emails) {
      const norm = normalisePostcode(em.postcode);
      const matched = norm ? leadByPostcode.get(norm) : undefined;

      if (matched) matchCount++;

      // Broadcast each enquiry as a structured event the UI can render
      broadcast("enquiry", {
        subject: em.subject,
        from: em.from,
        date: em.date,
        postcode: em.postcode,
        snippet: em.snippet,
        matchedLead: matched
          ? { customerName: matched.customerName, profile: matched.profile, address: matched.address }
          : null,
      });
    }

    broadcast(
      matchCount > 0 ? "ok" : "status",
      `Enquiry inbox: ${emails.length} email(s) found, ${matchCount} matched to a current lead.`
    );
  } catch (err) {
    broadcast("status", `Enquiry match error: ${err instanceof Error ? err.message : String(err)}`);
  }
}

/**
 * Complete the OTP step and extract leads.
 * Called by both the manual /magic-link route and the auto-IMAP polling path.
 */
async function completeLogin(otp: string): Promise<void> {
  if (!page) throw new Error("No active browser session — start from step 1.");

  broadcast("status", "Entering one-time code…");

  const codeInput = page
    .locator(
      'input[name="code"], input[autocomplete="one-time-code"], input[placeholder*="code" i], input[id*="code" i]'
    )
    .first();
  await codeInput.waitFor({ timeout: 10000 });
  await codeInput.fill(otp);
  await page.screenshot({ path: "/tmp/checkatrade-code-filled.png" });
  broadcast("status", "Code entered — clicking Login…");

  const loginBtn = page
    .locator('button:has-text("Login"), input[type="submit"][value*="Login"], button[type="submit"]')
    .first();
  await loginBtn.waitFor({ timeout: 5000 });
  await loginBtn.click();

  await page.waitForURL(
    (u) => !u.toString().includes("login.trade.checkatrade.com"),
    { timeout: 20000 }
  );
  await page.waitForTimeout(2000);

  const currentUrl = page.url();
  broadcast("status", `Landed on: ${currentUrl.split("?")[0]}`);

  if (currentUrl.includes("login") || currentUrl.includes("signin")) {
    await page.screenshot({ path: "/tmp/checkatrade-code-filled.png" });
    broadcast("fail", "Login failed — still on the login page. Check the code and try again.");
    return;
  }

  broadcast("ok", "Login successful!");
  await finishLoginAndExtract();
}

/**
 * Post-login work shared by every login path (password OR OTP): scrape leads,
 * forward them to PowWash, match enquiry emails, then close the browser.
 */
async function finishLoginAndExtract(): Promise<void> {
  if (!page) throw new Error("No active browser session.");

  // Save cookies immediately after login (before any scraping that might hang).
  await saveSessionCookies(page.context()).catch((e) => broadcast("status", `Cookie save warning: ${e}`));

  const leads = await extractLeads(page);
  latestLeads = leads;
  broadcast("ok", `Found ${leads.length} lead(s).`);
  broadcast("leads", leads);

  // Hand leads to the PowWash app (messages the customer)
  await forwardLeadsToPowwash(leads);

  // Match enquiry emails to the extracted leads
  await matchEnquiryEmails(leads);

  await browser?.close().catch(() => {});
  browser = null;
  page = null;
}

// ── UI ────────────────────────────────────────────────────────────────────────
/** Check whether the browser is currently logged into Checkatrade (no login needed). */
router.get("/checkatrade/session", async (_req, res) => {
  try {
    if (!page) return void res.json({ loggedIn: false });
    const url = page.url();
    const loggedIn =
      url.includes("membersapp.checkatrade.com") &&
      !url.includes("/login") &&
      !url.includes("auth0.com");
    res.json({ loggedIn, url });
  } catch {
    res.json({ loggedIn: false });
  }
});

/** Refresh leads without re-logging in (session must already be active). */
router.post("/checkatrade/fetch", async (_req, res) => {
  if (!page) return void res.status(400).json({ error: "No active browser session — please log in first." });
  res.json({ ok: true });
  void (async () => {
    try {
      broadcast("status", "Refreshing leads...");
      const leads = await extractLeads(page!);
      latestLeads = leads;
      broadcast("leads", leads);
      broadcast("ok", `Done — ${leads.length} lead(s) loaded.`);
      await forwardLeadsToPowwash(leads);
      await matchEnquiryEmails(leads);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      broadcast("fail", `Lead extraction error: ${msg}`);
    }
  })();
});

/** Monitor status — reads from DB so it survives restarts */
router.get("/checkatrade/monitor", async (_req, res) => {
  const rows = await db.select().from(appSettings).where(eq(appSettings.id, 1));
  const enabled = rows[0]?.monitorEnabled ?? true;
  res.json({ active: enabled });
});

router.post("/checkatrade/monitor/stop", async (_req, res) => {
  // Persist OFF to DB so server restarts respect it
  await db
    .insert(appSettings)
    .values({ id: 1, monitorEnabled: false })
    .onConflictDoUpdate({ target: appSettings.id, set: { monitorEnabled: false } });
  await stopMonitor();
  broadcast("monitor", { active: false, msg: "Monitor stopped." });
  res.json({ ok: true });
});

router.post("/checkatrade/monitor/start", async (_req, res) => {
  // Persist ON to DB
  await db
    .insert(appSettings)
    .values({ id: 1, monitorEnabled: true })
    .onConflictDoUpdate({ target: appSettings.id, set: { monitorEnabled: true } });
  if (!isMonitorActive()) {
    startMonitor(broadcast, async (subject, postcode) => {
      await triggerAutoFlow(postcode).catch((err) => {
        broadcast("fail", `Auto-flow error: ${err instanceof Error ? err.message : String(err)}`);
      });
    });
  }
  broadcast("monitor", { active: true, msg: "Monitor started — watching enquiry inbox." });
  res.json({ ok: true });
});

/**
 * Fully automated login + lead fetch triggered by the enquiry email monitor.
 * Uses stored credentials — no user interaction needed.
 */
export async function triggerAutoFlow(postcode?: string): Promise<void> {
  if (testScrapeRunning) {
    broadcast("status", "A scraper test is currently running — skipping this auto-flow to avoid a clash. It will pick up the next enquiry.");
    return;
  }
  autoFlowRunning = true;
  try {
    await runAutoFlow(postcode);
  } finally {
    autoFlowRunning = false;
  }
}

async function runAutoFlow(postcode?: string): Promise<void> {
  // If already logged in, just refresh leads
  if (page) {
    const url = page.url();
    if (
      url.includes("membersapp.checkatrade.com") &&
      !url.includes("/login") &&
      !url.includes("auth0.com")
    ) {
      broadcast("status", `📬 New enquiry${postcode ? ` (${postcode})` : ""} — refreshing leads…`);
      try {
        const leads = await extractLeads(page);
        latestLeads = leads;
        broadcast("leads", leads);
        broadcast("ok", `Found ${leads.length} lead(s).`);
        await forwardLeadsToPowwash(leads);
        await matchEnquiryEmails(leads);
      } catch (err) {
        broadcast("fail", `Lead refresh error: ${err instanceof Error ? err.message : String(err)}`);
      }
      return;
    }
  }

  const rows = await db.select().from(appSettings).where(eq(appSettings.id, 1));
  const s = rows[0];
  if (!s?.loginEmail || !s?.loginEmailPassword) {
    broadcast("fail", "New enquiry detected but no Checkatrade login credentials saved — go to Settings.");
    return;
  }

  broadcast("status", `📬 New enquiry${postcode ? ` (${postcode})` : ""} — auto-logging in to Checkatrade…`);
  broadcast("step2", "auto"); // signal to UI that auto-login is in progress

  autoLoginResolved = false;
  if (browser) { await browser.close().catch(() => {}); browser = null; page = null; }

  browser = await chromium.launch({
    executablePath: "/nix/store/qa9cnw4v5xkxyip6mb9kxqfq1z4x2dx1-chromium-138.0.7204.100/bin/chromium",
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote", "--no-first-run", "--disable-extensions"],
  });
  const ctx = await browser.newContext({
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  });
  page = await ctx.newPage();

  await page.goto("https://membersapp.checkatrade.com/login", { waitUntil: "load", timeout: 30000 });
  const cookieBtn = page.locator('button:has-text("Accept All Cookies")');
  if (await cookieBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    await cookieBtn.click();
    await page.waitForTimeout(1500);
  }
  const tradeLoginBtn = page.locator('button:has-text("Trade log in")');
  await tradeLoginBtn.waitFor({ timeout: 10000 });
  await tradeLoginBtn.click();
  await page.waitForURL(/login\.trade\.checkatrade\.com/, { timeout: 15000 });

  const emailInput = page.locator('input[name="username"], input[autocomplete="email"]').first();
  await emailInput.waitFor({ timeout: 10000 });
  await emailInput.fill(s.loginEmail);
  const continueBtn = page.locator('button:has-text("Continue"), input[type="submit"][value*="Continue"]').first();
  await continueBtn.waitFor({ timeout: 5000 });
  await continueBtn.click();
  await page.waitForTimeout(3000);

  broadcast("status", "Login code sent to inbox — reading automatically…");
  const loginTime = new Date();
  const otp = await pollForLoginOtp(
    s.loginEmail, s.loginEmailPassword, loginTime, 90_000,
    (msg) => { if (!autoLoginResolved) broadcast("status", msg); }
  );
  if (!otp) {
    broadcast("fail", "Could not auto-read login code. Please log in manually from the Leads tab.");
    if (browser) { await browser.close().catch(() => {}); browser = null; page = null; }
    return;
  }
  autoLoginResolved = true;
  await completeLogin(otp);
}

/**
 * Test endpoint — runs the full auto-login + lead-fetch flow and matches
 * against already-READ enquiry emails (no waiting for a new one).
 * Identical to triggerAutoFlow() but also reads previously-seen emails.
 */
router.post("/checkatrade/test", async (_req, res) => {
  res.json({ ok: true });
  void triggerAutoFlow("TEST").catch((err) => {
    broadcast("fail", `Test error: ${err instanceof Error ? err.message : String(err)}`);
  });
});

/**
 * "Test Checkatrade scraper" button — proves the end-to-end pipeline:
 * reads the last 3 enquiry-notification emails, logs into Checkatrade, and for
 * each email switches to the right profile, finds the matching job by postcode,
 * and scrapes the full customer details. Streams one "testresult" event per
 * email. Does NOT message customers — purely a verification preview.
 */
let testScrapeRunning = false;
router.post("/checkatrade/test-scrape", async (_req, res) => {
  if (testScrapeRunning) { res.status(409).json({ error: "A test is already running." }); return; }
  if (autoFlowRunning) { res.status(409).json({ error: "An auto-login/lead-fetch is currently running — try again in a moment." }); return; }

  // Stream SSE events directly in this response so the button can read results
  // without depending on a separate EventSource connection (which can fail through proxies).
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();
  sseClients.push(res);
  testScrapeRunning = true;

  try {
    const rows = await db.select().from(appSettings).where(eq(appSettings.id, 1));
    const s = rows[0];

    if (!s?.enquiryEmail || !s?.enquiryEmailPassword) {
      broadcast("testdone", {
        error:
          "Enquiry inbox isn't set up yet. Open Gmail Settings and add the Gmail address (and its app password) that receives the Checkatrade lead-notification emails.",
      });
      return;
    }
    if (!s?.loginEmail || !s?.loginEmailPassword) {
      broadcast("testdone", { error: "No Checkatrade login email saved — add it in Gmail Settings." });
      return;
    }

    broadcast("teststart", { msg: "Reading your last 3 Checkatrade enquiry emails…" });
    const emails = (await readRecentEnquiries(
      s.enquiryEmail,
      s.enquiryEmailPassword,
      (m) => broadcast("status", m),
      14
    )).slice(0, 3);

    if (emails.length === 0) {
      broadcast("testdone", { error: "No Checkatrade enquiry emails found in the last 14 days." });
      return;
    }
    broadcast("teststart", { msg: `Found ${emails.length} enquiry email(s). Logging into Checkatrade…`, total: emails.length });

    const p = await launchAndLogin(s.loginEmail, s.loginEmailPassword, s.loginAccountPassword || "");

    let matched = 0;
    for (let i = 0; i < emails.length; i++) {
      const em = emails[i];
      broadcast("status", `Email ${i + 1}/${emails.length}: ${em.subject} — postcode ${em.postcode || "not found"}`);

      let lead: Lead | null = null;
      if (em.postcode) {
        lead = await scrapeLeadByPostcode(p, em.postcode).catch((err) => {
          broadcast("status", `Scrape error for ${em.postcode}: ${err instanceof Error ? err.message : String(err)}`);
          return null;
        });
      }
      if (lead) matched++;

      broadcast("testresult", {
        index: i,
        total: emails.length,
        enquiry: { subject: em.subject, from: em.from, date: em.date, postcode: em.postcode },
        lead,
      });
    }

    broadcast("testdone", { ok: true, total: emails.length, matched });
  } catch (err) {
    broadcast("testdone", { error: err instanceof Error ? err.message : String(err) });
  } finally {
    if (browser) { await browser.close().catch(() => {}); browser = null; page = null; }
    testScrapeRunning = false;
    sseClients = sseClients.filter(c => c !== res);
    res.end();
  }
});

/** Start the IMAP IDLE monitor. Called once at server boot.
 *  Reads monitorEnabled from DB — if user turned it off, respects that. */
export async function initCheckatradeMonitor() {
  const rows = await db.select().from(appSettings).where(eq(appSettings.id, 1)).catch(() => []);
  const enabled = rows[0]?.monitorEnabled ?? true;
  if (!enabled) return; // user explicitly disabled — don't auto-start
  startMonitor(broadcast, async (subject, postcode) => {
    await triggerAutoFlow(postcode).catch((err) => {
      broadcast("fail", `Auto-flow error: ${err instanceof Error ? err.message : String(err)}`);
    });
  });
}

router.get("/checkatrade", (_req, res) => {
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Cache-Control", "no-store, no-cache, must-revalidate");
  res.setHeader("Pragma", "no-cache");
  res.send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Checkatrade Leads</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; padding: 28px 20px; }
    h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
    .subtitle { font-size: 13px; color: #636e85; margin-top: 4px; margin-bottom: 28px; }

    .panel { background: #161a24; border: 1px solid #242840; border-radius: 12px; padding: 24px; margin-bottom: 20px; }
    .panel h2 { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.6px; color: #636e85; margin-bottom: 14px; }

    .steps { display: flex; gap: 12px; }
    .step-block { flex: 1; }
    .step-block label { font-size: 12px; color: #636e85; display: block; margin-bottom: 6px; }
    input { width: 100%; background: #0f1117; border: 1px solid #242840; border-radius: 8px; color: #e2e8f0; padding: 9px 12px; font-size: 13px; outline: none; transition: border-color 0.15s; }
    input:focus { border-color: #5865f2; }
    .step-block input { margin-bottom: 0; }

    .actions { display: flex; gap: 10px; margin-top: 14px; }
    button { flex: 1; background: #5865f2; color: white; border: none; border-radius: 8px; padding: 10px; font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.15s, opacity 0.15s; }
    button:hover:not(:disabled) { background: #4752c4; }
    button:disabled { opacity: 0.4; cursor: not-allowed; }
    button.secondary { background: #242840; color: #8892a4; }
    button.secondary:hover:not(:disabled) { background: #2d3358; }

    .log { background: #0f1117; border: 1px solid #242840; border-radius: 8px; padding: 12px 14px; font-family: "SF Mono", "Fira Code", monospace; font-size: 11.5px; line-height: 1.75; min-height: 64px; max-height: 160px; overflow-y: auto; }
    .ll { color: #636e85; }
    .ll.ok { color: #48bb78; }
    .ll.err { color: #fc8181; }
    .ll.info { color: #63b3ed; }

    #leadsSection { display: none; }
    .leads-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
    .count-badge { background: #5865f2; color: white; font-size: 11px; font-weight: 700; border-radius: 20px; padding: 2px 10px; }

    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #636e85; padding: 0 12px 10px; border-bottom: 1px solid #242840; }
    td { padding: 12px; border-bottom: 1px solid #1c2030; vertical-align: top; color: #c8d0df; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #1a1f2e; }
    td.name { font-weight: 600; color: #e2e8f0; }
    td.job { color: #8892a4; }
    td.contact { color: #63b3ed; }
    .empty { text-align: center; padding: 32px; color: #636e85; font-size: 13px; }

    .settings-btn { flex: none; display: inline-flex; align-items: center; gap: 6px; background: #5865f2; color: white; border: none; border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; margin-top: 2px; transition: background 0.15s; }
    .settings-btn:hover { background: #4752c4; }

    .modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.72); z-index: 9000; display: none; align-items: center; justify-content: center; padding: 20px; }
    .modal-backdrop.open { display: flex; }
    .modal-box { background: #161a24; border: 1px solid #242840; border-radius: 16px; padding: 28px; width: 100%; max-width: 580px; max-height: 90vh; overflow-y: auto; position: relative; }
    .modal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
    .modal-head h2 { font-size: 16px; font-weight: 700; color: #e2e8f0; text-transform: none; letter-spacing: 0; margin: 0; }
    .modal-close { background: none; border: none; color: #636e85; cursor: pointer; font-size: 20px; line-height: 1; padding: 4px 6px; border-radius: 6px; flex: none; width: auto; }
    .modal-close:hover { color: #e2e8f0; background: #242840; }
    .cred-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 18px 0; }
    .cred-label { font-size: 12px; color: #636e85; display: block; margin-bottom: 6px; }
  </style>
</head>
<body>

<div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:28px">
  <div>
    <h1>Checkatrade Leads</h1>
    <p class="subtitle" style="margin-bottom:0">Log in to fetch your latest leads. Open <strong>⚙ Settings</strong> first to add your Gmail addresses &amp; app passwords.</p>
  </div>
  <button id="btnOpenSettings" class="settings-btn">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
    Gmail Settings
  </button>
</div>

<div class="panel">
  <h2>Login</h2>
  <div class="steps">
    <div class="step-block" id="step1Block">
      <label>Step 1 — Your email</label>
      <input id="email" type="email" placeholder="you@example.com" />
    </div>
    <div class="step-block" id="step2Block" style="display:none">
      <label>Step 2 — Magic link from your inbox</label>
      <input id="magicLink" type="url" placeholder="https://www.checkatrade.com/login?token=..." />
    </div>
  </div>
  <div class="actions">
    <button id="btnStart">Send magic link →</button>
    <button id="btnLink" class="secondary" style="display:none">Complete login &amp; fetch leads →</button>
    <button id="btnReset" class="secondary" style="display:none">Start over</button>
  </div>
  <div class="log" id="log" style="margin-top:14px"><div class="ll">Ready — enter your email above to begin.</div></div>
</div>

<div class="panel">
  <div class="leads-header">
    <h2 style="margin-bottom:4px">Test Checkatrade scraper</h2>
  </div>
  <p style="font-size:13px;color:#636e85;line-height:1.5;margin-top:0">
    Pulls your <strong>last 3 Checkatrade enquiry emails</strong>, logs in, finds each job by postcode
    (switching profile automatically), and shows the full customer details it would hand to the messenger.
    This is a preview only — no customers are messaged.
  </p>
  <div class="actions">
    <button id="btnTestScrape">▶ Test Checkatrade scraper</button>
  </div>
  <div id="testResults" style="margin-top:14px"></div>
</div>

<div class="panel" id="leadsSection">
  <div class="leads-header">
    <h2 style="margin-bottom:0">Your Leads <span class="count-badge" id="countBadge">0</span></h2>
  </div>
  <table id="leadsTable">
    <thead>
      <tr>
        <th>Name</th>
        <th>Job / Service</th>
        <th>Location</th>
        <th>Profile</th>
        <th>Contact</th>
        <th>Message</th>
      </tr>
    </thead>
    <tbody id="leadsBody">
      <tr><td colspan="6" class="empty">No leads loaded yet.</td></tr>
    </tbody>
  </table>
</div>

<div id="settingsPanel" class="modal-backdrop">
  <div class="modal-box">
    <div class="modal-head">
      <h2>Gmail Settings</h2>
      <button id="btnCloseSettings" class="modal-close" title="Close">✕</button>
    </div>
    <p style="font-size:13px;color:#636e85;line-height:1.5">The scraper reads your Gmail inboxes over IMAP — one to watch for Checkatrade lead emails, one to auto-read the login code. Use <a href="https://myaccount.google.com/apppasswords" target="_blank" style="color:#5865f2">Google app passwords</a> (16-char code), not your real Gmail password.</p>
    <div class="cred-grid">
      <div>
        <label class="cred-label">Checkatrade login Gmail<br><span style="color:#8892a4;font-weight:400">(receives the OTP login code)</span></label>
        <input id="sLoginEmail" type="email" placeholder="ben@example.com" autocomplete="off" />
      </div>
      <div>
        <label class="cred-label">App password for that inbox</label>
        <input id="sLoginPassword" type="password" placeholder="xxxx xxxx xxxx xxxx" autocomplete="new-password" />
      </div>
      <div>
        <label class="cred-label">Checkatrade account password<br><span style="color:#8892a4;font-weight:400">(fast login — skips the email code)</span></label>
        <input id="sAccountPassword" type="password" placeholder="Checkatrade password" autocomplete="new-password" />
      </div>
      <div>
        <label class="cred-label">Enquiry notification Gmail<br><span style="color:#8892a4;font-weight:400">(receives new-lead alert emails)</span></label>
        <input id="sEnquiryEmail" type="email" placeholder="enquiries@example.com" autocomplete="off" />
      </div>
      <div>
        <label class="cred-label">App password for that inbox</label>
        <input id="sEnquiryPassword" type="password" placeholder="xxxx xxxx xxxx xxxx" autocomplete="new-password" />
      </div>
    </div>
    <div class="actions" style="margin-top:0">
      <button id="btnSaveSettings">Save credentials</button>
      <button id="btnCloseSettings2" class="secondary">Cancel</button>
    </div>
    <div id="settingsStatus" style="margin-top:12px;font-size:13px;display:none"></div>
  </div>
</div>

<script>
  const $ = id => document.getElementById(id);
  const log = $("log");
  const btnStart = $("btnStart");
  const btnLink = $("btnLink");
  const btnReset = $("btnReset");

  function addLog(msg, cls = "ll") {
    if (log.children.length === 1 && log.children[0].classList.contains("ll") && !log.children[0].classList.contains("ok") && !log.children[0].classList.contains("err") && !log.children[0].classList.contains("info")) {
      log.innerHTML = "";
    }
    const d = document.createElement("div");
    d.className = "ll " + cls;
    d.textContent = "› " + msg;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
  }

  function renderLeads(leads) {
    const tbody = $("leadsBody");
    $("leadsSection").style.display = "block";
    $("countBadge").textContent = leads.length;
    if (!leads.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">No leads found on the page — the selectors may need tuning once we see Checkatrade\'s layout.</td></tr>';
      return;
    }
    tbody.innerHTML = leads.map(l => {
      const contact = [l.phone, l.email].filter(Boolean).join("<br>") || "—";
      return \`<tr>
      <td class="name">\${l.customerName || "—"}</td>
      <td class="job">\${l.jobTitle || "—"}</td>
      <td>\${l.address || "—"}</td>
      <td>\${l.profile || "—"}</td>
      <td class="contact">\${contact}</td>
      <td>\${l.message || "—"}</td>
    </tr>\`;
    }).join("");
  }

  // SSE
  const es = new EventSource("/api/checkatrade/events");
  es.addEventListener("status", e => addLog(JSON.parse(e.data), "info"));
  es.addEventListener("ok",     e => addLog(JSON.parse(e.data), "ok"));
  es.addEventListener("error",  e => addLog(JSON.parse(e.data), "err"));
  es.addEventListener("step2",  () => {
    $("step1Block").style.display = "none";
    $("step2Block").style.display = "block";
    btnStart.style.display = "none";
    btnLink.style.display = "block";
    btnReset.style.display = "block";
  });
  es.addEventListener("leads", e => renderLeads(JSON.parse(e.data)));

  // ── Test Checkatrade scraper ────────────────────────────────────────────────
  const btnTest = $("btnTestScrape");
  const testResults = $("testResults");
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;"}[c]));

  function renderTestResult(d) {
    const e = d.enquiry || {};
    const l = d.lead;
    const dateStr = e.date ? new Date(e.date).toLocaleString("en-GB") : "";
    const card = document.createElement("div");
    card.style.cssText = "border:1px solid #e3e8f0;border-radius:10px;padding:14px;margin-bottom:12px;background:#fafbfd";
    const matchBadge = l
      ? '<span style="background:#def7ec;color:#03543f;padding:2px 8px;border-radius:6px;font-size:12px;font-weight:600">✓ Matched &amp; scraped</span>'
      : '<span style="background:#fde8e8;color:#9b1c1c;padding:2px 8px;border-radius:6px;font-size:12px;font-weight:600">No matching job found</span>';
    let body;
    if (l) {
      body = \`<table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:10px">
        <tr><td style="color:#8892a4;padding:3px 8px 3px 0;width:90px">Name</td><td style="font-weight:600">\${esc(l.customerName) || "—"}</td></tr>
        <tr><td style="color:#8892a4;padding:3px 8px 3px 0">Address</td><td>\${esc(l.address) || "—"}</td></tr>
        <tr><td style="color:#8892a4;padding:3px 8px 3px 0">Phone</td><td>\${esc(l.phone) || "—"}</td></tr>
        <tr><td style="color:#8892a4;padding:3px 8px 3px 0">Email</td><td>\${esc(l.email) || "—"}</td></tr>
        <tr><td style="color:#8892a4;padding:3px 8px 3px 0">Job</td><td>\${esc(l.jobTitle) || "—"}</td></tr>
        <tr><td style="color:#8892a4;padding:3px 8px 3px 0">Profile</td><td>\${esc(l.profile) || "—"}</td></tr>
        <tr><td style="color:#8892a4;padding:3px 8px 3px 0;vertical-align:top">Message</td><td>\${esc(l.message) || "—"}</td></tr>
      </table>\`;
    } else {
      body = '<p style="font-size:13px;color:#9b1c1c;margin:10px 0 0">Could not find a Checkatrade job matching this email\\'s postcode on either profile.</p>';
    }
    card.innerHTML = \`
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
        <strong style="font-size:14px">Email \${(d.index ?? 0) + 1} of \${d.total ?? "?"}</strong>
        \${matchBadge}
      </div>
      <div style="font-size:12px;color:#636e85;margin-top:4px">
        \${esc(e.subject) || "(no subject)"}\${e.postcode ? " · " + esc(e.postcode) : ""}\${dateStr ? " · " + esc(dateStr) : ""}
      </div>
      \${body}\`;
    testResults.appendChild(card);
  }

  // teststart still arrives via EventSource for the login-log panel.
  // testresult + testdone are now read directly from the POST response stream (see button handler).
  es.addEventListener("teststart", e => {
    const d = JSON.parse(e.data);
    if (d.msg) addLog(d.msg, "info");
  });

  btnTest.addEventListener("click", async () => {
    btnTest.disabled = true;
    btnTest.textContent = "Running\\u2026 (this takes ~1\\u20132 min)";
    testResults.innerHTML = "";
    addLog("Starting Checkatrade scraper test\\u2026", "info");

    let r;
    try {
      r = await fetch("/api/checkatrade/test-scrape", { method: "POST" });
    } catch (fetchErr) {
      addLog("Network error \\u2014 scraper unreachable: " + (fetchErr.message || fetchErr), "err");
      btnTest.disabled = false;
      btnTest.textContent = "\\u25b6 Test Checkatrade scraper";
      return;
    }
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      addLog(d.error || "Could not start the test.", "err");
      btnTest.disabled = false;
      btnTest.textContent = "\\u25b6 Test Checkatrade scraper";
      return;
    }

    // Read SSE events directly from the streaming response body —
    // no dependency on the separate EventSource connection.
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let curEvent = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("event: ")) { curEvent = line.slice(7).trim(); }
          else if (line.startsWith("data: ")) {
            try {
              const d = JSON.parse(line.slice(6));
              if (curEvent === "testresult") {
                renderTestResult(d);
              } else if (curEvent === "testdone") {
                if (d.error) {
                  addLog(d.error, "err");
                  const w = document.createElement("div");
                  w.style.cssText = "border:1px solid #fde8e8;background:#fef6f6;color:#9b1c1c;border-radius:10px;padding:14px;font-size:13px";
                  w.textContent = d.error;
                  testResults.appendChild(w);
                } else {
                  addLog("Test complete \\u2014 " + d.matched + "/" + d.total + " email(s) matched to a scraped job.", "ok");
                }
              }
            } catch (_) {}
            curEvent = "";
          }
        }
      }
    } catch (streamErr) {
      addLog("Connection lost during test: " + (streamErr.message || streamErr), "err");
    }
    btnTest.disabled = false;
    btnTest.textContent = "\\u25b6 Test Checkatrade scraper";
  });

  btnStart.addEventListener("click", async () => {
    const email = $("email").value.trim();
    if (!email) return;
    btnStart.disabled = true;
    log.innerHTML = "";
    addLog("Starting browser session...", "info");
    const r = await fetch("/api/checkatrade/start", {
      method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({email})
    });
    const d = await r.json();
    if (!r.ok) { addLog(d.error || "Something went wrong", "err"); btnStart.disabled = false; }
  });

  btnLink.addEventListener("click", async () => {
    const url = $("magicLink").value.trim();
    if (!url) return;
    btnLink.disabled = true;
    addLog("Submitting magic link...", "info");
    const r = await fetch("/api/checkatrade/magic-link", {
      method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({url})
    });
    const d = await r.json();
    if (!r.ok) { addLog(d.error || "Something went wrong", "err"); btnLink.disabled = false; }
  });

  btnReset.addEventListener("click", () => location.reload());

  // ── Settings modal ────────────────────────────────────────────────────────
  const settingsPanel = $("settingsPanel");
  function openSettings() {
    settingsPanel.classList.add("open");
    fetch("/api/checkatrade/credentials").then(r => r.ok ? r.json() : null).then(d => {
      if (!d) return;
      $("sLoginEmail").value = d.loginEmail || "";
      $("sEnquiryEmail").value = d.enquiryEmail || "";
    }).catch(() => {});
  }
  function closeSettings() { settingsPanel.classList.remove("open"); }
  $("btnOpenSettings").addEventListener("click", openSettings);
  $("btnCloseSettings").addEventListener("click", closeSettings);
  $("btnCloseSettings2").addEventListener("click", closeSettings);
  settingsPanel.addEventListener("click", e => { if (e.target === settingsPanel) closeSettings(); });
  $("btnSaveSettings").addEventListener("click", async () => {
    const btn = $("btnSaveSettings");
    const st = $("settingsStatus");
    btn.disabled = true; btn.textContent = "Saving…";
    try {
      const r = await fetch("/api/checkatrade/credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          loginEmail:           $("sLoginEmail").value.trim(),
          loginEmailPassword:   $("sLoginPassword").value,
          loginAccountPassword: $("sAccountPassword").value,
          enquiryEmail:         $("sEnquiryEmail").value.trim(),
          enquiryEmailPassword: $("sEnquiryPassword").value,
        }),
      });
      if (r.ok) {
        st.textContent = "✓ Credentials saved!";
        st.style.color = "#48bb78"; st.style.display = "block";
        $("sLoginPassword").value = ""; $("sEnquiryPassword").value = ""; $("sAccountPassword").value = "";
        setTimeout(() => { st.style.display = "none"; closeSettings(); }, 1800);
      } else {
        st.textContent = "Error saving — try again.";
        st.style.color = "#fc8181"; st.style.display = "block";
      }
    } catch(_) {
      st.textContent = "Request failed.";
      st.style.color = "#fc8181"; st.style.display = "block";
    }
    btn.disabled = false; btn.textContent = "Save credentials";
  });
</script>
</body>
</html>`);
});

// SSE stream
router.get("/checkatrade/events", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();
  sseClients.push(res);
  req.on("close", () => { sseClients = sseClients.filter(c => c !== res); });
});

// Start — submit email
router.post("/checkatrade/start", async (req, res) => {
  const { email } = req.body as { email?: string };
  if (!email || !email.includes("@")) { res.status(400).json({ error: "Valid email required" }); return; }

  if (browser) { await browser.close().catch(() => {}); browser = null; page = null; }
  autoLoginResolved = false;

  res.json({ ok: true });

  try {
    // 1️⃣ Saved-session fast path — skips authentication entirely.
    broadcast("status", "Checking saved session…");
    const restored = await trySavedSession().catch(() => null);
    if (restored) {
      autoLoginResolved = true;
      broadcast("ok", "Resumed saved session — no login needed.");
      await finishLoginAndExtract();
      return;
    }

    // 2️⃣ Fresh login — launch browser.
    broadcast("status", "Launching headless browser...");
    browser = await chromium.launch({
      executablePath: CHROMIUM_PATH,
      headless: true,
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote", "--no-first-run", "--disable-extensions"],
    });
    const ctx = await browser.newContext({
      userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    });
    page = await ctx.newPage();

    broadcast("status", "Opening Checkatrade members login page...");
    await page.goto("https://membersapp.checkatrade.com/login", { waitUntil: "load", timeout: 30000 });
    const cookieBtn = page.locator('button:has-text("Accept All Cookies")');
    if (await cookieBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await cookieBtn.click(); await page.waitForTimeout(1500);
      broadcast("status", "Dismissed cookie banner.");
    }
    broadcast("status", "Clicking 'Trade log in' button...");
    const tradeLoginBtn = page.locator('button:has-text("Trade log in")');
    await tradeLoginBtn.waitFor({ timeout: 10000 });
    await tradeLoginBtn.click();
    await page.waitForURL(/login\.trade\.checkatrade\.com/, { timeout: 15000 });
    broadcast("status", `Arrived at login form: ${page.url().split("?")[0]}`);

    // 3️⃣ Submit email (triggers email code server-side) then immediately try
    //    to switch to the password connection — bypasses the code.
    const credRows = await db.select().from(appSettings).where(eq(appSettings.id, 1));
    const creds = credRows[0];
    const loginTime = new Date();

    const emailInput = page.locator('input[name="username"], input[autocomplete="email"]').first();
    await emailInput.waitFor({ timeout: 10000 });
    await emailInput.fill(email);
    const continueBtn = page.locator('button:has-text("Continue"), input[type="submit"][value*="Continue"]').first();
    await continueBtn.waitFor({ timeout: 5000 });
    await continueBtn.click();
    await page.waitForTimeout(2500);

    if (creds?.loginAccountPassword) {
      broadcast("status", "Logging in with password…");
      const ok = await tryPasswordLogin(page!, creds.loginAccountPassword).catch(() => false);
      if (ok) {
        autoLoginResolved = true;
        broadcast("ok", "Logged in to Checkatrade (password).");
        await finishLoginAndExtract();
        return;
      }
      broadcast("status", "Password login unavailable — falling back to email code…");
    }

    // 4️⃣ OTP fallback.
    broadcast("ok", `Login code sent to: ${email}`);
    broadcast("step2", "ready");
    void (async () => {
      try {
        const s = creds;
        if (!s?.loginEmail || !s?.loginEmailPassword) {
          broadcast("status", "No login email credentials in Settings — enter the code manually above.");
          return;
        }
        const otp = await pollForLoginOtp(s.loginEmail, s.loginEmailPassword, loginTime, 90_000,
          (msg) => { if (!autoLoginResolved) broadcast("status", msg); });
        if (autoLoginResolved) return;
        if (!otp) { broadcast("status", "Could not auto-read login code — please paste it manually above."); return; }
        autoLoginResolved = true;
        broadcast("ok", "Login code auto-read from inbox! Completing login…");
        await completeLogin(otp);
      } catch (err: unknown) {
        if (!autoLoginResolved) broadcast("status", `Auto-login error: ${err instanceof Error ? err.message : String(err)}`);
      }
    })();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    broadcast("fail", `Browser error: ${msg}`);
    if (browser) await browser.close().catch(() => {});
    browser = null; page = null;
  }
});

// Complete login manually with the OTP the user pastes in
router.post("/checkatrade/magic-link", async (req, res) => {
  const { url, code } = req.body as { url?: string; code?: string };
  const otp = code?.trim() || url?.trim();
  if (!otp) { res.status(400).json({ error: "One-time code is required" }); return; }
  if (!browser || !page) { res.status(400).json({ error: "No active session — start from step 1" }); return; }
  if (autoLoginResolved) {
    res.json({ ok: true, note: "Login already completed automatically." });
    return;
  }

  autoLoginResolved = true;
  res.json({ ok: true });

  try {
    await completeLogin(otp);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    broadcast("fail", `Error: ${msg}`);
  }
});

// GET /api/checkatrade/credentials — return saved emails (passwords never sent back)
router.get("/checkatrade/credentials", async (_req, res) => {
  try {
    const rows = await db.select().from(appSettings).where(eq(appSettings.id, 1));
    const s = rows[0];
    res.json({
      loginEmail:    s?.loginEmail    || "",
      enquiryEmail:  s?.enquiryEmail  || "",
      hasLoginPassword:    !!(s?.loginEmailPassword),
      hasAccountPassword:  !!(s?.loginAccountPassword),
      hasEnquiryPassword:  !!(s?.enquiryEmailPassword),
    });
  } catch (err) {
    res.status(500).json({ error: "Failed to read settings" });
  }
});

// POST /api/checkatrade/credentials — save Gmail addresses + app passwords
router.post("/checkatrade/credentials", async (req, res) => {
  const { loginEmail, loginEmailPassword, loginAccountPassword, enquiryEmail, enquiryEmailPassword } =
    req.body as { loginEmail?: string; loginEmailPassword?: string; loginAccountPassword?: string; enquiryEmail?: string; enquiryEmailPassword?: string };
  try {
    const existing = await db.select().from(appSettings).where(eq(appSettings.id, 1));
    const current = existing[0];
    await db
      .insert(appSettings)
      .values({
        id: 1,
        loginEmail:          loginEmail?.trim()          ?? current?.loginEmail          ?? "",
        loginEmailPassword:  loginEmailPassword           ?? current?.loginEmailPassword  ?? "",
        loginAccountPassword:loginAccountPassword          ?? current?.loginAccountPassword?? "",
        enquiryEmail:        enquiryEmail?.trim()         ?? current?.enquiryEmail        ?? "",
        enquiryEmailPassword:enquiryEmailPassword          ?? current?.enquiryEmailPassword?? "",
        monitorEnabled:      current?.monitorEnabled ?? true,
      })
      .onConflictDoUpdate({
        target: appSettings.id,
        set: {
          ...(loginEmail            !== undefined && { loginEmail:           loginEmail.trim() }),
          ...(loginEmailPassword    !== undefined && loginEmailPassword !== "" && { loginEmailPassword }),
          ...(loginAccountPassword  !== undefined && loginAccountPassword !== "" && { loginAccountPassword }),
          ...(enquiryEmail          !== undefined && { enquiryEmail:         enquiryEmail.trim() }),
          ...(enquiryEmailPassword  !== undefined && enquiryEmailPassword !== "" && { enquiryEmailPassword }),
          updatedAt: new Date(),
        },
      });
    res.json({ ok: true });
  } catch (err) {
    res.status(500).json({ error: "Failed to save settings" });
  }
});

// POST /api/checkatrade/test-credentials — try connecting to one or both IMAP inboxes
// Body may supply credentials to test directly (pre-save); falls back to DB values for empty fields.
// Pass which: "login" | "enquiry" | "both" (default "both").
router.post("/checkatrade/test-credentials", async (req, res) => {
  const body = req.body as {
    which?: "login" | "enquiry" | "both";
    loginEmail?: string;
    loginEmailPassword?: string;
    enquiryEmail?: string;
    enquiryEmailPassword?: string;
  };
  const rows = await db.select().from(appSettings).where(eq(appSettings.id, 1));
  const s = rows[0];

  async function testImap(email: string, password: string): Promise<{ ok: boolean; error?: string }> {
    if (!email || !password) return { ok: false, error: "No credentials saved" };
    const { ImapFlow } = await import("imapflow");
    const client = new ImapFlow({
      host: "imap.gmail.com",
      port: 993,
      secure: true,
      auth: { user: email, pass: password },
      logger: false,
    });
    // Absorb stray error events emitted after connect() resolves/rejects to
    // prevent Node.js crashing on unhandled-error (e.g. socket timeout).
    client.on("error", () => {});
    try {
      await client.connect();
      await client.logout();
      return { ok: true };
    } catch (err: any) {
      try { client.close(); } catch (_) {}
      return { ok: false, error: err?.message ?? String(err) };
    }
  }

  const which = body.which ?? "both";
  const loginEmail    = body.loginEmail?.trim()    || s?.loginEmail    || "";
  const loginPass     = body.loginEmailPassword    || s?.loginEmailPassword  || "";
  const enquiryEmail  = body.enquiryEmail?.trim()  || s?.enquiryEmail  || "";
  const enquiryPass   = body.enquiryEmailPassword  || s?.enquiryEmailPassword || "";

  if (which === "login") {
    res.json({ login: await testImap(loginEmail, loginPass) });
  } else if (which === "enquiry") {
    res.json({ enquiry: await testImap(enquiryEmail, enquiryPass) });
  } else {
    const [login, enquiry] = await Promise.all([
      testImap(loginEmail, loginPass),
      testImap(enquiryEmail, enquiryPass),
    ]);
    res.json({ login, enquiry });
  }
});

export default router;
