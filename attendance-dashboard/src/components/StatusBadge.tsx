import { RowStatus } from "@/lib/attendanceCalc";
import { Badge } from "./Badge";

const LABELS: Record<RowStatus, string> = {
  "currently-in": "Currently in",
  present: "Present",
  "missing-checkout": "Missing checkout",
  "missing-checkin": "Missing checkin",
};

const TONES: Record<RowStatus, "success" | "neutral" | "warning"> = {
  "currently-in": "success",
  present: "neutral",
  "missing-checkout": "warning",
  "missing-checkin": "warning",
};

export function StatusBadge({ status }: { status: RowStatus }) {
  return <Badge tone={TONES[status]}>{LABELS[status]}</Badge>;
}
