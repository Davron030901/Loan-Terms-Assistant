"use client";

import { Check, PenLine, Search, ShieldAlert, ShieldCheck, X } from "lucide-react";
import type { StageState } from "@/hooks/useChat";
import type { TraceStage } from "@/lib/types";
import { cn, formatMs } from "@/lib/utils";

const ROWS: { key: TraceStage; label: string; icon: typeof Search; gate: boolean }[] = [
  { key: "scope_guard", label: "Scope guard", icon: ShieldAlert, gate: true },
  { key: "retrieval", label: "Retrieval", icon: Search, gate: false },
  { key: "answer", label: "Answer", icon: PenLine, gate: false },
  { key: "grounding_guard", label: "Grounding guard", icon: ShieldCheck, gate: true },
];

function summarise(key: TraceStage, data: Record<string, unknown>): string {
  switch (key) {
    case "scope_guard":
      return data.verdict === "ALLOW"
        ? "ALLOW"
        : `REFUSE${data.layer ? ` · ${data.layer} layer` : ""}`;
    case "retrieval": {
      const pages = (data.pages as number[] | undefined) ?? [];
      const unique = [...new Set(pages)].slice(0, 4).join(", ");
      return `${data.chunks ?? 0} clauses · top ${Number(data.top_score ?? 0).toFixed(2)}${
        unique ? ` · p. ${unique}` : ""
      }`;
    }
    case "answer":
      return `${data.model ?? "model"}${data.repaired ? " · repaired" : ""}`;
    case "grounding_guard":
      return `${data.verdict ?? "—"}${data.method && data.method !== "none" ? ` · ${data.method}` : ""}`;
    default:
      return "—";
  }
}

function isBad(key: TraceStage, data: Record<string, unknown>) {
  if (key === "scope_guard") return data.verdict === "REFUSE";
  if (key === "grounding_guard") return data.verdict === "NOT_GROUNDED";
  if (key === "retrieval") return data.chunks === 0;
  return false;
}

export function TracePanel({ stages, busy }: { stages: StageState; busy: boolean }) {
  const total = Object.values(stages).reduce<number>(
    (sum, stage) => sum + (Number((stage as Record<string, unknown> | undefined)?.latency_ms) || 0),
    0,
  );

  return (
    <div className="card p-4">
      <header className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">Agent trace</h2>
        <span className="font-mono text-[0.68rem] text-muted">
          {total > 0 ? formatMs(total) : busy ? "running…" : "idle"}
        </span>
      </header>

      <ol className="relative space-y-1">
        {ROWS.map((row, index) => {
          const data = (stages[row.key] ?? {}) as Record<string, unknown>;
          const status = (data.status as string) ?? "idle";
          const bad = status === "done" && isBad(row.key, data);
          const Icon = row.icon;

          return (
            <li key={row.key} className="relative flex gap-3 pb-1">
              {index < ROWS.length - 1 && (
                <span
                  aria-hidden
                  className={cn(
                    "absolute left-[13px] top-8 h-[calc(100%-1rem)] w-px transition-colors",
                    status === "done" ? "bg-brand-500/35" : "bg-[color:var(--border-hairline)]",
                  )}
                />
              )}

              <span
                className={cn(
                  "relative z-10 mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition",
                  status === "idle" && "border-hairline text-muted",
                  status === "running" && "border-brand-500/50 bg-brand-500/10 text-brand-500",
                  status === "done" &&
                    !bad &&
                    "border-grounded-500/45 bg-grounded-500/10 text-grounded-500",
                  status === "done" && bad && "border-blocked-500/45 bg-blocked-500/10 text-blocked-500",
                )}
              >
                {status === "done" ? (
                  bad ? (
                    <X className="h-3.5 w-3.5" aria-hidden />
                  ) : (
                    <Check className="h-3.5 w-3.5" aria-hidden />
                  )
                ) : (
                  <Icon className={cn("h-3.5 w-3.5", status === "running" && "pulse-dot")} aria-hidden />
                )}
              </span>

              <div className="min-w-0 flex-1 pt-0.5">
                <div className="flex items-baseline justify-between gap-2">
                  <span
                    className={cn(
                      "text-[0.8rem] font-medium",
                      row.gate && "text-refused-600 dark:text-refused-400",
                    )}
                  >
                    {row.label}
                    {row.gate && <span className="ml-1 text-[0.62rem] uppercase opacity-70">gate</span>}
                  </span>
                  {status === "done" && (
                    <span className="shrink-0 font-mono text-[0.65rem] text-muted">
                      {formatMs(Number(data.latency_ms) || 0)}
                    </span>
                  )}
                </div>
                <p className="truncate font-mono text-[0.68rem] text-muted">
                  {status === "idle"
                    ? "waiting"
                    : status === "running"
                      ? "running…"
                      : summarise(row.key, data)}
                </p>
              </div>
            </li>
          );
        })}
      </ol>

      <p className="mt-3 border-t border-hairline pt-3 text-[0.68rem] leading-relaxed text-muted">
        Both gates run on the server. Neither can be disabled from this page.
      </p>
    </div>
  );
}
