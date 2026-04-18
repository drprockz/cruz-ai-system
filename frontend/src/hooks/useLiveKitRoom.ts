import { useEffect, useRef, useState } from "react";
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
        const isMac = /Macintosh/.test(navigator.userAgent);
        // On Mac the daemon owns speakers; web UI is visual only by default.
        // To force browser audio on Mac (e.g. testing without daemon), set
        // sessionStorage["cruz:web_audio"] = "1" from DevTools.
        const forceWebAudio =
          sessionStorage.getItem("cruz:web_audio") === "1";
        if (
          participant.identity.startsWith("agent-") &&
          (!isMac || forceWebAudio)
        ) {
          const el = track.attach();
          el.autoplay = true;
          document.body.appendChild(el);
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

    await r.connect(tok.ws_url, tok.token);
    _state.room = r;
    _state.connected = true;
    _state.deviceId = deviceId;
    _state.connecting = null;
    _notify();
    return r;
  })();

  try {
    return await _state.connecting;
  } catch (exc) {
    _state.connecting = null;
    throw exc;
  }
}

export function useLiveKitRoom(deviceId: string) {
  const [, forceRender] = useState(0);
  const micTrackRef = useRef<LocalAudioTrack | null>(null);

  useEffect(() => {
    const onChange = () => forceRender((n) => n + 1);
    _listeners.add(onChange);
    _ensureRoom(deviceId).catch((exc: unknown) => {
      console.error("livekit connect failed", exc);
    });
    return () => {
      _listeners.delete(onChange);
      // Don't disconnect on unmount — other consumers may still want the room.
      // Room stays alive for the browser session; torn down via Disconnected event.
    };
  }, [deviceId]);

  const startPTT = async () => {
    const r = _state.room ?? (await _ensureRoom(deviceId));
    const t = await createLocalAudioTrack();
    micTrackRef.current = t;
    await r.localParticipant.publishTrack(t);
    useVoice.getState().set({ state: "listening" });
  };

  const stopPTT = async () => {
    const r = _state.room;
    if (!r || !micTrackRef.current) return;
    await r.localParticipant.unpublishTrack(micTrackRef.current);
    micTrackRef.current.stop();
    micTrackRef.current = null;
    useVoice.getState().set({ state: "thinking" });
  };

  return {
    room: _state.room,
    connected: _state.connected,
    startPTT,
    stopPTT,
  };
}
