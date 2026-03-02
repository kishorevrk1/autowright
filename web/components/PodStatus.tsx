"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

export default function PodStatus() {
  const [health, setHealth] = useState<"ok" | "error" | "loading">("loading");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const res = await fetch(`${API_URL}/health`);
        if (!cancelled) setHealth(res.ok ? "ok" : "error");
      } catch {
        if (!cancelled) setHealth("error");
      }
    }

    check();
    const interval = setInterval(check, 10_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const dotClass =
    health === "ok"
      ? "bg-emerald-500"
      : health === "loading"
      ? "bg-zinc-600 animate-pulse"
      : "bg-red-500";

  const label =
    health === "ok" ? "Pipeline ready" : health === "loading" ? "Connecting…" : "Pipeline offline";

  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${dotClass}`} />
      <span className="text-xs text-zinc-500">{label}</span>
    </div>
  );
}
