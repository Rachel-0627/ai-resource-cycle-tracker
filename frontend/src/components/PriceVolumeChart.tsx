import ReactECharts from "echarts-for-react";

import type { PriceBar, Signal } from "../api/types";

const SIGNAL_COLORS: Record<string, string> = {
  REL_VOL_SPIKE: "#722ed1",
  BREAKOUT_60D: "#13c2c2",
  BREAKOUT_252D: "#2f54eb",
  KEY_ANNOUNCEMENT: "#eb2f96",
  SCORE_CROSS_UP: "#fa8c16",
};

export default function PriceVolumeChart({
  bars,
  signals,
}: {
  bars: PriceBar[];
  signals: Signal[];
}) {
  const dates = bars.map((b) => b.date);
  const candles = bars.map((b) => [b.open, b.close, b.low, b.high]);
  const volumes = bars.map((b, i) => ({
    value: b.volume,
    itemStyle: { color: i > 0 && b.close >= bars[i - 1].close ? "#26a69a99" : "#ef535099" },
  }));

  const markPoints = signals
    .filter((s) => dates.includes(s.date))
    .map((s) => {
      const bar = bars[dates.indexOf(s.date)];
      return {
        coord: [s.date, bar.high],
        value: s.signal_type.split("_")[0][0] + (s.signal_type.includes("BREAKOUT") ? "B" : ""),
        itemStyle: { color: SIGNAL_COLORS[s.signal_type] ?? "#888" },
        tooltipText: `${s.date} ${s.signal_type}: ${s.reason}`,
      };
    });

  const option = {
    animation: false,
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: [
      { left: 60, right: 20, top: 20, height: "55%" },
      { left: 60, right: 20, top: "72%", height: "18%" },
    ],
    xAxis: [
      { type: "category", data: dates, boundaryGap: true, axisLine: { onZero: false } },
      { type: "category", gridIndex: 1, data: dates, axisLabel: { show: false } },
    ],
    yAxis: [
      { scale: true, splitArea: { show: false } },
      { gridIndex: 1, splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 55, end: 100 },
      { type: "slider", xAxisIndex: [0, 1], top: "93%", start: 55, end: 100 },
    ],
    series: [
      {
        name: "price",
        type: "candlestick",
        data: candles,
        itemStyle: {
          color: "#26a69a",
          color0: "#ef5350",
          borderColor: "#26a69a",
          borderColor0: "#ef5350",
        },
        markPoint: {
          symbol: "pin",
          symbolSize: 34,
          label: { fontSize: 9, color: "#fff" },
          data: markPoints,
          tooltip: {
            formatter: (p: { data?: { tooltipText?: string } }) => p.data?.tooltipText ?? "",
          },
        },
      },
      { name: "volume", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: volumes },
    ],
  };

  return <ReactECharts option={option} style={{ height: 420 }} notMerge />;
}
