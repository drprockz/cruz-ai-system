import { useEffect, useState } from "react";
import {
  Room,
  RoomEvent,
  Track,
  LocalAudioTrack,
  createLocalAudioTrack,
  type RemoteTrack,
  type RemoteTrackPublication,
  type RemoteParticipant,
  type Participant,
} from "livekit-client";
import { fetchVoiceToken } from "@/lib/livekit";
import { useVoice } from "@/state/voiceStore";

// Persist conversation_id across page reloads + React StrictMode double-mounts.
// Without this every re-render spawns a new LiveKit room and a new worker job.
function getOrCreateConversationId(): string {
  const key = "cruz:conversation_id";
  const existing = sessionStorage.getItem(key);
  if (existing) return existing;
  const fresh = crypto.randomUUID();
  sessionStorage.setItem(key, fresh);
  return fresh;
}

// Module-scoped singleton so multiple hook callers on the same page share one
// Room (previously ConversationTab AND PTTButton each created their own).
interface RoomState {
  room: Room | null;
  connected: boolean;
  connecting: Promise<Room> | null;
  deviceId: string | null;
}
const _state: RoomState = {
  room: null,
  connected: false,
  connecting: null,
  deviceId: null,
};
const _listeners = new Set<() => void>();
function _notify() {
  _listeners.forEach((l) => l());
}

// Data channel contract — must match workers/voice_agent/worker.py
// _publish_voice_msg and docs/superpowers/specs/2026-04-19-voice-mode-and-ui-polish.md
export type CruzVoiceMsg =
  | { type: "stt_interim"; text: string }
  | { type: "stt_final"; text: string }
  | { type: "reply_chunk"; text: string; trace_id: string }
  | { type: "reply_done"; trace_id: string };

const _dataListeners = new Set<(msg: CruzVoiceMsg) => void>();
export function onCruzVoiceMsg(cb: (msg: CruzVoiceMsg) => void): () => void {
  _dataListeners.add(cb);
  return () => _dataListeners.delete(cb);
}

async function _ensureRoom(deviceId: string): Promise<Room> {
  if (_state.room && _state.deviceId === deviceId) return _state.room;
  if (_state.connecting) return _state.connecting;

  _state.connecting = (async () => {
    const conversationId = getOrCreateConversationId();
    const tok = await fetchVoiceToken(deviceId, conversationId);
    const r = new Room({ adaptiveStream: true, dynacast: true });

    r.on(
      RoomEvent.TrackSubscribed,
      (
        track: RemoteTrack,
        _pub: RemoteTrackPublication,
        participant: RemoteParticipant,
      ) => {
        if (track.kind !== Track.Kind.Audio) return;
        // The web UI and the Mac daemon join DIFFERENT rooms (deviceId
        // `mac-web` vs `mac-mini`), so there's no speaker double-play risk
        // even on Mac. Always attach agent audio so browser-initiated PTT
        // gets a response. To silence browser audio (e.g. during daemon
        // testing) set sessionStorage["cruz:mute_web_audio"] = "1".
        const muteWebAudio =
          sessionStorage.getItem("cruz:mute_web_audio") === "1";
        if (participant.identity.startsWith("agent-") && !muteWebAudio) {
          const el = track.attach() as HTMLAudioElement;
          el.autoplay = true;
          el.muted = false;
          el.volume = 1.0;
          el.setAttribute("playsinline", "");
          el.setAttribute("data-cruz-agent-audio", "1");
          document.body.appendChild(el);
          // Chrome can block autoplay even post-user-gesture on some
          // configs; nudge it explicitly and surface failures.
          void el.play().catch((err: unknown) => {
            console.warn("[cruz] agent audio autoplay blocked:", err);
          });
          console.log(
            "[cruz] agent audio attached from",
            participant.identity,
          );
        }
      },
    );

    r.on(RoomEvent.ActiveSpeakersChanged, (speakers: Array<Participant>) => {
      const agentSpeaking = speakers.some((s) =>
        s.identity.startsWith("agent-"),
      );
      const userSpeaking = speakers.some(
        (s) => !s.identity.startsWith("agent-") && s.identity !== deviceId,
      );
      useVoice.getState().set({
        state: agentSpeaking
          ? "speaking"
          : userSpeaking
            ? "listening"
            : "idle",
      });
    });

    r.on(RoomEvent.Disconnected, () => {
      _state.room = null;
      _state.connected = false;
      _state.deviceId = null;
      _state.connecting = null;
      _notify();
    });

    // Data channel: worker publishes interim/final STT + reply chunks here.
    r.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
      try {
        const text = new TextDecoder().decode(payload);
        const msg = JSON.parse(text) as CruzVoiceMsg;
        _dataListeners.forEach((cb) => {
          try {
            cb(msg);
          } catch (err) {
            console.error("[cruz] data listener threw", err);
          }
        });
      } catch (err) {
        console.warn("[cruz] malformed data-channel msg", err);
      }
    });

    console.log("[cruz] connecting LiveKit room:", tok.room, "@", tok.ws_url);
    await r.connect(tok.ws_url, tok.token);
    console.log("[cruz] LiveKit connected; waiting for cruz-voice-worker…");
    _state.room = r;
    _state.connected = true;
    _state.deviceId = deviceId;
    _state.connecting = null;
    _notify();

    // Agent-join watchdog: LiveKit Cloud should dispatch cruz-voice-worker
    // within a few seconds. If it doesn't, the room is orphaned — warn
    // the user so they don't hold-to-talk into a black hole.
    setTimeout(() => {
      const agentHere = Array.from(r.remoteParticipants.values()).some(
        (p) => p.identity.startsWith("agent-"),
      );
      if (!agentHere) {
        console.warn(
          "[cruz] NO AGENT in room after 6s. cruz-voice-worker did not " +
            "get dispatched. Run `sessionStorage.clear(); location.reload()` " +
            "to force a fresh room, and check `pm2 logs cruz-voice-worker`.",
        );
      } else {
        console.log("[cruz] agent participant present — voice loop ready.");
      }
    }, 6000);

    return r;
  })();

  try {
    return await _state.connecting;
  } catch (exc) {
    _state.connecting = null;
    throw exc;
  }
}

// Module-scoped mic track — one persistent track, muted between PTT presses.
// Creating a fresh LocalAudioTrack on every press races with LiveKit's async
// publish/unpublish and drops turns ("could not find local track subscription").
const _mic: {
  track: LocalAudioTrack | null;
  published: boolean;
  busy: Promise<void> | null;
} = { track: null, published: false, busy: null };

async function _serialize<T>(fn: () => Promise<T>): Promise<T> {
  // Wait for any in-flight PTT op to settle before starting the next one.
  while (_mic.busy) {
    try {
      await _mic.busy;
    } catch {
      /* previous op failed; we still proceed */
    }
  }
  let resolve!: () => void;
  _mic.busy = new Promise<void>((res) => {
    resolve = res;
  });
  try {
    return await fn();
  } finally {
    resolve();
    _mic.busy = null;
  }
}

export function useLiveKitRoom(deviceId: string) {
  const [, forceRender] = useState(0);

  useEffect(() => {
    const onChange = () => forceRender((n) => n + 1);
    _listeners.add(onChange);
    _ensureRoom(deviceId).catch((exc: unknown) => {
      console.error("[cruz] livekit connect failed", exc);
      const msg = exc instanceof Error ? exc.message : String(exc);
      if (!(window as unknown as { __cruzLKWarned?: boolean }).__cruzLKWarned) {
        (window as unknown as { __cruzLKWarned?: boolean }).__cruzLKWarned =
          true;
        console.warn(
          "[cruz] voice disabled — token/LiveKit error. PTT will refuse.",
          msg,
        );
      }
    });
    return () => {
      _listeners.delete(onChange);
    };
  }, [deviceId]);

  const startPTT = () =>
    _serialize(async () => {
      try {
        console.log("[cruz] PTT down → ensuring room…");
        const r = _state.room ?? (await _ensureRoom(deviceId));
        try {
          await r.startAudio();
          console.log("[cruz] audio context resumed");
        } catch (err) {
          console.warn("[cruz] startAudio failed (continuing):", err);
        }
        // Reuse a single mic track; just unmute instead of re-creating.
        if (!_mic.track) {
          console.log("[cruz] PTT creating mic track (first press)…");
          _mic.track = await createLocalAudioTrack();
        }
        if (!_mic.published) {
          await r.localParticipant.publishTrack(_mic.track);
          _mic.published = true;
          console.log("[cruz] PTT mic published");
        }
        await _mic.track.unmute();
        console.log("[cruz] PTT mic unmuted");
        useVoice.getState().set({ state: "listening" });
      } catch (exc) {
        console.error("[cruz] PTT start failed:", exc);
        useVoice.getState().set({ state: "idle" });
        alert(
          "Mic failed: " +
            (exc instanceof Error ? exc.message : String(exc)) +
            "\n\nCheck browser mic permission for this site.",
        );
      }
    });

  const stopPTT = () =>
    _serialize(async () => {
      try {
        if (!_mic.track) return;
        await _mic.track.mute();
        console.log("[cruz] PTT up → mic muted, waiting for CRUZ…");
        useVoice.getState().set({ state: "thinking" });
      } catch (exc) {
        console.error("[cruz] PTT stop failed:", exc);
      }
    });

  // Continuous voice-mode: unmute once, keep mic hot until exit.
  // Deepgram's 500ms endpointing + worker barge-in handle turn-taking;
  // the browser just publishes audio continuously.
  const enterVoiceMode = () =>
    _serialize(async () => {
      const r = _state.room ?? (await _ensureRoom(deviceId));
      try {
        await r.startAudio();
      } catch {
        /* ok */
      }
      if (!_mic.track) {
        _mic.track = await createLocalAudioTrack({
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        });
      }
      if (!_mic.published) {
        await r.localParticipant.publishTrack(_mic.track);
        _mic.published = true;
      }
      await _mic.track.unmute();
      console.log("[cruz] voice mode entered — mic hot");
    });

  const exitVoiceMode = () =>
    _serialize(async () => {
      if (_mic.track) {
        try {
          await _mic.track.mute();
        } catch {
          /* ok */
        }
      }
      console.log("[cruz] voice mode exited — mic muted");
    });

  return {
    room: _state.room,
    connected: _state.connected,
    startPTT,
    stopPTT,
    enterVoiceMode,
    exitVoiceMode,
  };
}
