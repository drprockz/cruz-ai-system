import { useLiveKitRoom } from "@/hooks/useLiveKitRoom";
import { Mic } from "lucide-react";

interface PTTButtonProps {
  deviceId: string;
}

export function PTTButton({ deviceId }: PTTButtonProps) {
  const { startPTT, stopPTT, connected } = useLiveKitRoom(deviceId);

  return (
    <button
      disabled={!connected}
      onPointerDown={() => void startPTT()}
      onPointerUp={() => void stopPTT()}
      onPointerLeave={() => void stopPTT()}
      className="flex items-center gap-2 rounded-full bg-green-500 px-6 py-3 text-black font-semibold disabled:opacity-40 select-none touch-none"
      aria-label="Push to talk"
    >
      <Mic size={18} />
      Hold to talk
    </button>
  );
}
