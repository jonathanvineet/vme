import { EmployeeTotal, formatDuration } from "@/lib/attendanceCalc";
import { Badge } from "./Badge";

export function SummaryReport({
  totals,
  rangeLabel,
}: {
  totals: EmployeeTotal[];
  rangeLabel: string;
}) {
  const maxMs = Math.max(1, ...totals.map((t) => t.totalMs));

  return (
    <div className="rounded-[10px] border border-border bg-surface">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-[15px] font-semibold">Summary Report</h2>
        <p className="mt-0.5 text-xs text-text-dim">Total time logged per employee · {rangeLabel}</p>
      </div>

      {totals.length === 0 ? (
        <div className="px-5 py-10 text-center text-sm text-text-dim">No attendance in this range.</div>
      ) : (
        <ul className="divide-y divide-border">
          {totals.map((t) => (
            <li key={t.employeeId} className="px-5 py-3.5">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-medium">{t.name}</span>
                  <span className="text-xs text-text-dim">{t.employeeId}</span>
                  {t.missingCheckout > 0 && (
                    <Badge tone="warning">{t.missingCheckout} missing checkout</Badge>
                  )}
                  {t.missingCheckin > 0 && (
                    <Badge tone="warning">{t.missingCheckin} missing checkin</Badge>
                  )}
                </div>
                <div className="flex items-baseline gap-3">
                  <span className="text-xs text-text-dim">{t.daysPresent} days</span>
                  <span className="text-sm font-semibold">{formatDuration(t.totalMs)}</span>
                </div>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${Math.max(2, (t.totalMs / maxMs) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
