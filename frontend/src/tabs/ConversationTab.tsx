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
      const r = await fetch("/api/command", {
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
      <Orb />

      <div className="flex-1 overflow-y-auto rounded-md border border-zinc-800 bg-zinc-900/50 p-4 text-sm">
        {transcript.length === 0 && (
          <div className="text-zinc-500">
            Hold the button to talk, or type below.{" "}
            <span className="text-zinc-600">
              (On Mac you can also say &ldquo;Hey Jarvis&rdquo; via the
              daemon.)
            </span>
          </div>
        )}
        {transcript.map((t, i) => (
          <div key={i} className="mb-2">
            <span
              className={
                t.role === "user"
                  ? "text-blue-400 font-medium"
                  : t.role === "cruz"
                    ? "text-green-400 font-medium"
                    : "text-zinc-500"
              }
            >
              {t.role === "user" ? "You" : t.role === "cruz" ? "CRUZ" : "→"}
            </span>
            <span className="ml-2 text-zinc-200">{t.text}</span>
          </div>
        ))}
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
          className="flex-1 rounded-md bg-zinc-900 border border-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none focus:border-green-500"
        />
        <button
          type="button"
          onClick={() => void sendText()}
          disabled={sending || !input.trim()}
          className="rounded-md bg-zinc-800 hover:bg-zinc-700 px-3 py-2 text-zinc-200 disabled:opacity-40"
          aria-label="Send"
        >
          <Send size={16} />
        </button>
        <PTTButton deviceId={deviceId} />
      </div>
    </div>
  );
}
