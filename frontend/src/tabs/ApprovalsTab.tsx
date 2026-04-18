import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

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
    <Card className="border-amber-900/40">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm font-semibold">
            <span className="text-amber-400 uppercase">{row.agent}</span>
            <span className="text-zinc-400 font-normal"> · {row.action}</span>
          </CardTitle>
          <Badge variant="outline" className="text-amber-400 border-amber-700 shrink-0">
            pending
          </Badge>
        </div>
        <p className="text-[11px] text-zinc-600 font-mono truncate" title={row.trace_id}>
          trace: {row.trace_id}
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {Object.keys(row.payload).length > 0 && (
          <pre className="text-[11px] bg-zinc-900 rounded p-2 overflow-x-auto text-zinc-400">
            {JSON.stringify(row.payload, null, 2)}
          </pre>
        )}
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-zinc-600">
            Requested {new Date(row.requested_at).toLocaleString()}
          </span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="destructive"
              disabled={busy}
              onClick={() => deny.mutate()}
            >
              Deny
            </Button>
            <Button
              size="sm"
              disabled={busy}
              onClick={() => approve.mutate()}
              className="bg-green-600 hover:bg-green-700 text-white"
            >
              Approve
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
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
    return <div className="p-6 text-zinc-500 text-sm">Loading approvals…</div>;
  }

  const items = data ?? [];

  return (
    <div className="h-full overflow-y-auto p-4 space-y-3">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-semibold text-zinc-200">Pending Approvals</h2>
        {items.length > 0 && (
          <Badge variant="destructive">{items.length}</Badge>
        )}
      </div>
      {items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-zinc-500 gap-2">
          <span className="text-2xl">✓</span>
          <p className="text-sm">No pending approvals.</p>
        </div>
      )}
      {items.map((row) => (
        <ApprovalCard key={row.id} row={row} />
      ))}
    </div>
  );
}
