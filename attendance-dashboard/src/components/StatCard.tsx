export function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: "success" | "accent";
}) {
  return (
    <div className="rounded-[10px] border border-border bg-surface p-5">
      <div className="text-xs font-medium uppercase tracking-wide text-text-dim">
        {label}
      </div>
      <div
        className={`mt-2 text-[28px] font-semibold leading-none ${
          accent === "success" ? "text-success" : accent === "accent" ? "text-accent" : "text-text"
        }`}
      >
        {value}
      </div>
      {sub && <div className="mt-1.5 text-xs text-text-dim">{sub}</div>}
    </div>
  );
}
