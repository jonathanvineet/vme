"use client";

import { useEffect, useMemo, useState } from "react";
import { AttendanceResponse } from "@/lib/types";
import {
  getCurrentlyIn,
  getDateRangePreset,
  filterByRange,
  totalsByEmployee,
  distinctEmployees,
  formatDuration,
} from "@/lib/attendanceCalc";
import { StatCard } from "./StatCard";
import { CurrentlyIn } from "./CurrentlyIn";
import { FilterBar } from "./FilterBar";
import { SummaryReport } from "./SummaryReport";
import { PersonalReport } from "./PersonalReport";
import { AttendanceList } from "./AttendanceList";

const POLL_MS = 45_000;

export function Dashboard() {
  const [data, setData] = useState<AttendanceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState<Date | null>(null);
  const [preset, setPreset] = useState("this-week");
  const [employeeId, setEmployeeId] = useState("all");

  useEffect(() => {
    setNow(new Date());
    const tick = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const res = await fetch("/api/attendance");
        if (!res.ok) throw new Error(`Request failed: ${res.status}`);
        const json: AttendanceResponse = await res.json();
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load data");
      }
    }

    load();
    const poll = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(poll);
    };
  }, []);

  const rows = data?.rows ?? [];
  const employees = useMemo(() => distinctEmployees(rows), [rows]);

  if (!now || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-text-dim">
        {error ? `Error: ${error}` : "Loading attendance data..."}
      </div>
    );
  }

  const range = getDateRangePreset(preset, now);
  const rangeRows = filterByRange(rows, range);
  const filteredRows = employeeId === "all" ? rangeRows : rangeRows.filter((r) => r.employeeId === employeeId);

  const currentlyIn = getCurrentlyIn(rows, now);
  const weekRange = getDateRangePreset("this-week", now);
  const weekTotals = totalsByEmployee(filterByRange(rows, weekRange), now);
  const weekHoursMs = weekTotals.reduce((sum, t) => sum + t.totalMs, 0);

  const selectedEmployee = employees.find((e) => e.employeeId === employeeId);

  return (
    <div className="mx-auto max-w-[1100px] px-6 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-accent shadow-[0_0_0_3px_var(--accent-dim)]" />
            <h1 className="text-xl font-semibold">Attendance Dashboard</h1>
          </div>
          <p className="mt-1 text-sm text-text-dim">
            {data.source === "mock" ? "Showing sample data — connect Google Sheets to go live." : "Live from Google Sheets"}
            {" · "}
            updated {new Date(data.generatedAt).toLocaleTimeString()}
          </p>
        </div>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Currently In" value={String(currentlyIn.length)} accent="success" />
        <StatCard label="Total Employees" value={String(employees.length)} />
        <StatCard label="Hours This Week" value={formatDuration(weekHoursMs)} accent="accent" />
        <StatCard
          label="Data Source"
          value={data.source === "mock" ? "Sample" : "Sheets"}
          sub={data.source === "mock" ? "for preview only" : "synced from gates"}
        />
      </div>

      <div className="mb-6">
        <CurrentlyIn rows={rows} />
      </div>

      <div className="mb-4">
        <FilterBar
          employees={employees}
          employeeId={employeeId}
          onEmployeeChange={setEmployeeId}
          preset={preset}
          onPresetChange={setPreset}
        />
      </div>

      <div className="mb-6">
        {employeeId === "all" ? (
          <SummaryReport totals={totalsByEmployee(filteredRows, now)} rangeLabel={range.label} />
        ) : (
          <PersonalReport
            rows={filteredRows}
            employeeName={selectedEmployee?.name ?? employeeId}
            rangeLabel={range.label}
            now={now}
          />
        )}
      </div>

      <AttendanceList rows={filteredRows} now={now} />
    </div>
  );
}
