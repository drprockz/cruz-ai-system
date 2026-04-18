/**
 * NavDrawer — hamburger Sheet for phone/tablet navigation.
 * Renders a Menu icon button that opens a right-side Sheet
 * containing links to all 4 tabs. Used when the side rails are hidden.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { Menu } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetClose,
} from "@/components/ui/sheet";

const NAV_ITEMS = [
  { to: "/tab/conversation", label: "Conversation", icon: "💬" },
  { to: "/tab/dashboard",    label: "Dashboard",    icon: "📊" },
  { to: "/tab/events",       label: "Events",       icon: "📡" },
  { to: "/tab/approvals",    label: "Approvals",    icon: "✅" },
];

export function NavDrawer() {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      {/* Trigger — floating button at top-right */}
      <button
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
        className="fixed top-2 right-3 z-40 flex h-8 w-8 items-center justify-center rounded-md bg-zinc-900 border border-zinc-700 text-zinc-300 hover:text-zinc-100 hover:bg-zinc-800"
      >
        <Menu size={16} />
      </button>

      <SheetContent side="right" className="bg-zinc-950 border-zinc-800 w-64">
        <SheetHeader>
          <SheetTitle className="text-zinc-100 text-sm font-semibold tracking-wider uppercase">
            CRUZ
          </SheetTitle>
        </SheetHeader>

        <nav className="mt-6 flex flex-col gap-1">
          {NAV_ITEMS.map(({ to, label, icon }) => (
            <SheetClose asChild key={to}>
              <Link
                to={to}
                className="flex items-center gap-3 rounded-md px-3 py-2.5 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 transition-colors"
              >
                <span className="text-base">{icon}</span>
                {label}
              </Link>
            </SheetClose>
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
