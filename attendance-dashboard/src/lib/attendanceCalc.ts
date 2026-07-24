import { AttendanceRow } from "./types";

// The gates write wall-clock date/time in the business's local timezone
// (India). The dashboard may run anywhere (Vercel defaults to UTC), so
// every "today" / date-range calculation below is pinned to this offset
// instead of the host's timezone — otherwise a check-in at, say, 00:37 IST
// falls on the *previous* calendar day in UTC and silently vanishes from
// "today" / "this week" views.
const BUSINESS_UTC_OFFSET = "+05:30";
const BUSINESS_OFFSET_MS = 5.5 * 60 * 60 * 1000;

export function toDateTime(date: string, time: string): Date {
  return new Date(`${date}T${time}${BUSINESS_UTC_OFFSET}`);
}

// Returns a Date whose UTC getters read as the business timezone's
// wall-clock fields, regardless of the host machine's own timezone.
function businessShifted(now: Date): Date {
  return new Date(now.getTime() + BUSINESS_OFFSET_MS);
}

export function todayStr(now: Date): string {
  return businessShifted(now).toISOString().slice(0, 10);
}

export type RowStatus =
  | "currently-in"
  | "present"
  | "missing-checkout"
  | "missing-checkin";

export function getRowStatus(row: AttendanceRow, now: Date): RowStatus {
  if (row.inTime && row.outTime) return "present";
  if (row.inTime && !row.outTime) {
    return row.date === todayStr(now) ? "currently-in" : "missing-checkout";
  }
  // !row.inTime && row.outTime (a row with neither shouldn't exist upstream)
  return "missing-checkin";
}

export function durationMs(row: AttendanceRow, now: Date): number | null {
  const status = getRowStatus(row, now);

  if (status === "missing-checkin") return null; // no in-time: nothing to measure from

  if (!row.inTime) return null;
  const inDt = toDateTime(row.date, row.inTime);

  if (status === "present") {
    return toDateTime(row.date, row.outTime as string).getTime() - inDt.getTime();
  }

  if (status === "currently-in") {
    return now.getTime() - inDt.getTime();
  }

  return null; // missing-checkout on a past day: can't know when they left
}

export function formatDuration(ms: number): string {
  const totalMinutes = Math.max(0, Math.floor(ms / 60000));
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h === 0) return `${m}m`;
  return `${h}h ${m}m`;
}

export function formatTime(time: string | null): string {
  if (!time) return "—";
  const [h, m] = time.split(":");
  const hour = parseInt(h, 10);
  const period = hour >= 12 ? "PM" : "AM";
  const displayHour = hour % 12 === 0 ? 12 : hour % 12;
  return `${displayHour}:${m} ${period}`;
}

export type CurrentlyInEntry = {
  employeeId: string;
  name: string;
  inTime: string;
  durationMs: number;
};

export function getCurrentlyIn(rows: AttendanceRow[], now: Date): CurrentlyInEntry[] {
  return rows
    .filter((r) => getRowStatus(r, now) === "currently-in")
    .map((r) => ({
      employeeId: r.employeeId,
      name: r.name,
      inTime: r.inTime as string,
      durationMs: durationMs(r, now) ?? 0,
    }))
    .sort((a, b) => b.durationMs - a.durationMs);
}

export type DateRange = { start: string; end: string; label: string };

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function getDateRangePreset(preset: string, now: Date): DateRange {
  // Do all calendar math on the business-shifted instant, then read its
  // UTC fields — this yields IST wall-clock date/day-of-week no matter
  // where the server process actually runs.
  const shifted = businessShifted(now);
  const start = new Date(shifted);
  const end = new Date(shifted);

  if (preset === "this-week") {
    const day = (shifted.getUTCDay() + 6) % 7; // Monday = 0
    start.setUTCDate(shifted.getUTCDate() - day);
    return { start: isoDate(start), end: isoDate(end), label: "This week" };
  }

  if (preset === "last-week") {
    const day = (shifted.getUTCDay() + 6) % 7;
    start.setUTCDate(shifted.getUTCDate() - day - 7);
    end.setUTCDate(shifted.getUTCDate() - day - 1);
    return { start: isoDate(start), end: isoDate(end), label: "Last week" };
  }

  if (preset === "this-month") {
    start.setUTCDate(1);
    return { start: isoDate(start), end: isoDate(end), label: "This month" };
  }

  // "last-30"
  start.setUTCDate(shifted.getUTCDate() - 29);
  return { start: isoDate(start), end: isoDate(end), label: "Last 30 days" };
}

export function filterByRange(rows: AttendanceRow[], range: DateRange): AttendanceRow[] {
  return rows.filter((r) => r.date >= range.start && r.date <= range.end);
}

export type EmployeeTotal = {
  employeeId: string;
  name: string;
  totalMs: number;
  daysPresent: number;
  missingCheckout: number;
  missingCheckin: number;
};

export function totalsByEmployee(rows: AttendanceRow[], now: Date): EmployeeTotal[] {
  const map = new Map<string, EmployeeTotal>();

  for (const row of rows) {
    if (!map.has(row.employeeId)) {
      map.set(row.employeeId, {
        employeeId: row.employeeId,
        name: row.name,
        totalMs: 0,
        daysPresent: 0,
        missingCheckout: 0,
        missingCheckin: 0,
      });
    }
    const entry = map.get(row.employeeId)!;
    const status = getRowStatus(row, now);
    const ms = durationMs(row, now);

    if (ms !== null) {
      entry.totalMs += ms;
      entry.daysPresent += 1;
    } else if (status === "missing-checkout") {
      entry.missingCheckout += 1;
    } else if (status === "missing-checkin") {
      entry.missingCheckin += 1;
    }
  }

  return Array.from(map.values()).sort((a, b) => b.totalMs - a.totalMs);
}

export function distinctEmployees(rows: AttendanceRow[]): { employeeId: string; name: string }[] {
  const map = new Map<string, string>();
  for (const row of rows) {
    if (!map.has(row.employeeId)) map.set(row.employeeId, row.name);
  }
  return Array.from(map.entries())
    .map(([employeeId, name]) => ({ employeeId, name }))
    .sort((a, b) => a.name.localeCompare(b.name));
}
