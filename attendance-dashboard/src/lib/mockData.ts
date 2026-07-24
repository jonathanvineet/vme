import { AttendanceRow } from "./types";

// Only used when GOOGLE_SHEET_ID / GOOGLE_SERVICE_ACCOUNT_JSON aren't set,
// so the dashboard is viewable during local development before the Sheet
// is wired up.
const EMPLOYEES = [
  { employeeId: "E1001", name: "Raghav Menon" },
  { employeeId: "E1002", name: "Vineet Jonathan" },
  { employeeId: "E1003", name: "Aisha Khan" },
  { employeeId: "E1004", name: "Dev Patel" },
  { employeeId: "E1005", name: "Sara Thomas" },
];

function fmtDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function fmtTime(h: number, m: number): string {
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`;
}

export function generateMockRows(): AttendanceRow[] {
  const rows: AttendanceRow[] = [];
  const today = new Date();

  for (let dayOffset = 13; dayOffset >= 0; dayOffset--) {
    const d = new Date(today);
    d.setDate(d.getDate() - dayOffset);
    const dow = d.getDay();
    if (dow === 0 || dow === 6) continue; // skip weekends

    for (const emp of EMPLOYEES) {
      if (Math.random() < 0.12) continue; // occasional absence

      const inHour = 8 + Math.floor(Math.random() * 2);
      const inMin = Math.floor(Math.random() * 60);
      const outHour = 17 + Math.floor(Math.random() * 3);
      const outMin = Math.floor(Math.random() * 60);

      const isToday = dayOffset === 0;
      const stillIn = isToday && Math.random() < 0.4;

      rows.push({
        employeeId: emp.employeeId,
        name: emp.name,
        date: fmtDate(d),
        inTime: fmtTime(inHour, inMin),
        outTime: stillIn ? null : fmtTime(outHour, outMin),
      });
    }
  }

  return rows;
}
