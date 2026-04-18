import { SystemBar } from "./SystemBar";
import { AgentRail } from "./AgentRail";
import { PendingRail } from "./PendingRail";
import { NavDrawer } from "./NavDrawer";
import { useDevice } from "@/lib/breakpoints";
import { useGlobalKeymap } from "@/lib/keymap";
import type { ReactNode } from "react";

export function Layout({ children }: { children: ReactNode }) {
  const d = useDevice();
  useGlobalKeymap();
  const showDrawer = d === "phone" || d === "tablet";

  return (
    <div
      className="h-dvh flex flex-col text-zinc-100 relative overflow-hidden"
      style={{ background: "var(--color-cruz-bg)" }}
    >
      {/* Ambient gradient texture — low-contrast, non-distracting */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(ellipse 80% 50% at 50% -10%, oklch(0.3 0.03 210 / 0.4), transparent 70%), radial-gradient(ellipse 60% 40% at 90% 110%, oklch(0.28 0.08 290 / 0.25), transparent 70%)",
        }}
      />
      <div className="relative z-10 flex flex-col h-full">
        <SystemBar />
        <div className="flex-1 flex overflow-hidden">
          {d === "desktop" && <AgentRail />}
          <main className="flex-1 overflow-hidden">{children}</main>
          {d === "desktop" && <PendingRail />}
        </div>
        {showDrawer && <NavDrawer />}
      </div>
    </div>
  );
}
