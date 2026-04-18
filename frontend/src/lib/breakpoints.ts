import { useEffect, useState } from "react";

export type Device = "phone" | "tablet" | "desktop";

function resolve(w: number): Device {
  if (w < 768) return "phone";
  if (w < 1024) return "tablet";
  return "desktop";
}

export function useDevice(): Device {
  const [d, setD] = useState<Device>(() =>
    typeof window === "undefined" ? "desktop" : resolve(window.innerWidth),
  );
  useEffect(() => {
    const on = () => setD(resolve(window.innerWidth));
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return d;
}
