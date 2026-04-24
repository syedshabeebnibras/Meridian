import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const revalidate = 10;

const ORCH_URL = (process.env.ORCH_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

interface Snapshot {
  requests_total: number;
  cost_usd_total: number;
  rate_limited_total: number;
  request_count: number;
  latency_sum_seconds: number;
  avg_latency_seconds: number | null;
}

function parseSnapshot(text: string): Snapshot {
  let requests_total = 0;
  let cost_usd_total = 0;
  let rate_limited_total = 0;
  let request_count = 0;
  let latency_sum_seconds = 0;

  for (const line of text.split("\n")) {
    if (line.startsWith("#") || line.trim() === "") continue;
    const match = line.match(/^([a-z_]+)(\{[^}]*\})?\s+([0-9.e+-]+)/);
    if (!match) continue;
    const [, name, , value] = match;
    const num = Number.parseFloat(value);
    if (!Number.isFinite(num)) continue;

    if (name === "meridian_requests_total") requests_total += num;
    else if (name === "meridian_cost_usd_total") cost_usd_total = num;
    else if (name === "meridian_rate_limited_total") rate_limited_total = num;
    else if (name === "meridian_request_duration_seconds_count") request_count = num;
    else if (name === "meridian_request_duration_seconds_sum") latency_sum_seconds = num;
  }

  const avg = request_count > 0 ? latency_sum_seconds / request_count : null;
  return {
    requests_total,
    cost_usd_total,
    rate_limited_total,
    request_count,
    latency_sum_seconds,
    avg_latency_seconds: avg,
  };
}

export async function GET(): Promise<Response> {
  try {
    const upstream = await fetch(`${ORCH_URL}/metrics`, {
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: "metrics upstream failed" }, { status: 502 });
    }
    const text = await upstream.text();
    return NextResponse.json(parseSnapshot(text));
  } catch {
    // The landing page renders gracefully when metrics are unavailable.
    return NextResponse.json({
      requests_total: 0,
      cost_usd_total: 0,
      rate_limited_total: 0,
      request_count: 0,
      latency_sum_seconds: 0,
      avg_latency_seconds: null,
    } satisfies Snapshot);
  }
}
