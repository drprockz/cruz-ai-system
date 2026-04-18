import { useMemo, useState } from "react";
import { useEventStream, type LogEvent } from "@/hooks/useEventStream";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

function statusClass(status: string): string {
  if (status === "success") return "text-green-500";
  if (status === "error") return "text-red-500";
  return "text-amber-500";
}

function EventRow({ event: e }: { event: LogEvent }) {
  return (
    <div className="flex gap-3 py-0.5 text-[11px] font-mono leading-relaxed">
      <span className="text-zinc-600 w-20 shrink-0">
        {new Date(e.created_at).toLocaleTimeString()}
      </span>
      <span className="text-blue-400 w-16 shrink-0">{e.agent}</span>
      <span className="text-zinc-400 w-24 shrink-0 truncate">{e.action}</span>
      <span className={`w-16 shrink-0 ${statusClass(e.status)}`}>{e.status}</span>
      <span className="text-zinc-600">{e.duration_ms}ms · {e.tokens_used}tk</span>
    </div>
  );
}

export function EventsTab() {
  const events = useEventStream(200);
  const [filter, setFilter] = useState("");

  const filtered = useMemo<LogEvent[]>(() => {
    if (!filter.trim()) return events;
    const q = filter.toLowerCase();
    return events.filter(
      (e) =>
        e.agent.toLowerCase().includes(q) ||
        e.action.toLowerCase().includes(q) ||
        e.trace_id.toLowerCase().includes(q) ||
        e.status.toLowerCase().includes(q),
    );
  }, [events, filter]);

  return (
    <div className="h-full flex flex-col gap-3 p-4">
      <div className="flex items-center gap-3">
        <Input
          placeholder="Filter by agent / action / trace_id / status"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-md bg-zinc-900 border-zinc-800 text-sm"
        />
        <span className="text-xs text-zinc-500 shrink-0">
          {filtered.length} events
        </span>
      </div>
      <ScrollArea className="flex-1 rounded-md border border-zinc-800 bg-zinc-900/50">
        <div className="p-3">
          {filtered.length === 0 && (
            <p className="text-zinc-500 text-xs py-4 text-center">
              {events.length === 0
                ? "Waiting for agent events…"
                : "No events match the filter."}
            </p>
          )}
          {filtered.map((e) => (
            <EventRow key={e.id} event={e} />
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
