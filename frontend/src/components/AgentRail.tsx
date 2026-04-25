import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const AGENTS = [
  "cruz", "forge", "echo", "reach", "pm", "catch",
  "qt", "sentinel", "titan", "mark", "raw", "pulse",
];

type AgentStatus = Record<string, { status: string; last_run?: string }>;

const STATUS_STYLES: Record<
  string,
  { dot: string; label: string }
> = {
  running: { dot: "bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.6)]", label: "running" },
  error: { dot: "bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.6)]", label: "error" },
  idle: { dot: "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.3)]", label: "ready" },
};

export function AgentRail() {
  const { data } = useQuery<AgentStatus>({
    queryKey: ["agents"],
    queryFn: () => api<AgentStatus>("/agents/status"),
    refetchInterval: 5_000,
  });
  return (
    <aside className="w-52 shrink-0 border-r border-white/5 bg-black/20 backdrop-blur-sm p-3">
      <div className="text-[10px] uppercase text-zinc-500 mb-3 tracking-widest px-1">
        12 Agents
      </div>
      <ul className="space-y-0.5">
        {AGENTS.map((a) => {
          const status = data?.[a]?.status ?? "idle";
          const style = STATUS_STYLES[status] ?? STATUS_STYLES.idle;
          return (
            <li
              key={a}
              className="group flex items-center justify-between px-2 py-1.5 rounded-md hover:bg-white/5 transition-colors"
            >
              <span className="flex items-center gap-2 text-xs text-zinc-200">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${style.dot}`}
                  aria-hidden
                />
                <span className="lowercase tracking-wide">{a}</span>
              </span>
              <span className="text-[10px] text-zinc-600 group-hover:text-zinc-400 transition-colors">
                {style.label}
              </span>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
