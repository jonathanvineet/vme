import "server-only";
import { google } from "googleapis";
import { AttendanceRow } from "./types";
import { generateMockRows } from "./mockData";

const SHEET_TAB = "Attendance";

function getCredentials() {
  const json = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
  const sheetId = process.env.GOOGLE_SHEET_ID;
  if (!json || !sheetId) return null;

  try {
    const credentials = JSON.parse(json);
    return { credentials, sheetId };
  } catch {
    throw new Error(
      "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON. Paste the full service-account key file contents."
    );
  }
}

async function fetchFromSheet(sheetId: string, credentials: object): Promise<AttendanceRow[]> {
  const auth = new google.auth.GoogleAuth({
    credentials,
    scopes: ["https://www.googleapis.com/auth/spreadsheets.readonly"],
  });

  const sheets = google.sheets({ version: "v4", auth });
  const result = await sheets.spreadsheets.values.get({
    spreadsheetId: sheetId,
    range: `${SHEET_TAB}!A2:E`,
  });

  const values = result.data.values ?? [];

  return values
    .filter((row) => row[0])
    .map((row) => ({
      employeeId: String(row[0] ?? ""),
      name: String(row[1] ?? ""),
      date: String(row[2] ?? ""),
      inTime: row[3] ? String(row[3]) : null,
      outTime: row[4] ? String(row[4]) : null,
    }));
}

/**
 * Reads attendance rows from the Google Sheet. Falls back to generated
 * mock data when credentials aren't configured, so the dashboard is
 * viewable before the Google Cloud setup is done.
 */
export async function getAttendanceRows(): Promise<{
  rows: AttendanceRow[];
  source: "sheets" | "mock";
}> {
  const config = getCredentials();

  if (!config) {
    return { rows: generateMockRows(), source: "mock" };
  }

  const rows = await fetchFromSheet(config.sheetId, config.credentials);
  return { rows, source: "sheets" };
}
