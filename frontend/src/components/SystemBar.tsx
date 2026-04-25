import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { Waves } from "lucide-react";
import { useEffect, useState } from "react";
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

function useLiveClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function SystemBar() {
  const device = useDevice();
  const { pathname } = useLocation();
  const clock = useLiveClock();
  const { data } = useQuery<Health>({
    queryKey: ["health"],
    queryFn: () => api<Health>("/health"),
    refetchInterval: 10_000,
  });

  const pgOk = svcState(data?.postgresql) === "up";
  const redisOk = svcState(data?.redis) === "up";
  const qdrantOk = svcState(data?.qdrant) === "up";
  const ollamaOk = svcState(data?.ollama) === "up";

  const critical = pgOk && redisOk;
  const allGreen = critical && qdrantOk && ollamaOk;
  const dotColor = !critical
    ? "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.7)]"
    : allGreen
      ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
      : "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]";

  const degradedReasons: string[] = [];
  if (!qdrantOk) degradedReasons.push("qdrant");
  if (!ollamaOk) degradedReasons.push("ollama");

  return (
    <div className="flex items-center gap-3 h-11 px-4 border-b border-white/5 bg-black/60 backdrop-blur-xl text-xs text-zinc-400">
      <span className="flex items-center gap-2">
        <span className={`inline-block w-2 h-2 rounded-full ${dotColor}`} />
        <span className="font-semibold tracking-wide text-zinc-100">CRUZ</span>
      </span>

      {critical ? (
        allGreen ? (
          <span className="text-emerald-300/80">all systems online</span>
        ) : (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-200/90">
            <span className="w-1 h-1 rounded-full bg-amber-400" />
            {degradedReasons.join(" · ")} offline · non-fatal
          </span>
        )
      ) : (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-500/10 border border-rose-500/30 text-rose-200 font-medium">
          CRITICAL
        </span>
      )}

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
                    ? "bg-white/10 text-zinc-100"
                    : "text-zinc-400 hover:text-zinc-100 hover:bg-white/5")
                }
              >
                {t.label}
              </Link>
            );
          })}
        </nav>
      )}

      <div className="ml-auto flex items-center gap-3">
        <Link
          to="/voice"
          className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-200 hover:bg-cyan-500/20 hover:text-cyan-100 transition-colors"
          title="Voice mode (v)"
        >
          <Waves size={12} />
          <span className="hidden sm:inline">Voice</span>
        </Link>
        <span className="font-mono text-zinc-500 tabular-nums">
          {clock.toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
}
