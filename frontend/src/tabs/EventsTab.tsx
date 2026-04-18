import { useMemo, useState } from "react";
import { useEventStream, type LogEvent } from "@/hooks/useEventStream";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

function statusClass(status: string): string {
  if (status === "success") return "text-emerald-400";
  if (status === "error") return "text-rose-400";
  return "text-amber-400";
}

function statusDot(status: string): string {
  if (status === "success") return "bg-emerald-400";
  if (status === "error") return "bg-rose-400";
  return "bg-amber-400";
}

function EventRow({ event: e }: { event: LogEvent }) {
  return (
    <div className="group flex items-center gap-3 py-1 px-2 text-[11px] font-mono leading-relaxed rounded-md hover:bg-white/5 transition-colors">
      <span
        className={`inline-block w-1.5 h-1.5 rounded-full ${statusDot(e.status)}`}
        aria-hidden
      />
      <span className="text-zinc-500 w-20 shrink-0 tabular-nums">
        {new Date(e.created_at).toLocaleTimeString()}
      </span>
      <span className="text-cyan-300/80 w-16 shrink-0 uppercase tracking-wide">
        {e.agent}
      </span>
      <span className="text-zinc-300 flex-1 truncate">{e.action}</span>
      <span className={`shrink-0 ${statusClass(e.status)}`}>{e.status}</span>
      <span className="text-zinc-500 shrink-0 tabular-nums">
        {e.duration_ms}ms · {e.tokens_used}tk
      </span>
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
          className="max-w-md bg-white/5 border-white/10 text-sm placeholder:text-zinc-600 focus:border-cyan-500/50"
        />
        <span className="text-xs text-zinc-500 shrink-0 tabular-nums">
          {filtered.length} / {events.length} events
        </span>
      </div>
      <ScrollArea className="flex-1 rounded-lg border border-white/5 bg-black/30 backdrop-blur-sm">
        <div className="p-2">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <div className="w-14 h-14 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
              </div>
              <div className="text-zinc-400 text-sm text-center">
                {events.length === 0 ? (
                  <>
                    <div className="font-medium">No agent activity yet</div>
                    <div className="text-xs text-zinc-500 mt-1">
                      CRUZ will log here when any agent runs.
                    </div>
                  </>
                ) : (
                  <>
                    <div className="font-medium">Nothing matches that filter</div>
                    <div className="text-xs text-zinc-500 mt-1">
                      Try a broader term or clear the search.
                    </div>
                  </>
                )}
              </div>
            </div>
          ) : (
            filtered.map((e) => <EventRow key={e.id} event={e} />)
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
