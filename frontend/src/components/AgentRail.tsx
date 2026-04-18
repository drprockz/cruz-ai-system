import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const AGENTS = [
  "cruz", "forge", "echo", "reach", "pm", "catch",
  "qt", "sentinel", "titan", "mark", "raw", "pulse",
];

type AgentStatus = Record<string, { status: string; last_run?: string }>;

export function AgentRail() {
  const { data } = useQuery<AgentStatus>({
    queryKey: ["agents"],
    queryFn: () => api<AgentStatus>("/agents/status"),
    refetchInterval: 5_000,
  });
  return (
    <div className="w-48 border-r bg-zinc-950/50 p-3">
      <div className="text-[10px] uppercase text-zinc-500 mb-2 tracking-wider">
        12 Agents
      </div>
      <ul className="space-y-1 text-xs">
        {AGENTS.map((a) => {
          const status = data?.[a]?.status ?? "idle";
          const dot =
            status === "running"
              ? "bg-amber-500"
              : status === "error"
                ? "bg-red-500"
                : "bg-green-500";
          return (
            <li key={a} className="flex items-center gap-2 text-zinc-300">
              <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
              <span className="lowercase">{a}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
