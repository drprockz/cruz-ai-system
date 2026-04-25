import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  Calendar,
  Mail,
  GitPullRequest,
  Rocket,
  MessageSquareText,
  Coins,
  CircleDollarSign,
  Clock3,
  Activity,
  AlarmClock,
} from "lucide-react";
import type { ReactNode } from "react";

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

// ─── Reusable card primitives ───────────────────────────────

function Card({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-white/5 bg-black/30 backdrop-blur-sm p-4 flex flex-col gap-3">
      {children}
    </div>
  );
}

function CardTitle({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-zinc-400">
      <span className="text-cyan-300/80">{icon}</span>
      <span className="font-semibold">{title}</span>
    </div>
  );
}

function Stat({
  label,
  value,
  icon,
}: {
  label: string;
  value: ReactNode;
  icon: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/5 flex items-center justify-center text-zinc-400">
        {icon}
      </div>
      <div className="flex flex-col">
        <span className="text-[11px] uppercase tracking-wide text-zinc-500">
          {label}
        </span>
        <span className="text-lg font-semibold text-zinc-100 tabular-nums">
          {value}
        </span>
      </div>
    </div>
  );
}

function HealthRow({ svc, state }: { svc: string; state: ServiceState }) {
  const ok = state === "healthy";
  return (
    <div className="flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-white/5 transition-colors">
      <span className="text-zinc-300 text-sm capitalize">
        {svc.replace("_", " ")}
      </span>
      <span
        className={
          "inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full border " +
          (ok
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
            : "bg-rose-500/10 border-rose-500/30 text-rose-300")
        }
      >
        <span
          className={
            "w-1.5 h-1.5 rounded-full " +
            (ok ? "bg-emerald-400" : "bg-rose-400")
          }
        />
        {state}
      </span>
    </div>
  );
}

// ─── Skeleton ────────────────────────────────────────────────

function DashboardSkeleton() {
  return (
    <div className="h-full overflow-y-auto p-4 grid grid-cols-1 md:grid-cols-2 gap-4 content-start">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-white/5 bg-black/30 p-4 h-40 relative overflow-hidden"
        >
          <div className="absolute inset-0 animate-shimmer" />
        </div>
      ))}
    </div>
  );
}

// ─── DashboardTab ───────────────────────────────────────────

export function DashboardTab() {
  const { data, isLoading } = useQuery<DashboardResponse>({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardResponse>("/dashboard"),
    refetchInterval: 10_000,
  });

  if (isLoading || !data) return <DashboardSkeleton />;

  const { today, metrics, system_health, upcoming } = data;

  return (
    <div className="h-full overflow-y-auto p-4 grid grid-cols-1 md:grid-cols-2 gap-4 content-start">
      <Card>
        <CardTitle icon={<Calendar size={14} />} title="Today" />
        <div className="grid grid-cols-2 gap-3">
          <Stat
            label="Calendar events"
            value={today.calendar_events.length}
            icon={<Calendar size={14} />}
          />
          <Stat
            label="Unread emails"
            value={today.unread_emails}
            icon={<Mail size={14} />}
          />
          <Stat
            label="Open PRs"
            value={today.open_prs}
            icon={<GitPullRequest size={14} />}
          />
          <Stat
            label="Deploys today"
            value={today.deploys_today}
            icon={<Rocket size={14} />}
          />
        </div>
      </Card>

      <Card>
        <CardTitle icon={<Activity size={14} />} title="Today's metrics" />
        <div className="grid grid-cols-2 gap-3">
          <Stat
            label="Turns"
            value={metrics.turns_today}
            icon={<MessageSquareText size={14} />}
          />
          <Stat
            label="Tokens"
            value={metrics.tokens_today.toLocaleString()}
            icon={<Coins size={14} />}
          />
          <Stat
            label="Est. cost"
            value={`$${metrics.estimated_cost_usd.toFixed(2)}`}
            icon={<CircleDollarSign size={14} />}
          />
          <Stat
            label="Time saved"
            value={`${metrics.estimated_time_saved_hours}h`}
            icon={<Clock3 size={14} />}
          />
        </div>
      </Card>

      <Card>
        <CardTitle icon={<Activity size={14} />} title="System health" />
        <div className="grid grid-cols-1 divide-y divide-white/5">
          {(Object.entries(system_health) as [string, ServiceState][]).map(
            ([svc, state]) => (
              <HealthRow key={svc} svc={svc} state={state} />
            ),
          )}
        </div>
      </Card>

      <Card>
        <CardTitle icon={<AlarmClock size={14} />} title="Upcoming" />
        {upcoming.length === 0 ? (
          <p className="text-zinc-500 text-sm py-4 text-center">
            No scheduled tasks.
          </p>
        ) : (
          <div className="space-y-1">
            {upcoming.map((item) => (
              <div
                key={`${item.agent}-${item.scheduled_at}`}
                className="flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-white/5 transition-colors"
              >
                <span className="text-zinc-300 text-sm">{item.label}</span>
                <span className="text-zinc-500 text-xs tabular-nums">
                  {item.scheduled_at}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
