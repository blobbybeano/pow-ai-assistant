/**
 * IMAP IDLE monitor for the enquiry inbox.
 */

import { ImapFlow } from "imapflow";
import { db, appSettings } from "@workspace/db";
import { eq } from "drizzle-orm";
import { extractPostcode } from "./imap";

type BroadcastFn = (event: string, data: unknown) => void;
type EnquiryCb = (subject: string, postcode: string, body: string) => Promise<void> | void;

let monitorRunning = false;
let activeClient: ImapFlow | null = null;
let broadcastFn: BroadcastFn = () => {};
let enquiryCb: EnquiryCb = async () => {};

// AbortController lets stopMonitor() immediately cancel any in-progress sleep
let sleepAbort: AbortController | null = null;

export function isMonitorActive() {
  return monitorRunning;
}

function extractAllText(raw: string): string {
  const parts: string[] = [raw];
  for (const m of raw.matchAll(
    /Content-Transfer-Encoding:\s*base64[\r\n]+(?:[^\r\n:]+:[^\r\n]+[\r\n]+)*[\r\n]+((?:[A-Za-z0-9+/=]+[ \t]*[\r\n]*)+)/gi
  )) {
    try { parts.push(Buffer.from(m[1].replace(/\s/g, ""), "base64").toString("utf-8")); } catch { /* skip */ }
  }
  return parts.join("\n");
}

/** Interruptible sleep — cancelled immediately when stopMonitor() is called. */
async function sleep(ms: number) {
  const ctrl = new AbortController();
  sleepAbort = ctrl;
  return new Promise<void>((resolve) => {
    const t = setTimeout(resolve, ms);
    ctrl.signal.addEventListener("abort", () => {
      clearTimeout(t);
      resolve(); // resolve (not reject) so the loop can check monitorRunning cleanly
    }, { once: true });
  }).finally(() => {
    if (sleepAbort === ctrl) sleepAbort = null;
  });
}

async function isEnabledInDb(): Promise<boolean> {
  try {
    const rows = await db.select().from(appSettings).where(eq(appSettings.id, 1));
    return rows[0]?.monitorEnabled ?? true;
  } catch {
    return false;
  }
}

async function runIdleLoop() {
  while (monitorRunning) {
    // Re-check DB every iteration — if user toggled OFF it stops here
    if (!await isEnabledInDb()) {
      monitorRunning = false;
      broadcastFn("monitor", { active: false, msg: "Monitor disabled." });
      break;
    }

    let client: ImapFlow | null = null;
    try {
      const rows = await db.select().from(appSettings).where(eq(appSettings.id, 1));
      const s = rows[0];

      if (!s?.enquiryEmail || !s?.enquiryEmailPassword) {
        broadcastFn("monitor", { active: false, msg: "No enquiry email configured in Settings." });
        await sleep(30_000);
        continue;
      }

      client = new ImapFlow({
        host: "imap.gmail.com",
        port: 993,
        secure: true,
        auth: { user: s.enquiryEmail, pass: s.enquiryEmailPassword },
        logger: false,
      });

      activeClient = client;
      await client.connect();
      await client.mailboxOpen("INBOX");

      broadcastFn("monitor", { active: true, msg: `Watching ${s.enquiryEmail} for new enquiries…` });

      const processedUids = new Set<number>();
      const existing: number[] = await client.search(
        { unseen: true, from: "checkatrade" },
        { uid: true }
      );
      existing.forEach((u) => processedUids.add(u));

      client.on("exists", async () => {
        try {
          const uids: number[] = await client.search(
            { unseen: true, from: "checkatrade" },
            { uid: true }
          );
          for (const uid of uids) {
            if (processedUids.has(uid)) continue;
            processedUids.add(uid);

            const msg = await client.fetchOne(String(uid), { source: true, envelope: true }, { uid: true });
            if (!msg?.source) continue;

            const subject = msg.envelope?.subject ?? "(no subject)";
            const body = extractAllText(msg.source.toString("utf-8"));
            const postcode = extractPostcode(body);

            broadcastFn("status", `📬 New Checkatrade enquiry: "${subject}"${postcode ? ` — ${postcode}` : ""}`);
            broadcastFn("new-enquiry", { subject, postcode });

            await enquiryCb(subject, postcode, body);
          }
        } catch (err) {
          broadcastFn("status", `Monitor handler error: ${err instanceof Error ? err.message : String(err)}`);
        }
      });

      // IDLE blocks until server timeout (~29 min) or we call logout
      await client.idle();

      activeClient = null;
      if (monitorRunning) await sleep(1_000);
    } catch (err) {
      activeClient = null;
      const msg = err instanceof Error ? err.message : String(err);
      broadcastFn("monitor", { active: false, msg: `Monitor disconnected: ${msg}` });
      if (monitorRunning) await sleep(15_000);
    } finally {
      if (client && client !== activeClient) {
        try { await client.logout(); } catch { /* ignore */ }
      }
    }
  }
}

export function startMonitor(broadcast: BroadcastFn, onNewEnquiry: EnquiryCb) {
  if (monitorRunning) return;
  broadcastFn = broadcast;
  enquiryCb = onNewEnquiry;
  monitorRunning = true;
  void runIdleLoop();
}

export async function stopMonitor() {
  monitorRunning = false;

  // Immediately cancel any pending reconnect sleep so we don't wait 15s
  if (sleepAbort) {
    sleepAbort.abort();
    sleepAbort = null;
  }

  // Kill the active IMAP connection
  const client = activeClient;
  activeClient = null;
  if (client) {
    client.on("error", () => {});
    try { await client.logout(); } catch { /* ignore */ }
  }
}

export function updateMonitorCallbacks(broadcast: BroadcastFn, onNewEnquiry: EnquiryCb) {
  broadcastFn = broadcast;
  enquiryCb = onNewEnquiry;
}
