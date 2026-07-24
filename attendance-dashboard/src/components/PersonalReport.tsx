import { AttendanceRow } from "@/lib/types";
import { durationMs, formatDuration, formatTime, getRowStatus } from "@/lib/attendanceCalc";
import { StatusBadge } from "./StatusBadge";

export function PersonalReport({
  rows,
  employeeName,
  rangeLabel,
  now,
}: {
  rows: AttendanceRow[];
  employeeName: string;
  rangeLabel: string;
  now: Date;
}) {
  const sorted = [...rows].sort((a, b) => b.date.localeCompare(a.date));
  const totalMs = sorted.reduce((sum, r) => sum + (durationMs(r, now) ?? 0), 0);

  return (
    <div className="rounded-[10px] border border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div>
          <h2 className="text-[15px] font-semibold">{employeeName} — Personal Report</h2>
          <p className="mt-0.5 text-xs text-text-dim">{rangeLabel}</p>
        </div>
        <div className="text-right">
          <div className="text-xs text-text-dim">Total</div>
          <div className="text-sm font-semibold">{formatDuration(totalMs)}</div>
        </div>
      </div>

      {sorted.length === 0 ? (
        <div className="px-5 py-10 text-center text-sm text-text-dim">No records in this range.</div>
      ) : (
        <table className="w-full">
          <thead>
            <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-text-dim">
              <th className="px-5 py-2.5">Date</th>
              <th className="px-5 py-2.5">In</th>
              <th className="px-5 py-2.5">Out</th>
              <th className="px-5 py-2.5">Duration</th>
              <th className="px-5 py-2.5">Status</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const ms = durationMs(r, now);
              const status = getRowStatus(r, now);
              return (
                <tr key={r.date} className="border-t border-border text-sm hover:bg-surface-2">
                  <td className="px-5 py-3">{r.date}</td>
                  <td className="px-5 py-3">{formatTime(r.inTime)}</td>
                  <td className="px-5 py-3">{formatTime(r.outTime)}</td>
                  <td className="px-5 py-3">{ms !== null ? formatDuration(ms) : "—"}</td>
                  <td className="px-5 py-3">
                    <StatusBadge status={status} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
