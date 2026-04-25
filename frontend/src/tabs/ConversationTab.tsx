import { useState } from "react";
import { useVoice } from "@/state/voiceStore";
import { Orb } from "@/components/Orb";
import { PTTButton } from "@/components/PTTButton";
import { useLiveKitRoom } from "@/hooks/useLiveKitRoom";
import { useDevice } from "@/lib/breakpoints";
import { Send } from "lucide-react";

export function ConversationTab() {
  const device = useDevice();
  const deviceId =
    device === "phone" ? "phone" : device === "tablet" ? "ipad" : "mac-web";

  // Singleton room across all consumers.
  useLiveKitRoom(deviceId);

  const transcript = useVoice((v) => v.transcript);
  const append = useVoice((v) => v.append);
  const setVoice = useVoice((v) => v.set);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function sendText() {
    const text = input.trim();
    if (!text || sending) return;
    setSending(true);
    append({ role: "user", text, ts: Date.now() });
    setInput("");
    setVoice({ state: "thinking" });
    try {
      const r = await fetch(`${import.meta.env.VITE_API_BASE ?? "/api"}/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command: text,
          conversation_id: sessionStorage.getItem("cruz:conversation_id"),
          device: "mac_web",
          stream: false,
        }),
      });
      if (r.ok) {
        const data = await r.json();
        const reply =
          typeof data.result === "string"
            ? data.result
            : JSON.stringify(data.result);
        append({ role: "cruz", text: reply, ts: Date.now() });
      } else {
        append({
          role: "tool",
          text: `HTTP ${r.status}: ${r.statusText}`,
          ts: Date.now(),
        });
      }
    } catch (exc) {
      append({ role: "tool", text: `error: ${String(exc)}`, ts: Date.now() });
    } finally {
      setVoice({ state: "idle" });
      setSending(false);
    }
  }

  return (
    <div className="h-full flex flex-col gap-4 p-4 overflow-hidden">
      <div className="flex items-center justify-center pt-2">
        <Orb />
      </div>

      <div className="flex-1 overflow-y-auto rounded-xl border border-white/5 bg-black/30 backdrop-blur-sm p-4 text-sm space-y-3 [mask-image:linear-gradient(to_bottom,transparent,black_4%,black_96%,transparent)]">
        {transcript.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center gap-3 py-12">
            <div className="text-zinc-300 font-medium">
              Type below, tap to talk, or press{" "}
              <kbd className="px-1.5 py-0.5 rounded bg-white/10 border border-white/10 text-xs font-mono">
                V
              </kbd>{" "}
              for voice mode.
            </div>
            <div className="text-zinc-500 text-xs max-w-sm">
              CRUZ has context from your last 30 days of work and will
              surface what matters. Try "what's on today?" or "summarize
              yesterday's activity."
            </div>
          </div>
        ) : (
          transcript.map((t, i) =>
            t.role === "user" ? (
              <div key={i} className="flex justify-start">
                <div className="bg-white/5 text-zinc-100 rounded-2xl rounded-bl-sm px-4 py-2 max-w-[80%]">
                  {t.text}
                </div>
              </div>
            ) : t.role === "cruz" ? (
              <div key={i} className="flex justify-end">
                <div className="bg-cyan-500/10 text-cyan-100 border border-cyan-500/20 rounded-2xl rounded-br-sm px-4 py-2 max-w-[80%]">
                  {t.text}
                </div>
              </div>
            ) : (
              <div
                key={i}
                className="text-[11px] text-zinc-500 text-center font-mono"
              >
                {t.text}
              </div>
            ),
          )
        )}
      </div>

      <div className="flex items-center gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void sendText();
            }
          }}
          disabled={sending}
          placeholder="Type a command or press Enter…"
          className="flex-1 rounded-xl bg-white/5 border border-white/10 px-4 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-cyan-500/50 focus:bg-white/10 transition-colors"
        />
        <button
          type="button"
          onClick={() => void sendText()}
          disabled={sending || !input.trim()}
          className="rounded-xl bg-white/10 hover:bg-white/15 px-3 py-2.5 text-zinc-200 disabled:opacity-40 transition-colors"
          aria-label="Send"
        >
          <Send size={16} />
        </button>
        <PTTButton deviceId={deviceId} />
      </div>
    </div>
  );
}
