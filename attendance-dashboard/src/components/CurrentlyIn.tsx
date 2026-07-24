"use client";

import { useEffect, useState } from "react";
import { AttendanceRow } from "@/lib/types";
import { getCurrentlyIn, formatDuration, formatTime } from "@/lib/attendanceCalc";
import { Badge } from "./Badge";

export function CurrentlyIn({ rows }: { rows: AttendanceRow[] }) {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  if (!now) return null;

  const currentlyIn = getCurrentlyIn(rows, now);

  return (
    <div className="rounded-[10px] border border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div>
          <h2 className="text-[15px] font-semibold">Currently In</h2>
          <p className="mt-0.5 text-xs text-text-dim">Live · updates every second</p>
        </div>
        <Badge tone="success">{currentlyIn.length} inside</Badge>
      </div>

      {currentlyIn.length === 0 ? (
        <div className="px-5 py-10 text-center text-sm text-text-dim">
          No one is currently checked in.
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {currentlyIn.map((e) => (
            <li key={e.employeeId} className="flex items-center justify-between px-5 py-3.5">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-[#3a4a7a] to-[#232834] text-[13px] font-semibold text-[#cdd6e8]">
                  {e.name[0]?.toUpperCase()}
                </div>
                <div>
                  <div className="text-sm font-medium">{e.name}</div>
                  <div className="text-xs text-text-dim">
                    {e.employeeId} · in at {formatTime(e.inTime)}
                  </div>
                </div>
              </div>
              <div className="text-sm font-semibold text-success">
                {formatDuration(e.durationMs)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
