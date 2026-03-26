'use client';

import React, { useMemo } from 'react';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Card, Typography, Empty, Tooltip } from 'antd';
import { PieChart as PieIcon, Activity, Gauge as GaugeIcon, Flame } from 'lucide-react';

const { Text } = Typography;

const useStyles = createStyles(({ token, css }) => ({
  card: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorder};
    border-radius: ${token.borderRadiusLG}px;
  `,
  header: css`
    padding: ${token.paddingMD}px ${token.paddingLG}px;
    border-bottom: 1px solid ${token.colorBorderSecondary};
  `,
  content: css`
    padding: ${token.paddingLG}px;
    display: flex;
    justify-content: center;
    align-items: center;
  `,
  sparklineContainer: css`
    height: 40px;
    display: flex;
    align-items: flex-end;
    gap: 2px;
  `,
  sparklineBar: css`
    flex: 1;
    border-radius: ${token.borderRadiusSM}px ${token.borderRadiusSM}px 0 0;
    background: ${token.colorPrimary};
    opacity: 0.7;
    transition: opacity 0.2s;
    &:hover {
      opacity: 1;
    }
  `,
  gaugeTrack: css`
    fill: none;
    stroke: ${token.colorFillTertiary};
    stroke-width: 12;
  `,
  gaugeArc: css`
    fill: none;
    stroke-width: 12;
    stroke-linecap: round;
    transition: stroke-dashoffset 0.5s ease;
  `,
  gaugeLabel: css`
    font-size: ${token.fontSizeXL}px;
    font-weight: 700;
    fill: ${token.colorText};
    text-anchor: middle;
    dominant-baseline: middle;
  `,
  gaugeSublabel: css`
    font-size: ${token.fontSizeSM}px;
    fill: ${token.colorTextSecondary};
    text-anchor: middle;
    dominant-baseline: middle;
  `,
  metricCard: css`
    background: ${token.colorFillQuaternary};
    border: 1px solid ${token.colorBorderSecondary};
    border-radius: ${token.borderRadius}px;
    padding: ${token.paddingMD}px;
    flex: 1;
    min-width: 120px;
  `,
  metricValue: css`
    font-size: ${token.fontSizeXL}px;
    font-weight: 700;
    color: ${token.colorText};
    line-height: 1.2;
  `,
  metricLabel: css`
    font-size: ${token.fontSizeSM}px;
    color: ${token.colorTextSecondary};
    margin-top: 4px;
  `,
  metricDelta: css`
    font-size: ${token.fontSizeSM}px;
    font-weight: 500;
    margin-top: 2px;
  `,
  heatmapCell: css`
    border-radius: ${token.borderRadiusSM}px;
    cursor: default;
    transition: opacity 0.2s;
    &:hover {
      opacity: 0.8;
    }
  `,
}));

// ─── Pie Chart ────────────────────────────────────────────────────────────────

export interface PieSlice {
  label: string;
  value: number;
  color?: string;
}

export interface PieChartProps {
  title?: string;
  data?: PieSlice[];
  size?: number;
}

const DEFAULT_COLORS = [
  '#4f9cf9', '#45d483', '#f9c74f', '#f76c6c', '#9b72cf',
  '#48cae4', '#fb8500', '#52b788', '#e63946', '#a8dadc',
];

export function PieChart({ title = 'Pie Chart', data = [], size = 160 }: PieChartProps) {
  const { styles, theme } = useStyles();

  const slices = useMemo(() => {
    if (data.length === 0) return [];
    const total = data.reduce((s, d) => s + d.value, 0);
    if (total === 0) return [];
    let angle = -90; // start at 12 o'clock
    return data.map((d, i) => {
      const sweep = (d.value / total) * 360;
      const startAngle = angle;
      angle += sweep;
      const color = d.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length];
      return { ...d, startAngle, sweep, color, pct: Math.round((d.value / total) * 100) };
    });
  }, [data]);

  function polarToXY(cx: number, cy: number, r: number, angleDeg: number) {
    const rad = (angleDeg * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  function describeArc(cx: number, cy: number, r: number, startAngle: number, sweep: number) {
    if (sweep >= 360) sweep = 359.99;
    const start = polarToXY(cx, cy, r, startAngle);
    const end = polarToXY(cx, cy, r, startAngle + sweep);
    const largeArc = sweep > 180 ? 1 : 0;
    return `M ${cx} ${cy} L ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y} Z`;
  }

  if (data.length === 0) {
    return (
      <Card className={styles.card} bordered={false}>
        <Flexbox className={styles.header} horizontal align="center" gap={8}>
          <PieIcon size={20} color={theme.colorPrimary} />
          <Text strong>{title}</Text>
        </Flexbox>
        <div className={styles.content}><Empty description="No data" /></div>
      </Card>
    );
  }

  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.38;

  return (
    <Card className={styles.card} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <PieIcon size={20} color={theme.colorPrimary} />
        <Text strong>{title}</Text>
      </Flexbox>
      <div className={styles.content}>
        <Flexbox horizontal align="center" gap={24} wrap="wrap">
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            {slices.map((s, i) => (
              <Tooltip key={i} title={`${s.label}: ${s.value} (${s.pct}%)`}>
                <path d={describeArc(cx, cy, r, s.startAngle, s.sweep)} fill={s.color} />
              </Tooltip>
            ))}
          </svg>
          <Flexbox gap={6}>
            {slices.map((s, i) => (
              <Flexbox key={i} horizontal align="center" gap={6}>
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
                <Text style={{ fontSize: theme.fontSizeSM }}>{s.label}: {s.pct}%</Text>
              </Flexbox>
            ))}
          </Flexbox>
        </Flexbox>
      </div>
    </Card>
  );
}

// ─── Gauge ────────────────────────────────────────────────────────────────────

export interface GaugeProps {
  title?: string;
  value: number;
  max?: number;
  unit?: string;
  thresholds?: { warn: number; danger: number };
}

export function Gauge({ title = 'Gauge', value, max = 100, unit = '%', thresholds }: GaugeProps) {
  const { styles, theme } = useStyles();
  const clampedValue = Math.min(Math.max(value, 0), max);
  const pct = clampedValue / max;

  // Semi-circle gauge: arc from 180° to 0° (left to right across top half)
  const r = 50;
  const cx = 60;
  const cy = 60;
  const circumference = Math.PI * r; // half-circle arc length
  const arcColor =
    thresholds && value >= thresholds.danger
      ? theme.colorError
      : thresholds && value >= thresholds.warn
      ? theme.colorWarning
      : theme.colorSuccess;

  // SVG stroke trick for semi-circle
  const strokeDasharray = circumference;
  const strokeDashoffset = circumference * (1 - pct);

  return (
    <Card className={styles.card} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <GaugeIcon size={20} color={theme.colorPrimary} />
        <Text strong>{title}</Text>
      </Flexbox>
      <div className={styles.content}>
        <svg width={120} height={70} viewBox="0 0 120 70">
          {/* Track */}
          <path
            d={`M 10 60 A ${r} ${r} 0 0 1 110 60`}
            className={styles.gaugeTrack}
          />
          {/* Value arc */}
          <path
            d={`M 10 60 A ${r} ${r} 0 0 1 110 60`}
            className={styles.gaugeArc}
            stroke={arcColor}
            strokeDasharray={strokeDasharray}
            strokeDashoffset={strokeDashoffset}
            pathLength={circumference}
          />
          <text x={cx} y={cy - 4} className={styles.gaugeLabel}>
            {clampedValue}{unit}
          </text>
          <text x={cx} y={cy + 12} className={styles.gaugeSublabel}>
            of {max}{unit}
          </text>
        </svg>
      </div>
    </Card>
  );
}

// ─── Sparkline ────────────────────────────────────────────────────────────────

export interface SparklineProps {
  data: number[];
  label?: string;
  color?: string;
  height?: number;
}

export function Sparkline({ data = [], label, color, height = 40 }: SparklineProps) {
  const { styles, theme } = useStyles();
  const fill = color ?? theme.colorPrimary;
  const max = data.length === 0 ? 1 : Math.max(...data, 1);

  return (
    <Flexbox gap={4}>
      <div className={styles.sparklineContainer} style={{ height }}>
        {data.map((v, i) => (
          <Tooltip key={i} title={String(v)}>
            <div
              className={styles.sparklineBar}
              style={{ height: `${Math.max(4, (v / max) * 100)}%`, background: fill }}
            />
          </Tooltip>
        ))}
      </div>
      {label && <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>{label}</Text>}
    </Flexbox>
  );
}

// ─── Metric Cards ─────────────────────────────────────────────────────────────

export interface MetricCardData {
  label: string;
  value: string | number;
  delta?: string;
  positive?: boolean;
}

export interface MetricCardsProps {
  metrics: MetricCardData[];
}

export function MetricCards({ metrics = [] }: MetricCardsProps) {
  const { styles, theme } = useStyles();
  return (
    <Flexbox horizontal gap={12} wrap="wrap">
      {metrics.map((m, i) => (
        <div key={i} className={styles.metricCard}>
          <div className={styles.metricValue}>{m.value}</div>
          <div className={styles.metricLabel}>{m.label}</div>
          {m.delta !== undefined && (
            <div
              className={styles.metricDelta}
              style={{ color: m.positive ? theme.colorSuccess : theme.colorError }}
            >
              {m.positive ? '▲' : '▼'} {m.delta}
            </div>
          )}
        </div>
      ))}
    </Flexbox>
  );
}

// ─── Heatmap ──────────────────────────────────────────────────────────────────

export interface HeatmapProps {
  title?: string;
  /** Rows × cols matrix of values (0–1 normalised or raw) */
  data: number[][];
  rowLabels?: string[];
  colLabels?: string[];
  colorHigh?: string;
  colorLow?: string;
}

export function Heatmap({
  title = 'Heatmap',
  data = [],
  rowLabels,
  colLabels,
  colorHigh,
  colorLow,
}: HeatmapProps) {
  const { styles, theme } = useStyles();
  const high = colorHigh ?? theme.colorPrimary;
  const low = colorLow ?? theme.colorFillQuaternary;

  const max = useMemo(() => {
    let m = 0;
    for (const row of data) for (const v of row) if (v > m) m = v;
    return m || 1;
  }, [data]);

  if (data.length === 0) {
    return (
      <Card className={styles.card} bordered={false}>
        <Flexbox className={styles.header} horizontal align="center" gap={8}>
          <Flame size={20} color={theme.colorPrimary} />
          <Text strong>{title}</Text>
        </Flexbox>
        <div className={styles.content}><Empty description="No data" /></div>
      </Card>
    );
  }

  const cellSize = 24;

  return (
    <Card className={styles.card} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <Flame size={20} color={theme.colorPrimary} />
        <Text strong>{title}</Text>
      </Flexbox>
      <div className={styles.content} style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'separate', borderSpacing: 3 }}>
          {colLabels && (
            <thead>
              <tr>
                <th />
                {colLabels.map((c, ci) => (
                  <th key={ci} style={{ fontSize: theme.fontSizeSM, color: theme.colorTextSecondary, fontWeight: 400, padding: '0 2px', textAlign: 'center' }}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {data.map((row, ri) => (
              <tr key={ri}>
                {rowLabels && (
                  <td style={{ fontSize: theme.fontSizeSM, color: theme.colorTextSecondary, paddingRight: 6, whiteSpace: 'nowrap' }}>
                    {rowLabels[ri] ?? ''}
                  </td>
                )}
                {row.map((v, ci) => {
                  const intensity = v / max;
                  return (
                    <td key={ci}>
                      <Tooltip title={`${rowLabels?.[ri] ?? ri}, ${colLabels?.[ci] ?? ci}: ${v}`}>
                        <div
                          className={styles.heatmapCell}
                          style={{
                            width: cellSize,
                            height: cellSize,
                            background: `color-mix(in srgb, ${high} ${Math.round(intensity * 100)}%, ${low})`,
                          }}
                        />
                      </Tooltip>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ─── Activity Feed ────────────────────────────────────────────────────────────

export interface ActivityItem {
  id: string;
  label: string;
  timestamp: string;
  value?: string | number;
}

export interface ActivityFeedProps {
  title?: string;
  items?: ActivityItem[];
}

export function ActivityFeed({ title = 'Activity', items = [] }: ActivityFeedProps) {
  const { styles, theme } = useStyles();
  return (
    <Card className={styles.card} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <Activity size={20} color={theme.colorPrimary} />
        <Text strong>{title}</Text>
      </Flexbox>
      <div className={styles.content} style={{ padding: `${theme.paddingSM}px ${theme.paddingLG}px` }}>
        {items.length === 0 ? (
          <Empty description="No activity" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Flexbox gap={8}>
            {items.map((item) => (
              <Flexbox key={item.id} horizontal align="center" justify="space-between">
                <Flexbox horizontal align="center" gap={8}>
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: theme.colorPrimary, flexShrink: 0 }} />
                  <Text style={{ fontSize: theme.fontSizeSM }}>{item.label}</Text>
                </Flexbox>
                <Flexbox horizontal align="center" gap={8}>
                  {item.value !== undefined && (
                    <Text strong style={{ fontSize: theme.fontSizeSM }}>{item.value}</Text>
                  )}
                  <Text type="secondary" style={{ fontSize: theme.fontSizeSM - 1 }}>
                    {new Date(item.timestamp).toLocaleTimeString()}
                  </Text>
                </Flexbox>
              </Flexbox>
            ))}
          </Flexbox>
        )}
      </div>
    </Card>
  );
}

export default { PieChart, Gauge, Sparkline, MetricCards, Heatmap, ActivityFeed };
