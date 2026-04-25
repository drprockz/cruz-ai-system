import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Link } from "react-router-dom";
import { AlertTriangle, Newspaper, FlaskConical, CheckCircle2 } from "lucide-react";

type Approval = { id: string; agent: string; action: string };

export function PendingRail() {
  const { data } = useQuery<Approval[]>({
    queryKey: ["approvals", "pending"],
    queryFn: () => api<Approval[]>("/approvals?state=pending"),
    refetchInterval: 4_000,
  });
  const items = data ?? [];

  return (
    <aside className="w-60 shrink-0 border-l border-white/5 bg-black/20 backdrop-blur-sm p-3 space-y-6">
      <section>
        <div className="text-[10px] uppercase text-zinc-500 mb-2 tracking-widest px-1">
          Pending
        </div>
        {items.length === 0 ? (
          <div className="flex items-center gap-2 text-xs text-zinc-500 px-2">
            <CheckCircle2 size={12} className="text-emerald-400/70" />
            No approvals
          </div>
        ) : (
          <ul className="space-y-1">
            {items.slice(0, 5).map((a) => (
              <li key={a.id}>
                <Link
                  to={`/tab/approvals/${a.id}`}
                  className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-amber-500/5 border border-amber-500/20 hover:bg-amber-500/10 transition-colors"
                >
                  <AlertTriangle size={12} className="text-amber-400 shrink-0" />
                  <span className="text-xs text-amber-100 truncate">
                    <span className="font-semibold uppercase">{a.agent}</span>{" "}
                    · {a.action}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section>
        <div className="text-[10px] uppercase text-zinc-500 mb-2 tracking-widest px-1">
          Upcoming
        </div>
        <ul className="space-y-1">
          <li className="flex items-center gap-2 px-2 py-1.5 text-xs text-zinc-300">
            <Newspaper size={12} className="text-cyan-300/80" />
            <span>Brief</span>
            <span className="ml-auto text-zinc-500 tabular-nums">6 AM</span>
          </li>
          <li className="flex items-center gap-2 px-2 py-1.5 text-xs text-zinc-300">
            <FlaskConical size={12} className="text-violet-300/80" />
            <span>Research</span>
            <span className="ml-auto text-zinc-500 tabular-nums">3 AM</span>
          </li>
        </ul>
      </section>
    </aside>
  );
}
