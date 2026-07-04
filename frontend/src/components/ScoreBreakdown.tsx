import { Descriptions, Tag, Typography } from "antd";

import type { ScoreBrief } from "../api/types";

const { Text } = Typography;

interface FundingComponent {
  points: number;
  max: number;
  value?: number | null;
  note?: string | null;
  window?: number | null;
  days?: number;
  day_change_pct?: number | null;
  dollar_turnover?: number;
}

interface AnnComponentItem {
  headline: string;
  type: string;
  base: number;
  age_days: number;
  decay: number;
  price_sensitive: boolean;
  effective: number;
}

/** Renders the persisted components JSON — the explainability contract. */
export default function ScoreBreakdown({ score }: { score: ScoreBrief }) {
  const comps = (score.components ?? {}) as Record<string, unknown>;
  const funding = (comps.funding ?? {}) as Record<string, FundingComponent>;
  const announcement = (comps.announcement ?? {}) as {
    announcements?: AnnComponentItem[];
    best?: number;
    bonus?: number;
    note?: string;
  };
  const commodity = (comps.commodity ?? {}) as {
    instrument?: string;
    r20_pct?: number;
    r60_pct?: number;
    note?: string;
  };
  const resource = (comps.resource ?? {}) as { value?: number; source?: string };
  const risk = (comps.risk ?? {}) as { value?: number; source?: string };

  const fundingRow = (name: string, c?: FundingComponent, extra?: string) =>
    c ? (
      <div key={name}>
        <Text strong>
          {name}: {c.points}/{c.max}
        </Text>{" "}
        {extra && <Text type="secondary">{extra}</Text>}
        {c.note && <Tag style={{ marginLeft: 6 }}>{c.note}</Tag>}
      </div>
    ) : null;

  return (
    <Descriptions column={1} size="small" bordered>
      <Descriptions.Item label={`Funding ${score.funding_score.toFixed(0)}`}>
        {fundingRow("放量", funding.rel_vol, funding.rel_vol?.value != null ? `rel_vol=${funding.rel_vol.value}x, 当日${funding.rel_vol.day_change_pct ?? "-"}%, 成交额A$${((funding.rel_vol.dollar_turnover ?? 0) / 1000).toFixed(0)}k` : undefined)}
        {fundingRow("突破", funding.breakout, funding.breakout?.window ? `${funding.breakout.window}日新高` : "无突破")}
        {fundingRow("连涨", funding.consecutive_up, `${funding.consecutive_up?.days ?? 0}天`)}
        {fundingRow("量能趋势", funding.vol_trend, funding.vol_trend?.value != null ? `MA5/MA20=${funding.vol_trend.value}` : undefined)}
      </Descriptions.Item>
      <Descriptions.Item label={`Announcement ${score.announcement_score.toFixed(0)}`}>
        {announcement.note === "no_announcements_30d" && <Text type="secondary">30 天内无公告(安静=无故事)</Text>}
        {(announcement.announcements ?? []).slice(0, 5).map((a, i) => (
          <div key={i}>
            <Tag>{a.type}</Tag>
            {a.price_sensitive && "⚡"} {a.headline}{" "}
            <Text type="secondary">
              base {a.base} × decay {a.decay}
              {a.price_sensitive ? " × 1.2" : ""} = {a.effective}
            </Text>
          </div>
        ))}
        {announcement.bonus ? <div><Text type="secondary">bonus +{announcement.bonus}</Text></div> : null}
      </Descriptions.Item>
      <Descriptions.Item label={`Resource ${score.resource_score.toFixed(0)}`}>
        <Text type="secondary">{resource.source === "manual_override" ? "手动覆盖值" : "中性默认 50(MVP-1 不做自动资源估值)"}</Text>
      </Descriptions.Item>
      <Descriptions.Item label={`Commodity ${score.commodity_score.toFixed(0)}`}>
        {commodity.note ? (
          <Text type="secondary">数据不足,取中性 50</Text>
        ) : (
          <Text type="secondary">
            {commodity.instrument}: 20日 {commodity.r20_pct}%, 60日 {commodity.r60_pct}%
          </Text>
        )}
      </Descriptions.Item>
      <Descriptions.Item label={`Risk ${score.risk_score.toFixed(0)}`}>
        <Text type="secondary">{risk.source === "manual_override" ? "手动覆盖值(越高越安全)" : "中性默认 50"}</Text>
      </Descriptions.Item>
    </Descriptions>
  );
}
