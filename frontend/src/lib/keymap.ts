/**
 * Global keyboard shortcuts.
 *
 *   1-4 → switch tabs (Conversation, Dashboard, Events, Approvals)
 *   v   → enter voice mode
 *   Esc → back to Conversation from any non-tab route
 *
 * No shortcuts fire while an input/textarea/contentEditable is focused.
 */
import { useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";

const TAB_KEYS: Record<string, string> = {
  "1": "/tab/conversation",
  "2": "/tab/dashboard",
  "3": "/tab/events",
  "4": "/tab/approvals",
};

export function useGlobalKeymap() {
  const nav = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Skip when user is typing.
      const t = e.target as HTMLElement | null;
      if (!t) return;
      const tag = t.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        (t as HTMLElement).isContentEditable
      ) {
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (TAB_KEYS[e.key]) {
        e.preventDefault();
        nav(TAB_KEYS[e.key]);
        return;
      }
      if (e.key.toLowerCase() === "v" && !pathname.startsWith("/voice")) {
        e.preventDefault();
        nav("/voice");
        return;
      }
      if (e.key === "Escape" && pathname.startsWith("/voice")) {
        // Voice mode has its own handler; don't double-fire.
        return;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nav, pathname]);
}
