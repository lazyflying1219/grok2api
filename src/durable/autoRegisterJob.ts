import type { Env } from "../env";
import { addTokens } from "../repo/tokens";
import { nowMs } from "../utils/time";
import type { ActionConfig, GrokSettingsSnapshot, RegisterPool, RegisterSettingsSnapshot } from "../register/autoRegister";
import { getActionConfigCached, registerOne } from "../register/autoRegister";
import { getSettings } from "../settings";

type JobStatus = "idle" | "starting" | "running" | "stopping" | "stopped" | "completed" | "error";

interface JobState {
  job_id: string;
  status: JobStatus;
  pool: RegisterPool;
  total: number;
  concurrency: number;
  completed: number;
  added: number;
  errors: number;
  error: string | null;
  last_error: string | null;
  logs: string[];
  started_at: number;
  finished_at: number | null;
  stop_requested: boolean;
  max_errors: number;
  max_runtime_minutes: number;
  register: RegisterSettingsSnapshot;
  grok: GrokSettingsSnapshot;
  action: (ActionConfig & { updated_at: number }) | null;
}

function clampInt(n: unknown, min: number, max: number, fallback: number): number {
  const v = Number(n);
  if (!Number.isFinite(v)) return fallback;
  return Math.max(min, Math.min(max, Math.floor(v)));
}

function shortError(msg: unknown): string {
  const s = (msg instanceof Error ? msg.message : String(msg ?? "")).trim();
  if (!s) return "unknown";
  return s.length > 500 ? `${s.slice(0, 500)}...` : s;
}

function pushLog(job: JobState, message: string): void {
  const ts = new Date().toISOString();
  const line = `${ts} ${String(message || "").trim()}`.trim();
  const next = [...(job.logs || []), line];
  job.logs = next.slice(-200);
}

function jobToDict(job: JobState): Record<string, unknown> {
  return {
    job_id: job.job_id,
    status: job.status,
    pool: job.pool,
    total: job.total,
    concurrency: job.concurrency,
    completed: job.completed,
    added: job.added,
    errors: job.errors,
    error: job.error,
    last_error: job.last_error,
    logs: (job.logs || []).slice(-80),
    started_at: job.started_at,
    finished_at: job.finished_at,
  };
}

export class AutoRegisterJob implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  private async loadJob(): Promise<JobState | null> {
    const job = await this.state.storage.get<JobState>("job");
    return job ?? null;
  }

  private async saveJob(job: JobState): Promise<void> {
    await this.state.storage.put("job", job);
  }

  private async ensureAction(job: JobState): Promise<ActionConfig> {
    const now = nowMs();
    const cur = job.action;
    if (cur && now - cur.updated_at < 10 * 60 * 1000) return cur;
    pushLog(job, "Fetching sign-up action config...");
    const fresh = await getActionConfigCached(cur as any, 0, { cf_clearance: job.grok.cf_clearance });
    job.action = { ...fresh, updated_at: now };
    pushLog(job, `Action config ready (action_id=${fresh.action_id.slice(0, 8)}…)`);
    await this.saveJob(job);
    return job.action;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === "/start" && request.method === "POST") {
      const body = (await request.json().catch(() => ({}))) as any;
      const jobId = String(body?.job_id ?? "").trim();
      if (!jobId) return Response.json({ error: "Missing job_id" }, { status: 400 });

      const existing = await this.loadJob();
      if (existing && ["starting", "running", "stopping"].includes(existing.status)) {
        return Response.json({ error: "Auto registration already running" }, { status: 409 });
      }

      const settings = await getSettings(this.env);

      const register: RegisterSettingsSnapshot = {
        worker_domain: String(settings.register.worker_domain ?? "").trim(),
        email_domain: String(settings.register.email_domain ?? "").trim(),
        admin_password: String(settings.register.admin_password ?? "").trim(),
        yescaptcha_key: String(settings.register.yescaptcha_key ?? "").trim(),
        solver_url: String(settings.register.solver_url ?? "").trim() || "http://127.0.0.1:5072",
      };
      const grok: GrokSettingsSnapshot = { cf_clearance: String(settings.grok.cf_clearance ?? "").trim() };

      if (!register.worker_domain || !register.email_domain || !register.admin_password) {
        const job: JobState = {
          job_id: jobId,
          status: "error",
          pool: "ssoBasic",
          total: 0,
          concurrency: 1,
          completed: 0,
          added: 0,
          errors: 0,
          error: "Missing required register config: register.worker_domain / register.email_domain / register.admin_password",
          last_error: null,
          logs: [],
          started_at: nowMs(),
          finished_at: nowMs(),
          stop_requested: false,
          max_errors: 0,
          max_runtime_minutes: 0,
          register,
          grok,
          action: null,
        };
        pushLog(job, "Start failed: missing register config (worker_domain/email_domain/admin_password)");
        await this.saveJob(job);
        return Response.json(jobToDict(job), { status: 200 });
      }

      const total = clampInt(body?.total ?? body?.count, 1, 10_000, 100);
      const pool = (String(body?.pool ?? "ssoBasic").trim() as RegisterPool) || "ssoBasic";
      const threads = clampInt(body?.concurrency, 1, 10, settings.register.register_threads ?? 10);

      const maxErrorsRaw = Number(settings.register.max_errors ?? 0);
      const maxErrors = Number.isFinite(maxErrorsRaw) && maxErrorsRaw > 0 ? Math.floor(maxErrorsRaw) : Math.max(30, total * 5);
      const maxRuntimeRaw = Number(settings.register.max_runtime_minutes ?? 0);
      const maxRuntime = Number.isFinite(maxRuntimeRaw) && maxRuntimeRaw > 0 ? Math.floor(maxRuntimeRaw) : 0;

      const job: JobState = {
        job_id: jobId,
        status: "starting",
        pool,
        total,
        concurrency: threads,
        completed: 0,
        added: 0,
        errors: 0,
        error: null,
        last_error: null,
        logs: [],
        started_at: nowMs(),
        finished_at: null,
        stop_requested: false,
        max_errors: maxErrors,
        max_runtime_minutes: maxRuntime,
        register,
        grok,
        action: null,
      };

      pushLog(job, `Job created: total=${total} pool=${pool} concurrency=${threads}`);
      if (register.yescaptcha_key) pushLog(job, "Using YesCaptcha (register.yescaptcha_key set)");
      else pushLog(job, `Using solver_url=${register.solver_url}`);
      if (grok.cf_clearance) pushLog(job, "Using cf_clearance for challenge bypass (best-effort)");
      await this.saveJob(job);
      await this.state.storage.setAlarm(Date.now() + 100);
      return Response.json(jobToDict(job), { status: 200 });
    }

    if (path === "/status" && request.method === "GET") {
      const job = await this.loadJob();
      if (!job) return Response.json({ status: "not_found" }, { status: 404 });
      return Response.json(jobToDict(job), { status: 200 });
    }

    if (path === "/stop" && request.method === "POST") {
      const job = await this.loadJob();
      if (!job) return Response.json({ status: "not_found" }, { status: 404 });
      if (job.status === "completed" || job.status === "stopped" || job.status === "error") {
        return Response.json(jobToDict(job), { status: 200 });
      }
      job.stop_requested = true;
      if (job.status === "running" || job.status === "starting") job.status = "stopping";
      pushLog(job, "Stop requested");
      await this.saveJob(job);
      await this.state.storage.setAlarm(Date.now() + 100);
      return Response.json(jobToDict(job), { status: 200 });
    }

    return new Response("Not Found", { status: 404 });
  }

  async alarm(): Promise<void> {
    const job = await this.loadJob();
    if (!job) return;

    if (job.status === "error" || job.status === "completed" || job.status === "stopped") return;

    if (job.stop_requested || job.status === "stopping") {
      job.status = "stopped";
      job.finished_at = nowMs();
      pushLog(job, "Job stopped");
      await this.saveJob(job);
      return;
    }

    const elapsedMs = nowMs() - job.started_at;
    if (job.max_runtime_minutes > 0 && elapsedMs > job.max_runtime_minutes * 60_000) {
      job.status = "error";
      job.error = `Timeout after ${job.max_runtime_minutes} minutes.`;
      job.finished_at = nowMs();
      pushLog(job, job.error);
      await this.saveJob(job);
      return;
    }

    if (job.errors >= job.max_errors) {
      job.status = "error";
      job.error = `Too many failures (${job.errors}/${job.max_errors}). Check register config/solver.`;
      job.finished_at = nowMs();
      pushLog(job, job.error);
      await this.saveJob(job);
      return;
    }

    if (job.status === "starting") {
      job.status = "running";
      pushLog(job, "Job running");
    }

    const remaining = Math.max(0, job.total - job.completed);
    if (remaining === 0) {
      job.status = "completed";
      job.finished_at = nowMs();
      pushLog(job, "Job completed");
      await this.saveJob(job);
      return;
    }

    let action: ActionConfig;
    try {
      action = await this.ensureAction(job);
    } catch (e) {
      job.errors += 1;
      job.last_error = shortError(e);
      pushLog(job, `Init failed: ${job.last_error}`);
      await this.saveJob(job);
      await this.state.storage.setAlarm(Date.now() + 2000);
      return;
    }

    const batchSize = Math.max(1, Math.min(job.concurrency, remaining));
    const tokenType = job.pool === "ssoSuper" ? "ssoSuper" : "sso";

    const results = await Promise.all(
      Array.from({ length: batchSize }, async () => {
        if (job.stop_requested) return null;
        try {
          const { token } = await registerOne({ action, register: job.register, grok: job.grok });
          await addTokens(this.env.DB, [token], tokenType);
          return token;
        } catch (e) {
          return { error: shortError(e) } as any;
        }
      }),
    );

    for (const r of results) {
      if (!r) continue;
      if (typeof r === "string") {
        job.completed += 1;
        job.added += 1;
        pushLog(job, `Registered OK (${job.completed}/${job.total})`);
      } else if (typeof r === "object" && r && "error" in r) {
        job.errors += 1;
        job.last_error = shortError((r as any).error);
        pushLog(job, `Register failed: ${job.last_error}`);
      }
    }

    if (job.stop_requested) {
      job.status = "stopped";
      job.finished_at = nowMs();
      pushLog(job, "Job stopped");
      await this.saveJob(job);
      return;
    }

    if (job.completed >= job.total) {
      job.status = "completed";
      job.finished_at = nowMs();
      pushLog(job, "Job completed");
      await this.saveJob(job);
      return;
    }

    await this.saveJob(job);
    await this.state.storage.setAlarm(Date.now() + 500);
  }
}
