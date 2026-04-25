/**
 * VoiceOrb — canvas-based audio-reactive orb for voice mode.
 *
 * Rings:
 *   - inner: constant gentle pulse (breathing)
 *   - middle: amplitude of CRUZ's agent audio track (speaking ring)
 *   - outer:  amplitude of the local mic (listening ring)
 *
 * Colors keyed off state:
 *   idle       — slate
 *   connecting — amber
 *   listening  — cyan
 *   thinking   — violet
 *   speaking   — emerald
 *   error      — rose
 *
 * We avoid framer-motion here because canvas rAF is simpler and cheaper
 * than running a JS animation library at 60 fps for amplitude data.
 */
import { useEffect, useRef } from "react";
import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";
import type { VoiceSessionState } from "@/hooks/useVoiceSession";

interface Props {
  state: VoiceSessionState;
  room: Room | null;
  size?: number;
}

const COLORS: Record<VoiceSessionState, { primary: string; glow: string }> = {
  idle: { primary: "148 163 184", glow: "148 163 184" }, // slate-400
  connecting: { primary: "251 191 36", glow: "245 158 11" }, // amber
  listening: { primary: "34 211 238", glow: "8 145 178" }, // cyan
  thinking: { primary: "167 139 250", glow: "139 92 246" }, // violet
  speaking: { primary: "52 211 153", glow: "16 185 129" }, // emerald
  error: { primary: "251 113 133", glow: "225 29 72" }, // rose
};

function rmsFromAnalyser(a: AnalyserNode, buf: Uint8Array): number {
  // DOM lib expects Uint8Array<ArrayBuffer>, but modern TS tracks the
  // buffer type tightly and Uint8Array defaults to <ArrayBufferLike>.
  // Cast is safe: we construct all buffers over concrete ArrayBuffer.
  (a as unknown as {
    getByteTimeDomainData: (b: Uint8Array) => void;
  }).getByteTimeDomainData(buf);
  let sum = 0;
  for (let i = 0; i < buf.length; i++) {
    const v = (buf[i] - 128) / 128;
    sum += v * v;
  }
  return Math.min(1, Math.sqrt(sum / buf.length) * 3); // gain
}

export function VoiceOrb({ state, room, size = 280 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micAnalyserRef = useRef<AnalyserNode | null>(null);
  const agentAnalyserRef = useRef<AnalyserNode | null>(null);

  // Wire analyser nodes to local mic + remote agent track.
  useEffect(() => {
    if (!room) return;
    const ctx = new AudioContext();
    audioCtxRef.current = ctx;

    async function hookLocalMic() {
      const pubs = Array.from(room!.localParticipant.trackPublications.values());
      const mic = pubs.find((p) => p.source === Track.Source.Microphone);
      if (!mic || !mic.track) return;
      const ms = (mic.track as { mediaStreamTrack: MediaStreamTrack })
        .mediaStreamTrack;
      if (!ms) return;
      try {
        const src = ctx.createMediaStreamSource(new MediaStream([ms]));
        const a = ctx.createAnalyser();
        a.fftSize = 512;
        src.connect(a);
        micAnalyserRef.current = a;
      } catch (err) {
        console.warn("[cruz] orb: mic analyser failed", err);
      }
    }

    function hookAgentTrack(track: RemoteTrack) {
      if (track.kind !== Track.Kind.Audio) return;
      const ms = (track as { mediaStreamTrack?: MediaStreamTrack })
        .mediaStreamTrack;
      if (!ms) return;
      try {
        const src = ctx.createMediaStreamSource(new MediaStream([ms]));
        const a = ctx.createAnalyser();
        a.fftSize = 512;
        src.connect(a);
        agentAnalyserRef.current = a;
      } catch (err) {
        console.warn("[cruz] orb: agent analyser failed", err);
      }
    }

    // Existing agent tracks (subscribed before orb mounted).
    room.remoteParticipants.forEach((p) => {
      if (!p.identity.startsWith("agent-")) return;
      p.trackPublications.forEach((pub) => {
        if (pub.track) hookAgentTrack(pub.track);
      });
    });

    void hookLocalMic();

    const onSub = (track: RemoteTrack) => hookAgentTrack(track);
    const onLocalPub = () => {
      void hookLocalMic();
    };
    room.on(RoomEvent.TrackSubscribed, onSub);
    room.on(RoomEvent.LocalTrackPublished, onLocalPub);
    return () => {
      room.off(RoomEvent.TrackSubscribed, onSub);
      room.off(RoomEvent.LocalTrackPublished, onLocalPub);
      void ctx.close();
      micAnalyserRef.current = null;
      agentAnalyserRef.current = null;
      audioCtxRef.current = null;
    };
  }, [room]);

  // Render loop.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx2d = canvas.getContext("2d");
    if (!ctx2d) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx2d.scale(dpr, dpr);

    const micBuf = new Uint8Array(new ArrayBuffer(512));
    const agentBuf = new Uint8Array(new ArrayBuffer(512));
    const cx = size / 2;
    const cy = size / 2;
    const baseR = size * 0.22;
    let t0 = performance.now();

    function frame(now: number) {
      if (document.visibilityState === "hidden") {
        rafRef.current = requestAnimationFrame(frame);
        return;
      }
      const t = (now - t0) / 1000;
      const c = COLORS[state];
      const primary = c.primary;
      const glow = c.glow;
      const breath = 0.5 + 0.5 * Math.sin(t * 1.3);

      ctx2d!.clearRect(0, 0, size, size);

      // Outer ring — listening (mic amp)
      const micRms = micAnalyserRef.current
        ? rmsFromAnalyser(micAnalyserRef.current, micBuf)
        : 0;
      const outerR = baseR * 1.9 + micRms * baseR * 0.7;
      drawRing(ctx2d!, cx, cy, outerR, primary, 0.18 + micRms * 0.35, 1);

      // Middle ring — speaking (agent amp)
      const agentRms = agentAnalyserRef.current
        ? rmsFromAnalyser(agentAnalyserRef.current, agentBuf)
        : 0;
      const midR = baseR * 1.45 + agentRms * baseR * 0.55;
      drawRing(ctx2d!, cx, cy, midR, primary, 0.3 + agentRms * 0.45, 1.5);

      // Inner orb — breathing gradient
      const innerR = baseR * (0.95 + breath * 0.08);
      const grad = ctx2d!.createRadialGradient(cx, cy, 0, cx, cy, innerR);
      grad.addColorStop(0, `rgba(${primary} / 0.95)`);
      grad.addColorStop(0.55, `rgba(${primary} / 0.55)`);
      grad.addColorStop(1, `rgba(${glow} / 0.0)`);
      ctx2d!.fillStyle = grad;
      ctx2d!.beginPath();
      ctx2d!.arc(cx, cy, innerR, 0, Math.PI * 2);
      ctx2d!.fill();

      // Core
      ctx2d!.fillStyle = `rgba(${primary} / ${0.85 + breath * 0.1})`;
      ctx2d!.beginPath();
      ctx2d!.arc(cx, cy, baseR * 0.35, 0, Math.PI * 2);
      ctx2d!.fill();

      rafRef.current = requestAnimationFrame(frame);
    }

    rafRef.current = requestAnimationFrame(frame);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [state, size]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size }}
      className="block"
      aria-hidden
    />
  );
}

function drawRing(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  rgb: string,
  alpha: number,
  width: number,
) {
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.strokeStyle = `rgba(${rgb} / ${alpha})`;
  ctx.lineWidth = width;
  ctx.stroke();
}
