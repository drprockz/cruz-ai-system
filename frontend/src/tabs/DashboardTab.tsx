import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// ─── API response types ───────────────────────────────────────────────────────

interface DashboardToday {
  calendar_events: unknown[];
  unread_emails: number;
  open_prs: number;
  deploys_today: number;
}

interface DashboardMetrics {
  turns_today: number;
  tokens_today: number;
  estimated_cost_usd: number;
  estimated_time_saved_hours: number;
}

type ServiceState = "healthy" | "degraded";

interface DashboardSystemHealth {
  deepgram: ServiceState;
  livekit: ServiceState;
  postgres: ServiceState;
  redis: ServiceState;
  qdrant: ServiceState;
  ollama: ServiceState;
  claude_api: ServiceState;
}

interface UpcomingItem {
  agent: string;
  scheduled_at: string;
  label: string;
}

interface DashboardResponse {
  today: DashboardToday;
  metrics: DashboardMetrics;
  system_health: DashboardSystemHealth;
  upcoming: UpcomingItem[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function HealthBadge({ state }: { state: ServiceState }) {
  return (
    <Badge
      variant={state === "healthy" ? "default" : "destructive"}
      className={state === "healthy" ? "bg-green-600 hover:bg-green-600" : undefined}
    >
      {state}
    </Badge>
  );
}

// ─── DashboardTab ─────────────────────────────────────────────────────────────

export function DashboardTab() {
  const { data, isLoading } = useQuery<DashboardResponse>({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardResponse>("/dashboard"),
    refetchInterval: 10_000,
  });

  if (isLoading || !data) {
    return <div className="p-6 text-zinc-500 text-sm">Loading dashboard…</div>;
  }

  const { today, metrics, system_health, upcoming } = data;

  return (
    <div className="h-full overflow-y-auto p-4 grid grid-cols-1 md:grid-cols-2 gap-4 content-start">
      {/* Today */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Today</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-zinc-500">Calendar events</p>
            <p className="font-semibold">{today.calendar_events.length}</p>
          </div>
          <div>
            <p className="text-zinc-500">Unread emails</p>
            <p className="font-semibold">{today.unread_emails}</p>
          </div>
          <div>
            <p className="text-zinc-500">Open PRs</p>
            <p className="font-semibold">{today.open_prs}</p>
          </div>
          <div>
            <p className="text-zinc-500">Deploys today</p>
            <p className="font-semibold">{today.deploys_today}</p>
          </div>
        </CardContent>
      </Card>

      {/* Metrics */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Metrics</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-zinc-500">Turns today</p>
            <p className="font-semibold">{metrics.turns_today}</p>
          </div>
          <div>
            <p className="text-zinc-500">Tokens</p>
            <p className="font-semibold">{metrics.tokens_today.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-zinc-500">Est. cost</p>
            <p className="font-semibold">${metrics.estimated_cost_usd.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-zinc-500">Time saved</p>
            <p className="font-semibold">{metrics.estimated_time_saved_hours}h</p>
          </div>
        </CardContent>
      </Card>

      {/* System Health */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">System Health</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-2 text-sm">
          {(Object.entries(system_health) as [string, ServiceState][]).map(([svc, state]) => (
            <div key={svc} className="flex items-center justify-between">
              <span className="text-zinc-400 capitalize">{svc.replace("_", " ")}</span>
              <HealthBadge state={state} />
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Upcoming */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Upcoming</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {upcoming.length === 0 && (
            <p className="text-zinc-500">No scheduled tasks.</p>
          )}
          {upcoming.map((item) => (
            <div key={item.agent} className="flex items-center justify-between">
              <span className="text-zinc-300">{item.label}</span>
              <span className="text-zinc-500 text-xs">{item.scheduled_at}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
