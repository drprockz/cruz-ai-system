import { useState } from "react";
import { useLiveKitRoom } from "@/hooks/useLiveKitRoom";
import { Mic, MicOff } from "lucide-react";

interface PTTButtonProps {
  deviceId: string;
}

/**
 * Tap-to-toggle voice button (replaces the old press-and-hold PTT).
 *
 * Tap once  → mic unmutes, CRUZ listens.
 * Tap again → mic mutes. Deepgram's VAD on the worker also auto-finalizes
 *             on silence, so CRUZ will usually reply without you tapping
 *             a second time at all.
 *
 * Why toggle instead of hold:
 *   Browsers race on pointerdown/pointerup publish/unpublish cycles —
 *   you get "could not find local track subscription" warnings and
 *   dropped turns. One deliberate action per state transition fixes it.
 */
export function PTTButton({ deviceId }: PTTButtonProps) {
  const { startPTT, stopPTT, connected } = useLiveKitRoom(deviceId);
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    if (busy) return;
    setBusy(true);
    try {
      if (listening) {
        await stopPTT();
        setListening(false);
      } else {
        await startPTT();
        setListening(true);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      disabled={!connected || busy}
      onClick={() => void toggle()}
      className={
        "flex items-center gap-2 rounded-full px-6 py-3 font-semibold " +
        "disabled:opacity-40 select-none " +
        (listening
          ? "bg-red-500 text-white animate-pulse"
          : "bg-green-500 text-black")
      }
      aria-pressed={listening}
      aria-label={listening ? "Stop listening" : "Start listening"}
    >
      {listening ? <MicOff size={18} /> : <Mic size={18} />}
      {listening ? "Listening — tap to stop" : "Tap to talk"}
    </button>
  );
}
