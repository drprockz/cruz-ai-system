import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

type Health = { postgresql?: string; redis?: string; qdrant?: string; ollama?: string };

export function SystemBar() {
  const { data } = useQuery<Health>({
    queryKey: ["health"],
    queryFn: () => api<Health>("/health"),
    refetchInterval: 10_000,
  });
  const allGreen =
    data &&
    Object.values(data).every(
      (v) =>
        v === "connected" ||
        v === "reachable" ||
        (v && typeof v === "object" && (v as Record<string, string>).status !== "error"),
    );
  return (
    <div className="flex items-center gap-3 h-10 px-4 border-b bg-zinc-950/80 text-xs text-zinc-400">
      <span className={allGreen ? "text-green-500" : "text-amber-500"}>●</span>
      <span className="font-medium text-zinc-100">CRUZ</span>
      <span>{allGreen ? "all systems online" : "degraded"}</span>
      <span className="ml-auto">{new Date().toLocaleTimeString()}</span>
    </div>
  );
}
