/**
 * VoiceMode — full-screen continuous duplex voice UI.
 *
 * Claude-voice-mode / ChatGPT-voice style: one orb, live transcript
 * underneath, single "End call" button. No PTT button press per turn.
 *
 * Entered via top-bar "Voice" button or `v` keymap; exited via End,
 * Esc, or browser back.
 */
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { PhoneOff } from "lucide-react";
import { useVoiceSession } from "@/hooks/useVoiceSession";
import { VoiceOrb } from "@/components/voice/VoiceOrb";
import { LiveTranscript } from "@/components/voice/LiveTranscript";
import { useDevice } from "@/lib/breakpoints";

const STATE_LABELS = {
  idle: "Idle",
  connecting: "Connecting…",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Responding",
  error: "Error",
} as const;

export default function VoiceMode() {
  const device = useDevice();
  const deviceId =
    device === "phone" ? "phone" : device === "tablet" ? "ipad" : "mac-web";
  const nav = useNavigate();
  const session = useVoiceSession(deviceId);

  // Auto-enter on mount, auto-exit on unmount.
  useEffect(() => {
    void session.enter();
    return () => {
      void session.exit();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Esc → exit.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        void session.exit().then(() => nav("/tab/conversation"));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [session, nav]);

  const orbSize = device === "phone" ? 220 : device === "tablet" ? 280 : 340;

  return (
    <div className="fixed inset-0 z-50 bg-gradient-to-b from-zinc-950 via-zinc-900 to-black flex flex-col">
      {/* Top: state chip */}
      <div className="pt-8 flex justify-center">
        <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/5 backdrop-blur border border-white/10 text-xs tracking-wide uppercase">
          <span
            className={
              "inline-block w-2 h-2 rounded-full " +
              (session.state === "listening"
                ? "bg-cyan-400 animate-pulse"
                : session.state === "speaking"
                  ? "bg-emerald-400 animate-pulse"
                  : session.state === "thinking"
                    ? "bg-violet-400 animate-pulse"
                    : session.state === "connecting"
                      ? "bg-amber-400 animate-pulse"
                      : session.state === "error"
                        ? "bg-rose-400"
                        : "bg-zinc-500")
            }
          />
          <span className="text-zinc-200">
            {STATE_LABELS[session.state]}
          </span>
        </div>
      </div>

      {/* Middle: orb */}
      <div className="flex-1 flex items-center justify-center">
        <VoiceOrb state={session.state} room={session.room} size={orbSize} />
      </div>

      {/* Transcript */}
      <div className="pb-6">
        <LiveTranscript
          interim={session.interim}
          finals={session.finals}
          replies={session.replies}
        />
      </div>

      {/* Error overlay */}
      {session.error && (
        <div className="absolute bottom-28 inset-x-0 flex justify-center">
          <div className="px-4 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-200 text-sm max-w-md text-center">
            {session.error}
          </div>
        </div>
      )}

      {/* Bottom: end call */}
      <div className="pb-10 flex justify-center">
        <button
          type="button"
          onClick={() =>
            void session.exit().then(() => nav("/tab/conversation"))
          }
          className="flex items-center gap-2 px-6 py-3 rounded-full bg-rose-500 hover:bg-rose-400 text-white font-medium shadow-lg shadow-rose-500/30 transition-colors"
          aria-label="End voice session"
        >
          <PhoneOff size={18} />
          End
        </button>
      </div>
    </div>
  );
}
