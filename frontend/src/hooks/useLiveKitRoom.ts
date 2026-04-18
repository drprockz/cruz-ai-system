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

export function useLiveKitRoom(deviceId: string) {
  const [room, setRoom] = useState<Room | null>(null);
  const [connected, setConnected] = useState(false);
  const micTrackRef = useRef<LocalAudioTrack | null>(null);

  useEffect(() => {
    let mounted = true;
    let localRoom: Room | null = null;

    (async () => {
      try {
        const tok = await fetchVoiceToken(deviceId);
        const r = new Room({ adaptiveStream: true, dynacast: true });

        r.on(
          RoomEvent.TrackSubscribed,
          (
            track: RemoteTrack,
            _pub: RemoteTrackPublication,
            participant: RemoteParticipant,
          ) => {
            if (track.kind !== Track.Kind.Audio) return;
            // Only play agent audio on phone/tablet.
            // On Mac the daemon owns speaker output; web UI is visual only.
            const isMac = /Macintosh/.test(navigator.userAgent);
            if (participant.identity.startsWith("agent-") && !isMac) {
              const el = track.attach();
              el.autoplay = true;
              document.body.appendChild(el);
            }
          },
        );

        r.on(
          RoomEvent.ActiveSpeakersChanged,
          (speakers: Array<Participant>) => {
            const agentSpeaking = speakers.some((s) =>
              s.identity.startsWith("agent-"),
            );
            const userSpeaking = speakers.some(
              (s) =>
                !s.identity.startsWith("agent-") && s.identity !== deviceId,
            );
            useVoice.getState().set({
              state: agentSpeaking
                ? "speaking"
                : userSpeaking
                  ? "listening"
                  : "idle",
            });
          },
        );

        await r.connect(tok.ws_url, tok.token);

        if (!mounted) {
          await r.disconnect();
          return;
        }

        localRoom = r;
        setRoom(r);
        setConnected(true);
      } catch (exc) {
        console.error("livekit connect failed", exc);
      }
    })();

    return () => {
      mounted = false;
      if (localRoom) {
        void localRoom.disconnect();
      }
    };
  }, [deviceId]);

  const startPTT = async () => {
    if (!room) return;
    const t = await createLocalAudioTrack();
    micTrackRef.current = t;
    await room.localParticipant.publishTrack(t);
    useVoice.getState().set({ state: "listening" });
  };

  const stopPTT = async () => {
    if (!room || !micTrackRef.current) return;
    await room.localParticipant.unpublishTrack(micTrackRef.current);
    micTrackRef.current.stop();
    micTrackRef.current = null;
    useVoice.getState().set({ state: "thinking" });
  };

  return { room, connected, startPTT, stopPTT };
}
