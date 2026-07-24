export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "success" | "warning";
}) {
  const styles = {
    neutral: "bg-accent-dim text-[#a9bcff]",
    success: "bg-success-dim text-success",
    warning: "bg-[rgba(245,165,36,0.12)] text-warning",
  }[tone];

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${styles}`}>
      {children}
    </span>
  );
}
