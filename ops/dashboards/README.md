# Dashboards

Ten dashboards per Section 11. Each is declared as a vendor-neutral YAML
spec (metrics + panels), so the team can import into Grafana, Datadog, or
Langfuse without rewriting.

Each file has the shape:

```yaml
name: <dashboard name>
audience: [<role>, <role>]
panels:
  - name: <panel>
    type: timeseries | gauge | table | heatmap
    query: <PromQL / Langfuse / Datadog query>
    unit: <ms | % | req/s | usd>
    threshold:
      warn: <number>
      crit: <number>
```

Panels point at the Section-8 Telemetry attributes + Section-11 metrics
taxonomy (system / quality / safety / business).
