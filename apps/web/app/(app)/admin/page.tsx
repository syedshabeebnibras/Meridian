import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { getWorkspaceUsage } from "@/lib/db";
import { orchestratorJson, requireCaller } from "@/lib/orchestrator-server";
import { requireRoleAtLeast } from "@/lib/session-guard";

export const dynamic = "force-dynamic";

interface Capability {
  environment: string;
  version: string;
  template_provider: string;
  session_store_backend: string;
  semantic_cache_backend: string;
  retrieval_backend: string;
  feedback_store: string;
  audit_sink: string;
  input_guardrails: string[];
  output_guardrails: string[];
  rate_limiter_backend: string;
  cost_breaker_backend: string;
  model_gateway_url: string;
  tenant_aware: boolean;
  otel_enabled: boolean;
  internal_auth: string;
}

async function fetchCapability(): Promise<Capability | { error: string }> {
  try {
    const caller = await requireCaller();
    return await orchestratorJson<Capability>(caller, "/debug/config");
  } catch (err) {
    return { error: err instanceof Error ? err.message : String(err) };
  }
}

export default async function AdminPage() {
  // Visible only to owners + admins. Non-admins are bounced to /dashboard.
  const ctx = await requireRoleAtLeast("admin");
  const [usage, capability] = await Promise.all([
    getWorkspaceUsage(ctx.workspaceId, 30),
    fetchCapability(),
  ]);
  const cost30d = Number((usage.total_cost_usd as string) || "0") || 0;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-fg)]">
          Admin
        </h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Operational view for owners + admins. Backend details are reported via the
          orchestrator&apos;s redacted{" "}
          <code className="font-mono">/debug/config</code> — never secrets.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <Stat label="Requests · 30d" value={usage.total_requests.toLocaleString()} />
        <Stat label="Cost · 30d" value={`$${cost30d.toFixed(cost30d < 1 ? 4 : 2)}`} />
        <Stat
          label="Tokens · 30d"
          value={(usage.total_input_tokens + usage.total_output_tokens).toLocaleString()}
        />
      </section>

      <section className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Backend capability</CardTitle>
            <CardDescription>
              Snapshot from the orchestrator at request time. Mismatched expectations
              here are how production drift gets caught.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {"error" in capability ? (
              <div className="rounded-[var(--radius-md)] border border-[color-mix(in_oklch,var(--color-warning)_30%,transparent)] bg-[color-mix(in_oklch,var(--color-warning)_10%,var(--color-bg))] p-3 text-xs text-[var(--color-warning)]">
                Could not reach the orchestrator: {capability.error}
              </div>
            ) : (
              <CapabilityList cap={capability} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Launch gates</CardTitle>
            <CardDescription>
              The checklist Meridian shipped against. Source: <code>LAUNCH.md</code>.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              <Gate label="Tenant isolation enforced" status="pass" />
              <Gate label="Internal-key fail closed in prod" status="pass" />
              <Gate label="Guardrails wired (input + output)" status="pass" />
              <Gate label="Audit sink durable (Postgres)" status="depends" hint="Set DATABASE_URL" />
              <Gate label="Distributed rate limiter" status="depends" hint="Set REDIS_URL" />
              <Gate label="Document ingestion (Phase 6)" status="pass" />
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Red-team status</CardTitle>
            <CardDescription>Last full sweep against the prompt-injection corpus.</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-[var(--color-fg-muted)]">
            <p>
              Run via <code className="font-mono">make red-team</code> in CI. Latest
              report and pass-rate land in <code className="font-mono">REGRESSION.md</code>.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quality + cost dashboards</CardTitle>
            <CardDescription>
              Prometheus metrics exposed at <code>/metrics</code> by the orchestrator.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-[var(--color-fg-muted)]">
            <p>
              Hook a Grafana board against <code className="font-mono">meridian_*</code>{" "}
              metrics for live latency / cost / cache-hit / refusal-rate views.
            </p>
            <p>
              Per-(workspace, action) labels are present so dashboards can drill into a
              single tenant when needed.
            </p>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function CapabilityList({ cap }: { cap: Capability }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
      <Row label="Environment" value={cap.environment} />
      <Row label="Version" value={cap.version} mono />
      <Row label="Tenant-aware" value={cap.tenant_aware ? "yes" : "no"} />
      <Row label="Internal auth" value={cap.internal_auth} />
      <Row label="Templates" value={cap.template_provider} />
      <Row label="Sessions" value={cap.session_store_backend} />
      <Row label="Semantic cache" value={cap.semantic_cache_backend} />
      <Row label="Retrieval" value={cap.retrieval_backend} />
      <Row label="Feedback store" value={cap.feedback_store} />
      <Row label="Audit sink" value={cap.audit_sink} />
      <Row label="Rate limiter" value={cap.rate_limiter_backend} />
      <Row label="Cost breaker" value={cap.cost_breaker_backend} />
      <Row label="OTel" value={cap.otel_enabled ? "on" : "off"} />
      <Row label="Model gateway" value={cap.model_gateway_url} mono />
      <Row
        label="Input guardrails"
        value={cap.input_guardrails.length === 0 ? "none" : cap.input_guardrails.join(", ")}
      />
      <Row
        label="Output guardrails"
        value={cap.output_guardrails.length === 0 ? "none" : cap.output_guardrails.join(", ")}
      />
    </dl>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <>
      <dt className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
        {label}
      </dt>
      <dd
        className={`truncate text-[var(--color-fg)] ${mono ? "font-mono" : ""}`}
        title={value}
      >
        {value}
      </dd>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
          {label}
        </div>
        <div className="mt-1 text-2xl font-semibold tracking-tight text-[var(--color-fg)]">
          {value}
        </div>
      </CardContent>
    </Card>
  );
}

function Gate({
  label,
  status,
  hint,
}: {
  label: string;
  status: "pass" | "pending" | "depends";
  hint?: string;
}) {
  const variant = status === "pass" ? "success" : status === "depends" ? "info" : "warning";
  const text = status === "pass" ? "Pass" : status === "depends" ? "Conditional" : "Pending";
  return (
    <li className="flex items-center justify-between gap-3">
      <div>
        <span>{label}</span>
        {hint ? (
          <span className="ml-2 font-mono text-[10px] text-[var(--color-fg-subtle)]">
            {hint}
          </span>
        ) : null}
      </div>
      <Badge variant={variant}>{text}</Badge>
    </li>
  );
}
