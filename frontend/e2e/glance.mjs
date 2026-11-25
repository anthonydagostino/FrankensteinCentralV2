// Integration check for the glance view against a running dashboard (mock mode is fine).
// Usage: BASE_URL=http://127.0.0.1:8766 PASSWORD=anything [SHOT=/path/glance.png] node e2e/glance.mjs
// Asserts: the view fits one screen at two monitor sizes with no page scroll, every section is present,
// and the toggle round-trips between the full dashboard and the glance view, surviving a reload.
import { createRequire } from "node:module";

// Resolve Playwright from the project first, then from NODE_PATH style global installs, so a machine with a global copy works too.
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const base = process.env.BASE_URL ?? "http://127.0.0.1:8000";
const password = process.env.PASSWORD ?? "anything";
const sizes = [
  [1920, 1080],
  [1366, 768],
];
const failures = [];
const check = (ok, msg) => (ok ? console.log("ok   " + msg) : (failures.push(msg), console.log("FAIL " + msg)));

const browser = await chromium.launch();
for (const [width, height] of sizes) {
  const ctx = await browser.newContext({ viewport: { width, height } });
  const login = await ctx.request.post(base + "/api/auth/login", { data: { password } });
  check(login.ok(), `login at ${width}x${height}`);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + "/glance", { waitUntil: "networkidle" });
  await page.locator("section[aria-label='Calendar']").waitFor({ timeout: 15000 });
  // every module answers in mock mode, so wait until no panel is still showing its empty state
  await page
    .waitForFunction(() => !/No (calendar|weather|finance|train|training|benefits) data/.test(document.body.innerText), null, { timeout: 15000 })
    .catch(() => {});
  await page.waitForTimeout(500);
  const empties = await page.evaluate(() => (document.body.innerText.match(/No \w+ data/g) ?? []).join(", "));
  check(empties === "", `every panel has data at ${width}x${height}${empties ? ` (still empty: ${empties})` : ""}`);
  const metrics = await page.evaluate(() => ({
    scroll: document.documentElement.scrollHeight,
    inner: window.innerHeight,
    wide: document.documentElement.scrollWidth,
    innerW: window.innerWidth,
  }));
  check(metrics.scroll <= metrics.inner, `no vertical scroll at ${width}x${height} (page ${metrics.scroll}px, window ${metrics.inner}px)`);
  check(metrics.wide <= metrics.innerW, `no horizontal scroll at ${width}x${height}`);
  for (const name of ["Attention", "Calendar", "Weather", "Money", "Trains", "Lock-In", "Amex benefits", "Home"]) {
    check((await page.locator(`[aria-label='${name}']`).count()) === 1, `section ${name} present at ${width}x${height}`);
  }
  check(errors.length === 0, `no page errors at ${width}x${height}: ${errors.join("; ")}`);
  if (width === 1920) {
    // toggle round trip: full -> glance sticks across a reload, glance -> full clears it
    await page.goto(base + "/", { waitUntil: "networkidle" });
    await page.getByLabel("Glance view").click();
    await page.waitForURL("**/glance");
    await page.reload({ waitUntil: "networkidle" });
    await page.goto(base + "/", { waitUntil: "networkidle" });
    check(page.url().endsWith("/glance"), "the saved choice brings / back to /glance after a reload");
    await page.getByTitle("Switch to the full dashboard").click();
    await page.waitForURL(/\/$/);
    await page.reload({ waitUntil: "networkidle" });
    check(!page.url().endsWith("/glance"), "switching back keeps / on the full dashboard");
    if (process.env.SHOT) await page.screenshot({ path: process.env.SHOT });
  }
  await ctx.close();
}
// the kiosk route, opened with the token, shows the same one-screen view and still fits
if (process.env.KIOSK_TOKEN) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await ctx.newPage();
  await page.goto(`${base}/kiosk?token=${process.env.KIOSK_TOKEN}`, { waitUntil: "networkidle" });
  check(page.url().endsWith("/kiosk"), "the kiosk token drops out of the URL");
  await page.locator("section[aria-label='Trains']").waitFor({ timeout: 15000 });
  await page.waitForTimeout(500);
  const m = await page.evaluate(() => ({ scroll: document.documentElement.scrollHeight, inner: window.innerHeight }));
  check(m.scroll <= m.inner, `kiosk route has no vertical scroll (page ${m.scroll}px, window ${m.inner}px)`);
  for (const name of ["Calendar", "Trains", "Money"]) check((await page.locator(`[aria-label='${name}']`).count()) === 1, `kiosk route shows ${name}`);
  await ctx.close();
}
await browser.close();
if (failures.length) {
  console.error(`${failures.length} check(s) failed`);
  process.exit(1);
}
console.log("glance integration: all checks passed");
