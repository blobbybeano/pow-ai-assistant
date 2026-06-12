import { Router } from "express";
import { db, appSettings } from "@workspace/db";
import { eq } from "drizzle-orm";
import { ImapFlow } from "imapflow";

const router = Router();

// GET /api/settings — return current settings (passwords masked)
router.get("/settings", async (req, res) => {
  try {
    const rows = await db.select().from(appSettings).where(eq(appSettings.id, 1));
    if (rows.length === 0) {
      return res.json({
        loginEmail: "",
        loginEmailPassword: "",
        loginAccountPassword: "",
        enquiryEmail: "",
        enquiryEmailPassword: "",
      });
    }
    const row = rows[0];
    return res.json({
      loginEmail: row.loginEmail,
      loginEmailPassword: row.loginEmailPassword ? "••••••••" : "",
      loginAccountPassword: row.loginAccountPassword ? "••••••••" : "",
      enquiryEmail: row.enquiryEmail,
      enquiryEmailPassword: row.enquiryEmailPassword ? "••••••••" : "",
    });
  } catch (err) {
    req.log.error(err, "Failed to load settings");
    return res.status(500).json({ error: "Failed to load settings" });
  }
});

// POST /api/settings — upsert settings (blank password = keep existing)
router.post("/settings", async (req, res) => {
  try {
    const { loginEmail, loginEmailPassword, loginAccountPassword, enquiryEmail, enquiryEmailPassword } = req.body as {
      loginEmail?: string;
      loginEmailPassword?: string;
      loginAccountPassword?: string;
      enquiryEmail?: string;
      enquiryEmailPassword?: string;
    };

    // Fetch existing so we can preserve passwords when the placeholder "••••••••" is sent
    const existing = (await db.select().from(appSettings).where(eq(appSettings.id, 1)))[0];

    const resolvePassword = (incoming: string | undefined, stored: string | undefined) => {
      if (!incoming || incoming === "••••••••") return stored ?? "";
      return incoming;
    };

    const values = {
      id: 1 as const,
      loginEmail: loginEmail?.trim() ?? existing?.loginEmail ?? "",
      loginEmailPassword: resolvePassword(loginEmailPassword, existing?.loginEmailPassword),
      loginAccountPassword: resolvePassword(loginAccountPassword, existing?.loginAccountPassword),
      enquiryEmail: enquiryEmail?.trim() ?? existing?.enquiryEmail ?? "",
      enquiryEmailPassword: resolvePassword(enquiryEmailPassword, existing?.enquiryEmailPassword),
      updatedAt: new Date(),
    };

    await db
      .insert(appSettings)
      .values(values)
      .onConflictDoUpdate({ target: appSettings.id, set: values });

    return res.json({ ok: true });
  } catch (err) {
    req.log.error(err, "Failed to save settings");
    return res.status(500).json({ error: "Failed to save settings" });
  }
});

// GET /api/settings/login-email — return just the login email (used to pre-fill the login form)
router.get("/settings/login-email", async (req, res) => {
  try {
    const rows = await db.select({ loginEmail: appSettings.loginEmail }).from(appSettings).where(eq(appSettings.id, 1));
    return res.json({ loginEmail: rows[0]?.loginEmail ?? "" });
  } catch {
    return res.json({ loginEmail: "" });
  }
});

// POST /api/settings/test — attempt an IMAP connection
// body: { email: string, password: string }
// Credentials are passed directly from the form — no need to save first.
router.post("/settings/test", async (req, res) => {
  const { email, password } = req.body as { email?: string; password?: string };

  if (!email?.trim()) return res.json({ ok: false, message: "No email address entered — fill in the email field above." });
  if (!password?.trim() || password === "••••••••") return res.json({ ok: false, message: "No app password entered — fill in the app password field above." });

  // Detect IMAP host — Google Workspace custom domains still use imap.gmail.com
  const host = "imap.gmail.com";

  const client = new ImapFlow({
    host,
    port: 993,
    secure: true,
    auth: { user: email, pass: password },
    logger: false,
  });

  try {
    await client.connect();
    const status = await client.status("INBOX", { messages: true });
    await client.logout();
    return res.json({
      ok: true,
      message: `Connected successfully — INBOX has ${status.messages ?? "?"} messages.`,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    // Provide friendlier messages for the most common failures
    if (/AUTHENTICATIONFAILED|Invalid credentials/i.test(msg)) {
      return res.json({ ok: false, message: "Authentication failed — check the email address and app password." });
    }
    if (/ECONNREFUSED|ENOTFOUND|timeout/i.test(msg)) {
      return res.json({ ok: false, message: "Could not reach the mail server — check your network or host settings." });
    }
    return res.json({ ok: false, message: msg });
  }
});

export default router;
