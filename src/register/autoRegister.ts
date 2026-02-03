import { ensureTosAndNsfw } from "../grok/accountSettings";

export type RegisterPool = "ssoBasic" | "ssoSuper";

export interface ActionConfig {
  site_key: string;
  state_tree: string;
  action_id: string;
}

export interface RegisterSettingsSnapshot {
  worker_domain: string;
  email_domain: string;
  admin_password: string;
  yescaptcha_key: string;
  solver_url: string;
}

export interface GrokSettingsSnapshot {
  cf_clearance: string;
}

const SITE_URL = "https://accounts.x.ai";
const SIGNUP_URL = `${SITE_URL}/sign-up`;

const DEFAULT_SITE_KEY = "0x4AAAAAAAhr9JGVDZbrZOo0";

const USER_AGENTS = [
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.0.0 Safari/537.36 Edg/99.0.1150.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.0.0 Safari/537.36 Edg/101.0.1210.47",
];

function pickUserAgent(): string {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)] ?? USER_AGENTS[0]!;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function randomInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function randomLower(n: number): string {
  const chars = "abcdefghijklmnopqrstuvwxyz";
  let out = "";
  for (let i = 0; i < n; i++) out += chars[Math.floor(Math.random() * chars.length)]!;
  return out;
}

function randomDigits(n: number): string {
  const chars = "0123456789";
  let out = "";
  for (let i = 0; i < n; i++) out += chars[Math.floor(Math.random() * chars.length)]!;
  return out;
}

function generateEmailName(): string {
  const letters1 = randomLower(randomInt(4, 6));
  const digits = randomDigits(randomInt(1, 3));
  const letters2 = randomLower(randomInt(0, 5));
  return `${letters1}${digits}${letters2}`;
}

function generateRandomName(): string {
  const first = String.fromCharCode(65 + Math.floor(Math.random() * 26));
  return first + randomLower(randomInt(3, 5));
}

function generatePassword(len = 15): string {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  let out = "";
  for (let i = 0; i < len; i++) out += chars[Math.floor(Math.random() * chars.length)]!;
  return out;
}

function encodeVarint(n: number): Uint8Array {
  const out: number[] = [];
  let v = n >>> 0;
  while (v >= 0x80) {
    out.push((v & 0x7f) | 0x80);
    v >>>= 7;
  }
  out.push(v & 0x7f);
  return new Uint8Array(out);
}

function concatBytes(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((a, b) => a + b.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const p of parts) {
    out.set(p, offset);
    offset += p.length;
  }
  return out;
}

function encodeStringField(fieldId: number, value: string): Uint8Array {
  const key = encodeVarint((fieldId << 3) | 2);
  const bytes = new TextEncoder().encode(value);
  const len = encodeVarint(bytes.length);
  return concatBytes([key, len, bytes]);
}

function grpcWebFrame(payload: Uint8Array): Uint8Array {
  const header = new Uint8Array(5);
  header[0] = 0;
  header[1] = (payload.length >>> 24) & 0xff;
  header[2] = (payload.length >>> 16) & 0xff;
  header[3] = (payload.length >>> 8) & 0xff;
  header[4] = payload.length & 0xff;
  return concatBytes([header, payload]);
}

function toArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

function parseSetCookieHeaders(headers: Headers): string[] {
  const anyHeaders = headers as any;
  if (typeof anyHeaders.getSetCookie === "function") return anyHeaders.getSetCookie() as string[];
  const sc = headers.get("set-cookie");
  return sc ? [sc] : [];
}

class CookieJar {
  private map = new Map<string, string>();

  set(name: string, value: string) {
    const n = String(name || "").trim();
    const v = String(value || "").trim();
    if (!n || !v) return;
    this.map.set(n, v);
  }

  setFromHeader(setCookie: string) {
    const first = String(setCookie || "").split(";", 1)[0] ?? "";
    const idx = first.indexOf("=");
    if (idx <= 0) return;
    const name = first.slice(0, idx).trim();
    const value = first.slice(idx + 1).trim();
    if (!name) return;
    this.map.set(name, value);
  }

  absorb(res: Response) {
    for (const sc of parseSetCookieHeaders(res.headers)) this.setFromHeader(sc);
  }

  get(name: string): string {
    return this.map.get(name) ?? "";
  }

  header(): string {
    const items: string[] = [];
    for (const [k, v] of this.map.entries()) {
      if (!k || !v) continue;
      items.push(`${k}=${v}`);
    }
    return items.join("; ");
  }
}

async function fetchWithJar(url: string, init: RequestInit, jar: CookieJar): Promise<Response> {
  const headers = new Headers(init.headers);
  const cookie = jar.header();
  if (cookie && !headers.has("cookie")) headers.set("cookie", cookie);
  const res = await fetch(url, { ...init, headers });
  jar.absorb(res);
  return res;
}

async function fetchFollowRedirects(url: string, init: RequestInit, jar: CookieJar, max = 8): Promise<Response> {
  let curUrl = url;
  let curInit: RequestInit = { ...init };

  for (let i = 0; i < max; i++) {
    const res = await fetchWithJar(curUrl, { ...curInit, redirect: "manual" }, jar);
    if (![301, 302, 303, 307, 308].includes(res.status)) return res;
    const loc = res.headers.get("location");
    if (!loc) return res;
    const nextUrl = new URL(loc, curUrl).toString();
    curUrl = nextUrl;
    if (res.status === 303) curInit = { method: "GET" };
  }
  return fetchWithJar(curUrl, init, jar);
}

function parseHtmlTitle(html: string): string {
  return html.match(/<title>([^<]+)<\/title>/i)?.[1]?.trim() ?? "";
}

async function initActionConfig(userAgent: string, opts?: { cf_clearance?: string }): Promise<ActionConfig> {
  const headers: Record<string, string> = {
    "user-agent": userAgent,
    accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  };
  const clearance = String(opts?.cf_clearance ?? "").trim();
  if (clearance) headers.cookie = `cf_clearance=${clearance}`;

  const res = await fetch(SIGNUP_URL, { headers });
  const html = await res.text();
  const title = parseHtmlTitle(html);
  const cfRay = res.headers.get("cf-ray") ?? "";
  const blockedHint = title && /cloudflare|attention required|just a moment/i.test(title);

  if (!res.ok) {
    const hint = blockedHint ? " (blocked by Cloudflare challenge)" : "";
    const ray = cfRay ? ` cf_ray=${cfRay}` : "";
    throw new Error(`Register init failed: sign-up HTTP ${res.status} title="${title || "unknown"}"${hint}${ray}`);
  }

  const siteKey = html.match(/sitekey\":\"(0x4[a-zA-Z0-9_-]+)\"/)?.[1] ?? DEFAULT_SITE_KEY;
  const stateTree = html.match(/next-router-state-tree\":\"([^\"]+)\"/)?.[1] ?? "";

  const scriptSrcs = Array.from(html.matchAll(/<script[^>]+src=\"([^\"]+)\"[^>]*>/g))
    .map((m) => m[1]!)
    .filter((src) => src.includes("_next/static"))
    .slice(0, 30);

  if (!scriptSrcs.length) {
    throw new Error(
      `Register init failed: no _next/static scripts found (title="${title || "unknown"}"${cfRay ? ` cf_ray=${cfRay}` : ""})`,
    );
  }

  let actionId = "";
  for (const src of scriptSrcs) {
    const jsUrl = new URL(src, SIGNUP_URL).toString();
    const jsHeaders: Record<string, string> = { "user-agent": userAgent };
    if (clearance) jsHeaders.cookie = `cf_clearance=${clearance}`;
    const js = await fetch(jsUrl, { headers: jsHeaders }).then((r) => r.text());
    const match = js.match(/7f[a-fA-F0-9]{40}/);
    if (match?.[0]) {
      actionId = match[0];
      break;
    }
    await sleep(100);
  }

  if (!actionId) {
    throw new Error(
      `Register init failed: missing action_id (scripts=${scriptSrcs.length} title="${title || "unknown"}"${cfRay ? ` cf_ray=${cfRay}` : ""})`,
    );
  }
  return { site_key: siteKey, state_tree: stateTree, action_id: actionId };
}

async function createEmail(settings: RegisterSettingsSnapshot): Promise<{ jwt: string; address: string }> {
  const url = `https://${settings.worker_domain}/admin/new_address`;
  const name = generateEmailName();
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-admin-auth": settings.admin_password,
    },
    body: JSON.stringify({ enablePrefix: true, name, domain: settings.email_domain }),
  });
  if (!res.ok) throw new Error(`create_email failed: HTTP ${res.status}`);
  const data = (await res.json()) as any;
  const jwt = String(data?.jwt ?? "").trim();
  const address = String(data?.address ?? "").trim();
  if (!jwt || !address) throw new Error("create_email failed: missing jwt/address");
  return { jwt, address };
}

async function fetchFirstEmail(jwt: string, settings: RegisterSettingsSnapshot): Promise<string | null> {
  const url = `https://${settings.worker_domain}/api/mails?limit=10&offset=0`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${jwt}`,
      accept: "application/json",
    },
  });
  if (!res.ok) return null;
  const data = (await res.json()) as any;
  const raw = data?.results?.[0]?.raw;
  return typeof raw === "string" ? raw : null;
}

async function sendEmailCode(email: string, jar: CookieJar, userAgent: string): Promise<void> {
  const url = `${SITE_URL}/auth_mgmt.AuthManagement/CreateEmailValidationCode`;
  const payload = encodeStringField(1, email);
  const body = grpcWebFrame(payload);
  const res = await fetchWithJar(
    url,
    {
      method: "POST",
      headers: {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-user-agent": "connect-es/2.1.1",
        origin: SITE_URL,
        referer: `${SITE_URL}/sign-up?redirect=grok-com`,
        "user-agent": userAgent,
      },
      body: toArrayBuffer(body),
    },
    jar,
  );
  if (!res.ok) throw new Error(`send_email_code failed: HTTP ${res.status}`);
}

async function verifyEmailCode(email: string, code: string, jar: CookieJar, userAgent: string): Promise<void> {
  const url = `${SITE_URL}/auth_mgmt.AuthManagement/VerifyEmailValidationCode`;
  const payload = concatBytes([encodeStringField(1, email), encodeStringField(2, code)]);
  const body = grpcWebFrame(payload);
  const res = await fetchWithJar(
    url,
    {
      method: "POST",
      headers: {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-user-agent": "connect-es/2.1.1",
        origin: SITE_URL,
        referer: `${SITE_URL}/sign-up?redirect=grok-com`,
        "user-agent": userAgent,
      },
      body: toArrayBuffer(body),
    },
    jar,
  );
  if (!res.ok) throw new Error(`verify_email_code failed: HTTP ${res.status}`);
}

async function pollVerifyCode(jwt: string, settings: RegisterSettingsSnapshot, timeoutMs = 30_000): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const raw = await fetchFirstEmail(jwt, settings);
    if (raw) {
      const m = raw.match(/>([A-Z0-9]{3}-[A-Z0-9]{3})</);
      if (m?.[1]) return m[1].replace("-", "");
    }
    await sleep(1000);
  }
  throw new Error("verify_code not received");
}

async function solveTurnstile(args: {
  yescaptcha_key: string;
  solver_url: string;
  siteurl: string;
  sitekey: string;
}): Promise<string> {
  const yKey = (args.yescaptcha_key || "").trim();
  if (yKey) {
    const createRes = await fetch("https://api.yescaptcha.com/createTask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        clientKey: yKey,
        task: { type: "TurnstileTaskProxyless", websiteURL: args.siteurl, websiteKey: args.sitekey },
      }),
    });
    const create = (await createRes.json().catch(() => ({}))) as any;
    if (!createRes.ok || create?.errorId !== 0) throw new Error(`YesCaptcha createTask failed: ${create?.errorDescription || createRes.status}`);
    const taskId = String(create?.taskId ?? "").trim();
    if (!taskId) throw new Error("YesCaptcha missing taskId");

    for (let i = 0; i < 30; i++) {
      const res = await fetch("https://api.yescaptcha.com/getTaskResult", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ clientKey: yKey, taskId }),
      });
      const data = (await res.json().catch(() => ({}))) as any;
      if (!res.ok || data?.errorId !== 0) throw new Error(`YesCaptcha getTaskResult failed: ${data?.errorDescription || res.status}`);
      if (data?.status === "ready") {
        const token = String(data?.solution?.token ?? "").trim();
        if (token) return token;
        throw new Error("YesCaptcha returned empty token");
      }
      await sleep(2000);
    }
    throw new Error("YesCaptcha timeout");
  }

  const base = (args.solver_url || "").trim() || "http://127.0.0.1:5072";
  const createRes = await fetch(`${base.replace(/\/+$/, "")}/turnstile?url=${encodeURIComponent(args.siteurl)}&sitekey=${encodeURIComponent(args.sitekey)}`);
  const create = (await createRes.json().catch(() => ({}))) as any;
  const taskId = String(create?.taskId ?? "").trim();
  if (!createRes.ok || !taskId) throw new Error(`Solver create task failed: ${create?.errorDescription || create?.errorCode || createRes.status}`);

  for (let i = 0; i < 30; i++) {
    const res = await fetch(`${base.replace(/\/+$/, "")}/result?id=${encodeURIComponent(taskId)}`);
    const data = (await res.json().catch(() => ({}))) as any;
    if (!res.ok) throw new Error(`Solver get result failed: HTTP ${res.status}`);
    if (data?.errorId != null && data?.errorId !== 0) throw new Error(String(data?.errorDescription || data?.errorCode || "solver error"));
    const token = String(data?.solution?.token ?? "").trim();
    if (token) {
      if (token !== "CAPTCHA_FAIL") return token;
      throw new Error("CAPTCHA_FAIL");
    }
    await sleep(2000);
  }
  throw new Error("Solver timeout");
}

export async function registerOne(args: {
  action: ActionConfig;
  register: RegisterSettingsSnapshot;
  grok: GrokSettingsSnapshot;
  user_agent?: string;
}): Promise<{ token: string }> {
  const ua = args.user_agent || pickUserAgent();
  const jar = new CookieJar();
  const clearance = String(args.grok?.cf_clearance ?? "").trim();
  if (clearance) jar.set("cf_clearance", clearance);

  try {
    await fetchWithJar(SITE_URL, { headers: { "user-agent": ua } }, jar);
  } catch {
    // best-effort warmup
  }

  const password = generatePassword();
  const { jwt, address } = await createEmail(args.register);
  await sendEmailCode(address, jar, ua);
  const verifyCode = await pollVerifyCode(jwt, args.register, 30_000);
  await verifyEmailCode(address, verifyCode, jar, ua);

  for (let attempt = 0; attempt < 3; attempt++) {
    const turnstile = await solveTurnstile({
      yescaptcha_key: args.register.yescaptcha_key,
      solver_url: args.register.solver_url,
      siteurl: SIGNUP_URL,
      sitekey: args.action.site_key || DEFAULT_SITE_KEY,
    }).catch((e) => {
      throw new Error(`turnstile failed: ${e instanceof Error ? e.message : String(e)}`);
    });

    const payload = [
      {
        emailValidationCode: verifyCode,
        createUserAndSessionRequest: {
          email: address,
          givenName: generateRandomName(),
          familyName: generateRandomName(),
          clearTextPassword: password,
          tosAcceptedVersion: "$undefined",
        },
        turnstileToken: turnstile,
        promptOnDuplicateEmail: true,
      },
    ];

    const res = await fetchWithJar(
      SIGNUP_URL,
      {
        method: "POST",
        headers: {
          "user-agent": ua,
          accept: "text/x-component",
          "content-type": "text/plain;charset=UTF-8",
          origin: SITE_URL,
          referer: SIGNUP_URL,
          "next-router-state-tree": args.action.state_tree,
          "next-action": args.action.action_id,
        },
        body: JSON.stringify(payload),
      },
      jar,
    );

    if (!res.ok) {
      await sleep(3000);
      continue;
    }
    const text = await res.text();
    const m = text.match(/(https:\/\/[^\"\s]+set-cookie\?q=[^:\"\s]+)1:/);
    const verifyUrl = m?.[1] ?? "";
    if (!verifyUrl) throw new Error("sign_up missing set-cookie redirect");

    await fetchFollowRedirects(verifyUrl, { headers: { "user-agent": ua } }, jar, 8);

    const sso = jar.get("sso");
    if (!sso) throw new Error("sign_up missing sso cookie");

    const tos = await ensureTosAndNsfw({ token: sso, cf_clearance: args.grok.cf_clearance, user_agent: ua });
    if (!tos.ok) throw new Error(tos.error || "tos/nsfw failed");

    return { token: sso };
  }

  throw new Error("Registration failed after retries");
}

export async function getActionConfigCached(
  current: ActionConfig | null,
  maxAgeMs = 10 * 60 * 1000,
  opts?: { cf_clearance?: string },
): Promise<ActionConfig> {
  if (current && (current as any)?._ts && Date.now() - Number((current as any)._ts) < maxAgeMs) return current;
  const ua = pickUserAgent();
  const fresh = await initActionConfig(ua, opts);
  (fresh as any)._ts = Date.now();
  return fresh;
}
