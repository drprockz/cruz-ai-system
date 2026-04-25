/**
 * useVoiceSession — state machine + transcript for the /voice full-screen mode.
 *
 * Wraps useLiveKitRoom with:
 *   - enter/exit continuous voice mode
 *   - interim + final user transcripts from data channel
 *   - CRUZ reply stream (buffered by trace_id)
 *   - state: idle | listening | thinking | speaking | error
 *
 * State transitions are driven by:
 *   - RoomEvent.ActiveSpeakersChanged (via useVoice zustand store)
 *   - data channel messages (for transcript text only, NEVER for state)
 *
 * Contract: docs/superpowers/specs/2026-04-19-voice-mode-and-ui-polish.md
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useLiveKitRoom,
  onCruzVoiceMsg,
  type CruzVoiceMsg,
} from "@/hooks/useLiveKitRoom";
import { useVoice } from "@/state/voiceStore";

export type VoiceSessionState =
  | "idle"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "error";

export interface Reply {
  trace_id: string;
  text: string;
  streaming: boolean;
}

export interface VoiceSession {
  state: VoiceSessionState;
  error: string | null;
  interim: string;
  finals: string[];
  replies: Reply[];
  enter: () => Promise<void>;
  exit: () => Promise<void>;
  /** Underlying room; exposed so the orb can hook the analyser nodes. */
  room: ReturnType<typeof useLiveKitRoom>["room"];
  connected: boolean;
}

export function useVoiceSession(deviceId: string): VoiceSession {
  const { enterVoiceMode, exitVoiceMode, room, connected } =
    useLiveKitRoom(deviceId);

  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interim, setInterim] = useState("");
  const [finals, setFinals] = useState<string[]>([]);
  const [replies, setReplies] = useState<Reply[]>([]);
  // Voice state from the zustand store — populated by ActiveSpeakersChanged.
  const lkVoiceState = useVoice((v) => v.state);

  // Subscribe to data-channel transcripts.
  useEffect(() => {
    if (!active) return;
    const off = onCruzVoiceMsg((msg: CruzVoiceMsg) => {
      switch (msg.type) {
        case "stt_interim":
          setInterim(msg.text);
          break;
        case "stt_final":
          setInterim("");
          setFinals((f) => [...f.slice(-19), msg.text]);
          break;
        case "reply_chunk":
          setReplies((rs) => {
            const existing = rs.find((r) => r.trace_id === msg.trace_id);
            if (existing) {
              return rs.map((r) =>
                r.trace_id === msg.trace_id
                  ? { ...r, text: r.text + " " + msg.text }
                  : r,
              );
            }
            return [
              ...rs.slice(-19),
              { trace_id: msg.trace_id, text: msg.text, streaming: true },
            ];
          });
          break;
        case "reply_done":
          setReplies((rs) =>
            rs.map((r) =>
              r.trace_id === msg.trace_id ? { ...r, streaming: false } : r,
            ),
          );
          break;
      }
    });
    return off;
  }, [active]);

  // Derive session state. Gating on `active` means "before enter(),
  // we're idle regardless of what the underlying room is doing".
  const state: VoiceSessionState = useMemo(() => {
    if (error) return "error";
    if (!active) return "idle";
    if (!connected) return "connecting";
    // lkVoiceState reflects ActiveSpeakersChanged + our own mic state.
    // If no one is actively speaking but we have a pending reply stream,
    // we're thinking/about-to-speak.
    const lastReply = replies[replies.length - 1];
    const hasStreaming = lastReply && lastReply.streaming;
    if (lkVoiceState === "speaking") return "speaking";
    if (lkVoiceState === "listening") return "listening";
    if (hasStreaming) return "thinking";
    return "listening"; // default when active — mic is hot
  }, [error, active, connected, lkVoiceState, replies]);

  const busyRef = useRef(false);

  const enter = useCallback(async () => {
    if (busyRef.current || active) return;
    busyRef.current = true;
    try {
      setError(null);
      await enterVoiceMode();
      setActive(true);
    } catch (exc) {
      const msg =
        exc instanceof Error ? exc.message : `voice enter failed: ${exc}`;
      console.error("[cruz] voice enter failed:", exc);
      setError(msg);
    } finally {
      busyRef.current = false;
    }
  }, [active, enterVoiceMode]);

  const exit = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    try {
      await exitVoiceMode();
    } catch (exc) {
      console.warn("[cruz] voice exit warning:", exc);
    } finally {
      setActive(false);
      setInterim("");
      busyRef.current = false;
    }
  }, [exitVoiceMode]);

  // Auto-exit if the tab backgrounds for >60s (mic privacy guard).
  useEffect(() => {
    if (!active) return;
    let bgStart: number | null = null;
    const onVis = () => {
      if (document.visibilityState === "hidden") {
        bgStart = Date.now();
      } else if (bgStart && Date.now() - bgStart > 60_000) {
        console.warn("[cruz] voice mode auto-exit: tab backgrounded 60s+");
        void exit();
      } else {
        bgStart = null;
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [active, exit]);

  return {
    state,
    error,
    interim,
    finals,
    replies,
    enter,
    exit,
    room,
    connected,
  };
}
