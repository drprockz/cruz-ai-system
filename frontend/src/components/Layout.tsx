import { SystemBar } from "./SystemBar";
import { AgentRail } from "./AgentRail";
import { PendingRail } from "./PendingRail";
import { useDevice } from "@/lib/breakpoints";
import type { ReactNode } from "react";

export function Layout({ children }: { children: ReactNode }) {
  const d = useDevice();
  return (
    <div className="h-dvh flex flex-col bg-zinc-950 text-zinc-100">
      <SystemBar />
      <div className="flex-1 flex overflow-hidden">
        {d === "desktop" && <AgentRail />}
        <main className="flex-1 overflow-hidden">{children}</main>
        {d === "desktop" && <PendingRail />}
      </div>
    </div>
  );
}
