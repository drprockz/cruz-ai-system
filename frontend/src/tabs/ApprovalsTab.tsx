import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Check, X } from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ApprovalRow {
  id: string;
  trace_id: string;
  agent: string;
  action: string;
  payload: Record<string, unknown>;
  state: string;
  requested_at: string;
  responded_at: string | null;
  expires_at: string;
}

// ─── Approval card ────────────────────────────────────────────────────────────

function ApprovalCard({ row }: { row: ApprovalRow }) {
  const qc = useQueryClient();

  const approve = useMutation({
    mutationFn: () => api<{ state: string }>(`/approvals/${row.id}/approve`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["approvals"] }),
  });

  const deny = useMutation({
    mutationFn: () => api<{ state: string }>(`/approvals/${row.id}/deny`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["approvals"] }),
  });

  const busy = approve.isPending || deny.isPending;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="rounded-xl border border-amber-500/20 bg-gradient-to-b from-amber-500/5 to-transparent backdrop-blur-sm p-4 space-y-3"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-semibold uppercase tracking-wide text-amber-300">
              {row.agent}
            </span>
            <span className="text-zinc-500">→</span>
            <span className="text-zinc-200 font-medium">{row.action}</span>
          </div>
          <p
            className="text-[11px] text-zinc-500 font-mono truncate mt-1"
            title={row.trace_id}
          >
            trace: {row.trace_id}
          </p>
        </div>
        <span className="shrink-0 inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-200">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
          pending
        </span>
      </div>
      {Object.keys(row.payload).length > 0 && (
        <pre className="text-[11px] bg-black/40 border border-white/5 rounded-lg p-3 overflow-x-auto text-zinc-400 font-mono">
          {JSON.stringify(row.payload, null, 2)}
        </pre>
      )}
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-zinc-500 tabular-nums">
          Requested {new Date(row.requested_at).toLocaleString()}
        </span>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="destructive"
            disabled={busy}
            onClick={() => deny.mutate()}
            className="gap-1"
          >
            <X size={14} /> Deny
          </Button>
          <Button
            size="sm"
            disabled={busy}
            onClick={() => approve.mutate()}
            className="bg-emerald-500 hover:bg-emerald-400 text-black font-semibold gap-1"
          >
            <Check size={14} /> Approve
          </Button>
        </div>
      </div>
    </motion.div>
  );
}

// ─── ApprovalsTab ─────────────────────────────────────────────────────────────

export function ApprovalsTab() {
  const { data, isLoading } = useQuery<ApprovalRow[]>({
    queryKey: ["approvals"],
    queryFn: () => api<ApprovalRow[]>("/approvals?state=pending"),
    refetchInterval: 5_000,
  });

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto p-4 space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-white/5 bg-black/30 h-32 relative overflow-hidden"
          >
            <div className="absolute inset-0 animate-shimmer" />
          </div>
        ))}
      </div>
    );
  }

  const items = data ?? [];

  return (
    <div className="h-full overflow-y-auto p-4 space-y-3">
      <div className="flex items-center gap-3 px-1">
        <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">
          Pending approvals
        </h2>
        {items.length > 0 && (
          <span className="inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded-full bg-amber-500/20 border border-amber-500/30 text-amber-200 text-[11px] font-semibold">
            {items.length}
          </span>
        )}
      </div>
      {items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center gap-3">
          <div className="w-14 h-14 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-300">
            <CheckCircle2 size={24} />
          </div>
          <div>
            <div className="text-zinc-300 text-sm font-medium">You're clear</div>
            <div className="text-zinc-500 text-xs mt-1">
              Nothing needs your approval right now.
            </div>
          </div>
        </div>
      ) : (
        items.map((row) => <ApprovalCard key={row.id} row={row} />)
      )}
    </div>
  );
}
