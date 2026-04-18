import { useEffect, useState } from "react";
import { sseUrl } from "@/lib/api";

export interface LogEvent {
  id: number;
  trace_id: string;
  agent: string;
  action: string;
  status: string;
  tokens_used: number;
  duration_ms: number;
  created_at: string;
}

/**
 * Opens an SSE connection to /events and maintains a rolling buffer of
 * up to `max` log events. On mount, replays recent rows; on each `log`
 * server-sent event, appends to the list.
 */
export function useEventStream(max = 200): LogEvent[] {
  const [events, setEvents] = useState<LogEvent[]>([]);

  useEffect(() => {
    const es = new EventSource(sseUrl("/events"));

    es.addEventListener("replay", (e) => {
      const rows: LogEvent[] = JSON.parse((e as MessageEvent).data);
      setEvents(rows.slice(-max));
    });

    es.addEventListener("log", (e) => {
      const row: LogEvent = JSON.parse((e as MessageEvent).data);
      setEvents((prev) => [...prev.slice(-(max - 1)), row]);
    });

    es.onerror = () => {
      // Browser will auto-reconnect on transient failures; nothing to do.
    };

    return () => es.close();
  }, [max]);

  return events;
}
