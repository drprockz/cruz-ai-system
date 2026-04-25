import { motion } from "framer-motion";
import { useVoice } from "@/state/voiceStore";

/**
 * Compact in-page orb for the Conversation tab.
 *
 * Not to be confused with VoiceOrb (full-screen /voice route) — this one
 * is state-indicator only, no audio reactivity. Keeps the conversation
 * header alive without competing visually with message content.
 */
export function Orb() {
  const s = useVoice((v) => v.state);
  const text = useVoice((v) => v.currentText);

  const palette = {
    idle: { ring: "ring-zinc-700", glow: "rgba(113,113,122,0.15)", dot: "bg-zinc-600" },
    listening: {
      ring: "ring-cyan-500/60",
      glow: "rgba(34,211,238,0.35)",
      dot: "bg-cyan-400",
    },
    thinking: {
      ring: "ring-violet-500/60",
      glow: "rgba(167,139,250,0.35)",
      dot: "bg-violet-400",
    },
    speaking: {
      ring: "ring-emerald-500/60",
      glow: "rgba(52,211,153,0.4)",
      dot: "bg-emerald-400",
    },
    interrupted: {
      ring: "ring-amber-500/60",
      glow: "rgba(251,191,36,0.35)",
      dot: "bg-amber-400",
    },
  } as const;
  const p = palette[s];

  const scale = s === "speaking" ? 1.08 : s === "listening" ? 1.04 : 1;

  return (
    <div className="flex flex-col items-center justify-center gap-3">
      <motion.div
        animate={{ scale }}
        transition={{ type: "spring", stiffness: 160, damping: 16 }}
        className={`relative h-20 w-20 rounded-full ring-1 ${p.ring} bg-black/40 backdrop-blur-sm flex items-center justify-center`}
        style={{ boxShadow: `0 0 32px ${p.glow}` }}
      >
        {(s === "listening" || s === "speaking") ? (
          <div className="flex gap-1 items-end h-6">
            {[14, 22, 12, 20].map((h, i) => (
              <motion.div
                key={i}
                className={`w-[3px] rounded-full ${p.dot}`}
                animate={{ height: [h, h * 0.5, h] }}
                transition={{
                  duration: 0.6,
                  repeat: Infinity,
                  delay: i * 0.08,
                }}
                style={{ height: h }}
              />
            ))}
          </div>
        ) : s === "thinking" ? (
          <div className="flex gap-1.5">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className={`h-1.5 w-1.5 rounded-full ${p.dot}`}
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
              />
            ))}
          </div>
        ) : (
          <div className={`h-2 w-2 rounded-full ${p.dot}`} />
        )}
      </motion.div>
      {text && (
        <div className="text-xs text-zinc-400 text-center max-w-md">
          {text}
        </div>
      )}
    </div>
  );
}
