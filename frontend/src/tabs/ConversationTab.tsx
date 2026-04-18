import { useVoice } from "@/state/voiceStore";
import { Orb } from "@/components/Orb";
import { PTTButton } from "@/components/PTTButton";
import { useLiveKitRoom } from "@/hooks/useLiveKitRoom";
import { useDevice } from "@/lib/breakpoints";

export function ConversationTab() {
  const device = useDevice();
  const deviceId =
    device === "phone" ? "phone" : device === "tablet" ? "ipad" : "mac-web";

  // Ensure LiveKit room is joined for this device.
  // On Mac/desktop the daemon owns mic + speaker; here we observe room events
  // and render the transcript/orb state only.
  useLiveKitRoom(deviceId);

  const transcript = useVoice((v) => v.transcript);

  return (
    <div className="h-full flex flex-col gap-4 p-4 overflow-hidden">
      <Orb />

      <div className="flex-1 overflow-y-auto rounded-md border border-zinc-800 bg-zinc-900/50 p-4 text-sm">
        {transcript.length === 0 && (
          <div className="text-zinc-500">
            Say &ldquo;Hey CRUZ&rdquo; on Mac, or hold the button below to
            talk.
          </div>
        )}
        {transcript.map((t, i) => (
          <div key={i} className="mb-2">
            <span
              className={
                t.role === "user"
                  ? "text-blue-400 font-medium"
                  : t.role === "cruz"
                    ? "text-green-400 font-medium"
                    : "text-zinc-500"
              }
            >
              {t.role === "user" ? "You" : t.role === "cruz" ? "CRUZ" : "→"}
            </span>
            <span className="ml-2 text-zinc-200">{t.text}</span>
          </div>
        ))}
      </div>

      {device !== "desktop" && (
        <div className="flex justify-center pb-2">
          <PTTButton deviceId={deviceId} />
        </div>
      )}
    </div>
  );
}
