import { chromium } from "playwright";
import * as readline from "readline";

function ask(question: string): Promise<string> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => rl.question(question, (ans) => { rl.close(); resolve(ans.trim()); }));
}

async function main() {
  const email = await ask("Enter your Checkatrade email address: ");
  if (!email || !email.includes("@")) {
    console.error("That doesn't look like a valid email. Exiting.");
    process.exit(1);
  }

  console.log("\nLaunching browser...");
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  // Go to Checkatrade login
  await page.goto("https://www.checkatrade.com/login", { waitUntil: "domcontentloaded" });
  console.log("Opened Checkatrade login page.");

  // Enter email
  const emailInput = page.locator('input[type="email"]').first();
  await emailInput.waitFor({ timeout: 10000 });
  await emailInput.fill(email);
  await page.keyboard.press("Enter");
  console.log(`Submitted email: ${email}`);
  console.log("Check your inbox for the magic link / code from Checkatrade.");

  // Wait for user to paste the magic link URL
  const magicLink = await ask("Paste the full magic link URL from your email: ");

  if (!magicLink.startsWith("http")) {
    console.error("That doesn't look like a URL. Exiting.");
    await browser.close();
    process.exit(1);
  }

  await page.goto(magicLink, { waitUntil: "domcontentloaded" });
  console.log("Navigated to magic link...");
  await page.waitForTimeout(3000);

  const url = page.url();
  const title = await page.title();
  console.log(`\nCurrent URL : ${url}`);
  console.log(`Page title  : ${title}`);

  if (url.includes("dashboard") || url.includes("trades") || url.includes("leads") || url.includes("member")) {
    console.log("\n✓ Login successful!");
  } else {
    console.log("\n? Could not confirm login — check the browser window.");
  }

  await ask("Press Enter to close the browser...");
  await browser.close();
}

main().catch(console.error);
