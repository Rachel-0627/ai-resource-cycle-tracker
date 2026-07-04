export default function Pct({
  value,
  digits = 1,
  suffix = "%",
}: {
  value: number | null | undefined;
  digits?: number;
  suffix?: string;
}) {
  if (value === null || value === undefined) return <span style={{ color: "#999" }}>–</span>;
  const color = value > 0 ? "#3f8600" : value < 0 ? "#cf1322" : "#666";
  return (
    <span style={{ color }}>
      {value > 0 ? "+" : ""}
      {value.toFixed(digits)}
      {suffix}
    </span>
  );
}
