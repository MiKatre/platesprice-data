#!/usr/bin/env node
import { closeSync, constants, fstatSync, openSync, readFileSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import puppeteer from "puppeteer-core";

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const HELP = `Usage: kitesurf [script.js|-]
Run an async JavaScript body from a file or stdin with Puppeteer page, context,
and browser variables. Return a JSON-serializable result. Each call uses a fresh
Cloudflare Kitesurf session, closed on completion/failure/Stop. No local browser.
Credentials: ~/.config/kitesurf/credentials.json (0600), with string keys
KITESURF_ACCOUNT_ID and KITESURF_API_TOKEN (Browser Run - Edit).
Optional environment variables override the file. Settings are read on every call.
Async/browser-work budget: 120 seconds; connection/actions: 30 seconds.
Save outputs in files/. Synchronous local JS can block deadlines; not a sandbox.
Example:
  kitesurf <<'JS'
  await page.goto('https://example.com', { waitUntil: 'domcontentloaded' });
  return { url: page.url(), text: await page.$eval('body', body => body.innerText) };
  JS
`;

const CREDENTIAL_KEYS = ["KITESURF_ACCOUNT_ID", "KITESURF_API_TOKEN"];
let errorEnv = process.env;

export function loadBrowserEnvironment(env = process.env, file = join(homedir(), ".config", "kitesurf", "credentials.json")) {
  if (CREDENTIAL_KEYS.every(key => env[key] !== undefined)) return env;
  let fd;
  let content;
  try {
    fd = openSync(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    const stat = fstatSync(fd);
    if (!stat.isFile() || stat.nlink !== 1 || stat.size > 16_384 || (stat.mode & 0o077)
      || (process.getuid && stat.uid !== process.getuid())) throw new Error("Unsafe settings file.");
    content = readFileSync(fd, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return env;
    throw new Error("Private Kitesurf settings must be a readable regular file owned by you, with permission 0600.");
  } finally {
    if (fd !== undefined) closeSync(fd);
  }
  let settings;
  try { settings = JSON.parse(content); } catch {
    throw new Error("Invalid JSON in private Kitesurf settings; expected KITESURF_ACCOUNT_ID and KITESURF_API_TOKEN.");
  }
  if (!settings || Array.isArray(settings) || typeof settings !== "object"
    || Object.keys(settings).some(key => !CREDENTIAL_KEYS.includes(key))
    || CREDENTIAL_KEYS.some(key => typeof settings[key] !== "string")) {
    throw new Error("Private Kitesurf settings must contain only string KITESURF_ACCOUNT_ID and KITESURF_API_TOKEN values.");
  }
  return { ...env, ...Object.fromEntries(CREDENTIAL_KEYS.map(key => [key, env[key] ?? settings[key]])) };
}

async function closeBrowser(browser, timeoutMs) {
  if (!browser) return;
  let timer;
  try {
    await Promise.race([
      browser.close(),
      new Promise((resolve) => { timer = setTimeout(resolve, timeoutMs); }),
    ]);
  } catch {
    // Disconnection after Stop or a failed session is already terminal.
  } finally {
    clearTimeout(timer);
  }
}

export async function runBrowserScript(source, {
  env = process.env, driver = puppeteer, signal,
  timeoutMs = 120_000, connectTimeoutMs = 30_000, closeTimeoutMs = 1_000,
} = {}) {
  const account = env.KITESURF_ACCOUNT_ID?.trim();
  const token = env.KITESURF_API_TOKEN?.trim();
  if (!account || !token) {
    throw new Error("Set KITESURF_ACCOUNT_ID and KITESURF_API_TOKEN in ~/.config/kitesurf/credentials.json (0600), or the environment.");
  }
  if (!/^[a-f0-9]{32}$/i.test(account)) throw new Error("Invalid KITESURF_ACCOUNT_ID (expected 32 hex characters).");
  if (/\s/.test(token)) throw new Error("Invalid KITESURF_API_TOKEN.");
  const execute = new AsyncFunction("page", "context", "browser", source);
  if (signal?.aborted) throw new Error("Browser task stopped.");

  let browser;
  let finished = false;
  let timer;
  let connectionTimer;
  let stop;
  const interrupted = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("Browser task exceeded its 120-second session budget.")), timeoutMs);
    connectionTimer = setTimeout(() => reject(new Error("Browser connection timed out.")), Math.min(connectTimeoutMs, timeoutMs));
    stop = () => reject(new Error("Browser task stopped."));
    signal?.addEventListener("abort", stop, { once: true });
  });
  const work = async () => {
    const connected = await driver.connect({
      browserWSEndpoint: `wss://api.cloudflare.com/client/v4/accounts/${account}/browser-run/devtools/browser?browser=kitesurf`,
      headers: { Authorization: `Bearer ${token}` }, protocolTimeout: 30_000,
    });
    clearTimeout(connectionTimer);
    // A connection may complete after cancellation. Never run the script then.
    if (finished) {
      await closeBrowser(connected, closeTimeoutMs);
      return;
    }
    browser = connected;
    const context = browser.defaultBrowserContext();
    const page = (await context.pages())[0] || await context.newPage();
    if (finished) return;
    page.setDefaultTimeout(30_000);
    page.setDefaultNavigationTimeout(30_000);
    return await execute(page, context, browser);
  };
  try {
    return await Promise.race([work(), interrupted]);
  } finally {
    finished = true;
    clearTimeout(timer);
    clearTimeout(connectionTimer);
    signal?.removeEventListener("abort", stop);
    await closeBrowser(browser, closeTimeoutMs);
  }
}

export function safeError(error, env = process.env) {
  let message = String(error?.message || "Browser task failed.");
  for (const secret of new Set([env.KITESURF_API_TOKEN, env.KITESURF_API_TOKEN?.trim()])) {
    if (secret) message = message.replaceAll(secret, "[redacted]");
  }
  return message;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 1 && ["--help", "-h"].includes(args[0])) {
    await new Promise((resolve) => process.stdout.write(HELP, resolve));
    return;
  }
  if (args.length > 1 || (args[0]?.startsWith("-") && args[0] !== "-")) {
    throw new Error("Usage: kitesurf [script.js|-]; see kitesurf --help.");
  }
  const source = readFileSync(!args[0] || args[0] === "-" ? 0 : args[0], "utf8");
  const configuredEnv = loadBrowserEnvironment();
  errorEnv = configuredEnv;
  const controller = new AbortController();
  const stop = () => controller.abort();
  const signals = ["SIGTERM", "SIGINT", "SIGHUP"];
  for (const signal of signals) process.on(signal, stop);
  try {
    const result = await runBrowserScript(source, { env: configuredEnv, signal: controller.signal });
    await new Promise((resolve) => process.stdout.write(`${JSON.stringify(result ?? null)}\n`, resolve));
  } finally {
    for (const signal of signals) process.off(signal, stop);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  main().then(() => process.exit(0), (error) => {
    process.stderr.write(`kitesurf: ${safeError(error, errorEnv)}\n`, () => process.exit(1));
  });
}
