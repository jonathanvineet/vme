import { NextResponse } from "next/server";
import { getAttendanceRows } from "@/lib/sheets";
import { AttendanceResponse } from "@/lib/types";

// Decouples Sheets API traffic from dashboard viewer count: no matter how
// many people load the page, this route hits Google at most once per
// window, well under the 60 req/min/user quota.
export const revalidate = 30;

export async function GET() {
  try {
    const { rows, source } = await getAttendanceRows();
    const body: AttendanceResponse = {
      rows,
      source,
      generatedAt: new Date().toISOString(),
    };
    return NextResponse.json(body);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to load attendance data" },
      { status: 500 }
    );
  }
}
