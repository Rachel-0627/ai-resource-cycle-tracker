import { Tag } from "antd";

const COLORS: Record<string, string> = {
  "High Priority": "volcano",
  "Watch Closely": "gold",
  Monitor: "blue",
  Ignore: "default",
};

export default function LabelTag({ label }: { label: string | null | undefined }) {
  if (!label) return <Tag>replay</Tag>;
  return <Tag color={COLORS[label] ?? "default"}>{label}</Tag>;
}
