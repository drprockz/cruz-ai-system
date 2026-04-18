import { motion } from "framer-motion";
import { useVoice } from "@/state/voiceStore";

export function Orb() {
  const s = useVoice((v) => v.state);
  const text = useVoice((v) => v.currentText);

  const scale = s === "speaking" ? 1.1 : s === "listening" ? 1.05 : 1;

  const ringColour =
    s === "interrupted"
      ? "ring-amber-500"
      : s === "thinking"
        ? "ring-blue-500"
        : "ring-green-500";

  return (
    <div className="flex flex-col items-center justify-center gap-4 py-6">
      <motion.div
        animate={{ scale }}
        transition={{ type: "spring", stiffness: 180, damping: 14 }}
        className={`h-24 w-24 rounded-full ring-2 ${ringColour} ring-offset-2 ring-offset-zinc-950 bg-zinc-900 flex items-center justify-center`}
      >
        {(s === "listening" || s === "speaking") && (
          <div className="flex gap-1 items-end">
            {[16, 26, 14, 22].map((h, i) => (
              <motion.div
                key={i}
                className="w-1 bg-green-500 rounded-full"
                animate={{ height: [h, h * 0.6, h] }}
                transition={{
                  duration: 0.6,
                  repeat: Infinity,
                  delay: i * 0.1,
                }}
                style={{ height: h }}
              />
            ))}
          </div>
        )}
        {s === "thinking" && (
          <div className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="h-2 w-2 rounded-full bg-blue-400"
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
              />
            ))}
          </div>
        )}
        {s === "idle" && (
          <div className="h-2 w-2 rounded-full bg-zinc-600" />
        )}
        {s === "interrupted" && (
          <div className="h-3 w-3 rounded-full bg-amber-500" />
        )}
      </motion.div>
      <div className="text-sm text-zinc-300 min-h-[1.25rem] text-center max-w-xl">
        {text || (s === "idle" ? "Ready." : "")}
      </div>
    </div>
  );
}
