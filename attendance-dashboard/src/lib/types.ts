export type AttendanceRow = {
  employeeId: string;
  name: string;
  date: string; // YYYY-MM-DD
  inTime: string | null; // HH:MM:SS
  outTime: string | null; // HH:MM:SS
};

export type AttendanceResponse = {
  rows: AttendanceRow[];
  generatedAt: string;
  source: "sheets" | "mock";
};
