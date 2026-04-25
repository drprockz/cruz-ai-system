/**
 * LiveTranscript — renders the voice-mode conversation as it unfolds.
 *
 *   - interim user speech: gray italic (ephemeral)
 *   - final user turn:     white, left-aligned chip
 *   - CRUZ reply (streaming): emerald, right-aligned chip; shows a
 *     soft blinking caret while streaming, solid once reply_done.
 */
import { useEffect, useRef } from "react";
import type { Reply } from "@/hooks/useVoiceSession";

interface Props {
  interim: string;
  finals: string[];
  replies: Reply[];
}

/**
 * Interleave finals + replies by chronological order. In practice they
 * arrive alternating (user turn → CRUZ reply → user turn), so we just
 * zip them in order and render.
 */
export function LiveTranscript({ interim, finals, replies }: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scrollerRef.current?.scrollTo({
      top: scrollerRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [interim, finals.length, replies.length, replies[replies.length - 1]?.text]);

  const rows: Array<
    { kind: "user"; text: string } | { kind: "cruz"; reply: Reply }
  > = [];
  const n = Math.max(finals.length, replies.length);
  for (let i = 0; i < n; i++) {
    if (i < finals.length) rows.push({ kind: "user", text: finals[i] });
    if (i < replies.length) rows.push({ kind: "cruz", reply: replies[i] });
  }

  return (
    <div
      ref={scrollerRef}
      className="w-full max-w-2xl mx-auto h-64 overflow-y-auto px-6 space-y-3 [mask-image:linear-gradient(to_bottom,transparent,black_12%,black_88%,transparent)]"
    >
      {rows.length === 0 && !interim && (
        <div className="text-center text-zinc-500 text-sm pt-20">
          Say anything. CRUZ is listening.
        </div>
      )}
      {rows.map((r, i) =>
        r.kind === "user" ? (
          <div key={`u-${i}`} className="flex justify-start">
            <div className="bg-zinc-800/60 text-zinc-100 rounded-2xl rounded-bl-sm px-4 py-2 max-w-[80%] text-sm">
              {r.text}
            </div>
          </div>
        ) : (
          <div key={`c-${r.reply.trace_id}-${i}`} className="flex justify-end">
            <div className="bg-emerald-500/10 text-emerald-100 border border-emerald-500/20 rounded-2xl rounded-br-sm px-4 py-2 max-w-[80%] text-sm">
              {r.reply.text}
              {r.reply.streaming && (
                <span className="inline-block w-[2px] h-4 bg-emerald-300 ml-1 align-middle animate-pulse" />
              )}
            </div>
          </div>
        ),
      )}
      {interim && (
        <div className="flex justify-start">
          <div className="text-zinc-400 italic px-4 py-1 text-sm">{interim}</div>
        </div>
      )}
    </div>
  );
}
