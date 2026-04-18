import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Link } from "react-router-dom";

type Approval = { id: string; agent: string; action: string };

export function PendingRail() {
  const { data } = useQuery<Approval[]>({
    queryKey: ["approvals", "pending"],
    queryFn: () => api<Approval[]>("/approvals?state=pending"),
    refetchInterval: 4_000,
  });
  return (
    <div className="w-52 border-l bg-zinc-950/50 p-3">
      <div className="text-[10px] uppercase text-zinc-500 mb-2 tracking-wider">
        Pending
      </div>
      <ul className="space-y-2 text-xs">
        {!data?.length && <li className="text-zinc-500">No approvals</li>}
        {data?.slice(0, 5).map((a) => (
          <li key={a.id}>
            <Link
              to={`/tab/approvals/${a.id}`}
              className="block text-amber-400 hover:underline"
            >
              ⚠ {a.agent} · {a.action}
            </Link>
          </li>
        ))}
      </ul>
      <div className="text-[10px] uppercase text-zinc-500 mt-6 mb-2 tracking-wider">
        Upcoming
      </div>
      <ul className="space-y-1 text-xs text-zinc-400">
        <li>📰 Brief · 6 AM</li>
        <li>🔬 Research · 3 AM</li>
      </ul>
    </div>
  );
}
