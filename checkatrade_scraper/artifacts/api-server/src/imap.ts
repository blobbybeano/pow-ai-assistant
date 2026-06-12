import { ImapFlow } from "imapflow";

function makeClient(email: string, password: string) {
  return new ImapFlow({
    host: "imap.gmail.com",
    port: 993,
    secure: true,
    auth: { user: email, pass: password },
    logger: false,
  });
}

/** Decode a raw RFC-2822 message source → all readable text.
 *  Handles base64 and quoted-printable encoded body parts. */
function extractAllText(raw: string): string {
  const parts: string[] = [raw];

  // Decode every base64-encoded MIME part
  for (const m of raw.matchAll(
    /Content-Transfer-Encoding:\s*base64[\r\n]+(?:[^\r\n:]+:[ \t][^\r\n]+[\r\n]+)*[\r\n]+((?:[A-Za-z0-9+/=]+[ \t]*[\r\n]*)+)/gi
  )) {
    try {
      parts.push(Buffer.from(m[1].replace(/\s/g, ""), "base64").toString("utf-8"));
    } catch {
      // skip corrupt parts
    }
  }

  // Decode quoted-printable (digits are ASCII, so this mainly matters for context)
  for (const m of raw.matchAll(
    /Content-Transfer-Encoding:\s*quoted-printable[\r\n][\s\S]+?(?=\n--)/gi
  )) {
    parts.push(
      m[0]
        .replace(/=([0-9A-F]{2})/gi, (_, h) => String.fromCharCode(parseInt(h, 16)))
        .replace(/=\r?\n/g, "")
    );
  }

  return parts.join("\n");
}

/** Extract a 6-digit OTP from decoded email text. */
function extractOtp(text: string): string | null {
  const m = text.match(/\b(\d{6})\b/);
  return m?.[1] ?? null;
}

/** Extract a UK postcode from text.
 *  Requires a real outward+inward split with whitespace between the two halves,
 *  e.g. "M9 4QP" or "SW1A 1AA". The mandatory space prevents false positives like
 *  hex colours ("F8F9FF"), tracking codes ("TO80PC") and other ID gibberish that
 *  the old space-optional pattern wrongly matched as postcodes. */
export function extractPostcode(text: string): string {
  const m = text.match(/\b([A-Z]{1,2}\d[A-Z\d]?)\s+(\d[A-Z]{2})\b/i);
  return m ? `${m[1].toUpperCase()} ${m[2].toUpperCase()}` : "";
}

export interface EnquiryEmail {
  seq: number;
  subject: string;
  from: string;
  date: Date;
  postcode: string;
  snippet: string;
}

/**
 * Poll the INBOX for a recent Checkatrade OTP email.
 * Returns the 6-digit code, or null if not found within timeoutMs.
 */
export async function pollForLoginOtp(
  email: string,
  password: string,
  afterDate: Date,
  timeoutMs = 90_000,
  onStatus?: (msg: string) => void
): Promise<string | null> {
  const deadline = Date.now() + timeoutMs;
  const intervalMs = 5_000;

  onStatus?.("Watching inbox for Checkatrade login code…");

  while (Date.now() < deadline) {
    let found: string | null = null;
    try {
      const client = makeClient(email, password);
      await client.connect();
      const lock = await client.getMailboxLock("INBOX");
      try {
        // IMAP SINCE is date-only — use start of today to catch emails in early UTC hours
        const since = new Date(afterDate);
        since.setHours(0, 0, 0, 0);

        const seqs: number[] = await client.search({ since, from: "checkatrade" });
        onStatus?.(`Inbox: ${seqs.length} Checkatrade email(s) found today.`);

        for (const seq of [...seqs].reverse()) {
          const msg = await client.fetchOne(String(seq), { source: true, envelope: true });
          if (!msg?.source) continue;

          // Skip emails that clearly predate the login attempt
          const msgDate: Date | undefined = msg.envelope?.date;
          if (msgDate && msgDate.getTime() < afterDate.getTime() - 120_000) continue;

          const fullText = extractAllText(msg.source.toString("utf-8"));
          const otp = extractOtp(fullText);
          if (otp) {
            onStatus?.("Login code found in inbox.");
            found = otp;
            break;
          }
        }
      } finally {
        lock.release();
        await client.logout();
      }
    } catch (err) {
      onStatus?.(`IMAP poll: ${err instanceof Error ? err.message : String(err)}`);
    }

    if (found) return found;

    const remaining = deadline - Date.now();
    if (remaining < intervalMs) break;
    onStatus?.(`Still waiting for code… (${Math.round(remaining / 1000)}s left — or paste it manually above)`);
    await new Promise((r) => setTimeout(r, intervalMs));
  }

  return null;
}

/**
 * Read the most recent Checkatrade enquiry emails from the last 7 days
 * (read or unread). Returns them newest-first with postcodes extracted.
 */
export async function readRecentEnquiries(
  email: string,
  password: string,
  onStatus?: (msg: string) => void,
  daysBack = 7
): Promise<EnquiryEmail[]> {
  const client = makeClient(email, password);
  await client.connect();
  const lock = await client.getMailboxLock("INBOX");
  const results: EnquiryEmail[] = [];

  try {
    const since = new Date();
    since.setDate(since.getDate() - daysBack);
    since.setHours(0, 0, 0, 0);

    // All Checkatrade emails in the last N days (read or unread)
    const seqs: number[] = await client.search({ since, from: "checkatrade" });
    onStatus?.(`Enquiry inbox: ${seqs.length} Checkatrade email(s) in last ${daysBack} days.`);

    for (const seq of [...seqs].reverse()) { // newest first
      try {
        const msg = await client.fetchOne(String(seq), { source: true, envelope: true });
        if (!msg?.source) continue;

        const fullText = extractAllText(msg.source.toString("utf-8"));
        const postcode = extractPostcode(fullText);

        results.push({
          seq,
          subject: msg.envelope?.subject ?? "(no subject)",
          from: msg.envelope?.from?.[0]?.address ?? "",
          date: msg.envelope?.date ?? new Date(),
          postcode,
          snippet: fullText.slice(0, 800),
        });
      } catch {
        // skip unreadable messages
      }
    }
  } finally {
    lock.release();
    await client.logout();
  }

  return results;
}

/** @deprecated Use readRecentEnquiries instead */
export async function readTodayEnquiries(
  email: string,
  password: string,
  onStatus?: (msg: string) => void
): Promise<EnquiryEmail[]> {
  return readRecentEnquiries(email, password, onStatus, 1);
}
