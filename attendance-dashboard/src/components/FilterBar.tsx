"use client";

const PRESETS = [
  { key: "this-week", label: "This week" },
  { key: "last-week", label: "Last week" },
  { key: "this-month", label: "This month" },
  { key: "last-30", label: "Last 30 days" },
];

export function FilterBar({
  employees,
  employeeId,
  onEmployeeChange,
  preset,
  onPresetChange,
}: {
  employees: { employeeId: string; name: string }[];
  employeeId: string;
  onEmployeeChange: (id: string) => void;
  preset: string;
  onPresetChange: (preset: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-[10px] border border-border bg-surface px-4 py-3">
      <div className="flex items-center gap-1.5">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            onClick={() => onPresetChange(p.key)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              preset === p.key
                ? "bg-accent text-white"
                : "text-text-dim hover:bg-surface-2 hover:text-text"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <label className="text-xs text-text-dim">Employee</label>
        <select
          value={employeeId}
          onChange={(e) => onEmployeeChange(e.target.value)}
          className="rounded-md border border-border bg-surface-2 px-3 py-1.5 text-xs text-text outline-none focus:border-accent"
        >
          <option value="all">All employees</option>
          {employees.map((e) => (
            <option key={e.employeeId} value={e.employeeId}>
              {e.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
