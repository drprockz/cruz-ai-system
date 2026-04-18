import { create } from "zustand";

export type VoiceState = "idle" | "listening" | "thinking" | "speaking" | "interrupted";

export interface TranscriptEntry {
  role: "user" | "cruz" | "tool";
  text: string;
  ts: number;
}

interface VS {
  state: VoiceState;
  currentText: string;
  transcript: TranscriptEntry[];
  set: (s: Partial<Omit<VS, "set" | "append" | "reset">>) => void;
  append: (entry: TranscriptEntry) => void;
  reset: () => void;
}

export const useVoice = create<VS>((set) => ({
  state: "idle",
  currentText: "",
  transcript: [],
  set: (patch) => set(patch),
  append: (entry) =>
    set((s) => ({ transcript: [...s.transcript.slice(-99), entry] })),
  reset: () => set({ transcript: [], currentText: "", state: "idle" }),
}));
