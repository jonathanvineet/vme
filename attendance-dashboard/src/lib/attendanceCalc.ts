import { AttendanceRow } from "./types";

export function toDateTime(date: string, time: string): Date {
  return new Date(`${date}T${time}`);
}

export function todayStr(now: Date): string {
  return now.toISOString().slice(0, 10);
}

export function durationMs(row: AttendanceRow, now: Date): number | null {
  if (!row.inTime) return null;
  const inDt = toDateTime(row.date, row.inTime);
  if (row.outTime) {
    return toDateTime(row.date, row.outTime).getTime() - inDt.getTime();
  }
  if (row.date === todayStr(now)) {
    return now.getTime() - inDt.getTime();
  }
  return null; // missing out-time on a past day: incomplete, excluded from totals
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
  const today = todayStr(now);
  return rows
    .filter((r) => r.date === today && r.inTime && !r.outTime)
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
  const start = new Date(now);
  const end = new Date(now);

  if (preset === "this-week") {
    const day = (now.getDay() + 6) % 7; // Monday = 0
    start.setDate(now.getDate() - day);
    return { start: isoDate(start), end: isoDate(end), label: "This week" };
  }

  if (preset === "last-week") {
    const day = (now.getDay() + 6) % 7;
    start.setDate(now.getDate() - day - 7);
    end.setDate(now.getDate() - day - 1);
    return { start: isoDate(start), end: isoDate(end), label: "Last week" };
  }

  if (preset === "this-month") {
    start.setDate(1);
    return { start: isoDate(start), end: isoDate(end), label: "This month" };
  }

  // "last-30"
  start.setDate(now.getDate() - 29);
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
  incompleteDays: number;
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
        incompleteDays: 0,
      });
    }
    const entry = map.get(row.employeeId)!;
    const ms = durationMs(row, now);
    if (ms !== null) {
      entry.totalMs += ms;
      entry.daysPresent += 1;
    } else if (row.inTime && !row.outTime) {
      entry.incompleteDays += 1;
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
