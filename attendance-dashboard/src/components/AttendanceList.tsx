"use client";

import { useState } from "react";
import { AttendanceRow } from "@/lib/types";
import { durationMs, formatDuration, formatTime, getRowStatus } from "@/lib/attendanceCalc";
import { StatusBadge } from "./StatusBadge";

type SortKey = "date" | "name" | "duration";

export function AttendanceList({ rows, now }: { rows: AttendanceRow[]; now: Date }) {
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sorted = [...rows].sort((a, b) => {
    let cmp = 0;
    if (sortKey === "date") cmp = a.date.localeCompare(b.date);
    if (sortKey === "name") cmp = a.name.localeCompare(b.name);
    if (sortKey === "duration") cmp = (durationMs(a, now) ?? -1) - (durationMs(b, now) ?? -1);
    return sortDir === "asc" ? cmp : -cmp;
  });

  const headers: { key: SortKey; label: string }[] = [
    { key: "date", label: "Date" },
    { key: "name", label: "Employee" },
    { key: "duration", label: "Duration" },
  ];

  return (
    <div className="rounded-[10px] border border-border bg-surface">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-[15px] font-semibold">Attendance Log</h2>
        <p className="mt-0.5 text-xs text-text-dim">{sorted.length} records</p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim">
              {headers.map((h) => (
                <th key={h.key} className="px-5 py-2.5">
                  <button
                    onClick={() => toggleSort(h.key)}
                    className="flex items-center gap-1 hover:text-text"
                  >
                    {h.label}
                    {sortKey === h.key && <span>{sortDir === "asc" ? "↑" : "↓"}</span>}
                  </button>
                </th>
              ))}
              <th className="px-5 py-2.5">Employee ID</th>
              <th className="px-5 py-2.5">In</th>
              <th className="px-5 py-2.5">Out</th>
              <th className="px-5 py-2.5">Status</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => {
              const ms = durationMs(r, now);
              const status = getRowStatus(r, now);
              return (
                <tr key={`${r.employeeId}-${r.date}-${i}`} className="border-t border-border text-sm hover:bg-surface-2">
                  <td className="whitespace-nowrap px-5 py-3">{r.date}</td>
                  <td className="whitespace-nowrap px-5 py-3">{r.name}</td>
                  <td className="whitespace-nowrap px-5 py-3">{ms !== null ? formatDuration(ms) : "—"}</td>
                  <td className="whitespace-nowrap px-5 py-3 text-text-dim">{r.employeeId}</td>
                  <td className="whitespace-nowrap px-5 py-3">{formatTime(r.inTime)}</td>
                  <td className="whitespace-nowrap px-5 py-3">{formatTime(r.outTime)}</td>
                  <td className="whitespace-nowrap px-5 py-3">
                    <StatusBadge status={status} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {sorted.length === 0 && (
          <div className="px-5 py-10 text-center text-sm text-text-dim">No records match the current filters.</div>
        )}
      </div>
    </div>
  );
}
