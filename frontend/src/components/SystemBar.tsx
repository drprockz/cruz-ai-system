import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { api } from "@/lib/api";
import { useDevice } from "@/lib/breakpoints";

type Health = {
  postgresql?: string;
  redis?: string;
  qdrant?: string;
  ollama?: unknown;
};

function svcState(v: unknown): "up" | "down" {
  if (v === "connected" || v === "reachable") return "up";
  if (v && typeof v === "object") {
    const obj = v as Record<string, unknown>;
    if (obj.status === "reachable" || obj.status === "connected") return "up";
  }
  return "down";
}

const TABS = [
  { to: "/tab/conversation", label: "Conversation" },
  { to: "/tab/dashboard", label: "Dashboard" },
  { to: "/tab/events", label: "Events" },
  { to: "/tab/approvals", label: "Approvals" },
] as const;

export function SystemBar() {
  const device = useDevice();
  const { pathname } = useLocation();
  const { data } = useQuery<Health>({
    queryKey: ["health"],
    queryFn: () => api<Health>("/health"),
    refetchInterval: 10_000,
  });

  // Critical services: Postgres + Redis. Qdrant-down is informational,
  // not a "degraded" alarm (CRUZ works without semantic memory).
  const pgOk = svcState(data?.postgresql) === "up";
  const redisOk = svcState(data?.redis) === "up";
  const qdrantOk = svcState(data?.qdrant) === "up";
  const ollamaOk = svcState(data?.ollama) === "up";

  const critical = pgOk && redisOk;
  const color = critical ? (qdrantOk && ollamaOk ? "text-green-500" : "text-yellow-400") : "text-red-500";
  const label = critical
    ? qdrantOk && ollamaOk
      ? "all systems online"
      : `degraded (${!qdrantOk ? "qdrant" : ""}${!qdrantOk && !ollamaOk ? "+" : ""}${!ollamaOk ? "ollama" : ""} down — non-fatal)`
    : "CRITICAL";

  return (
    <div className="flex items-center gap-3 h-10 px-4 border-b border-zinc-800 bg-zinc-950/80 text-xs text-zinc-400">
      <span className={color}>●</span>
      <span className="font-medium text-zinc-100">CRUZ</span>
      <span className="truncate">{label}</span>

      {device === "desktop" && (
        <nav className="ml-8 flex items-center gap-1">
          {TABS.map((t) => {
            const active = pathname === t.to;
            return (
              <Link
                key={t.to}
                to={t.to}
                className={
                  "px-3 py-1 rounded-md text-xs font-medium transition-colors " +
                  (active
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900")
                }
              >
                {t.label}
              </Link>
            );
          })}
        </nav>
      )}

      <span className="ml-auto font-mono">{new Date().toLocaleTimeString()}</span>
    </div>
  );
}
