'use client';

import React, { useMemo } from 'react';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Card, Typography, Empty } from 'antd';
import { BarChart3, TrendingUp } from 'lucide-react';

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
  `,
  barContainer: css`
    display: flex;
    align-items: flex-end;
    gap: ${token.marginSM}px;
    height: 120px;
  `,
  bar: css`
    flex: 1;
    background: linear-gradient(180deg, ${token.colorPrimary}, ${token.colorPrimaryHover});
    border-radius: ${token.borderRadiusSM}px ${token.borderRadiusSM}px 0 0;
    transition: all 0.3s ease;
    cursor: pointer;
    
    &:hover {
      opacity: 0.8;
      transform: translateY(-2px);
    }
  `,
  lineContainer: css`
    position: relative;
    height: 120px;
    border-left: 1px solid ${token.colorBorder};
    border-bottom: 1px solid ${token.colorBorder};
  `,
  linePath: css`
    stroke: ${token.colorPrimary};
    stroke-width: 2;
    fill: none;
  `,
  linePoint: css`
    fill: ${token.colorPrimary};
  `,
  legend: css`
    display: flex;
    flex-wrap: wrap;
    gap: ${token.marginMD}px;
    margin-top: ${token.marginMD}px;
  `,
  legendItem: css`
    display: flex;
    align-items: center;
    gap: ${token.marginXS}px;
    font-size: ${token.fontSizeSM}px;
  `,
  legendDot: css`
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: ${token.colorPrimary};
  `,
}));

export interface ChartDataPoint {
  label: string;
  value: number;
}

export interface ChartProps {
  title?: string;
  data?: ChartDataPoint[];
}

export function BarChart({ title = 'Bar Chart', data = [] }: ChartProps) {
  const { styles, theme } = useStyles();

  const maxValue = useMemo(() => {
    if (data.length === 0) return 100;
    return Math.max(...data.map((d) => d.value));
  }, [data]);

  if (data.length === 0) {
    return (
      <Card className={styles.card} bordered={false}>
        <Flexbox className={styles.header} horizontal align="center" gap={8}>
          <BarChart3 size={20} color={theme.colorPrimary} />
          <Text strong>{title}</Text>
        </Flexbox>
        <div className={styles.content}>
          <Empty description="No data available" />
        </div>
      </Card>
    );
  }

  return (
    <Card className={styles.card} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <BarChart3 size={20} color={theme.colorPrimary} />
        <Text strong>{title}</Text>
      </Flexbox>
      <div className={styles.content}>
        <div className={styles.barContainer}>
          {data.map((point, index) => {
            const heightPercent = (point.value / maxValue) * 100;
            return (
              <div
                key={index}
                className={styles.bar}
                style={{ height: `${heightPercent}%` }}
                title={`${point.label}: ${point.value}`}
              />
            );
          })}
        </div>
        <div className={styles.legend}>
          {data.map((point, index) => (
            <div key={index} className={styles.legendItem}>
              <div className={styles.legendDot} />
              <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                {point.label}: {point.value}
              </Text>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

export function LineChart({ title = 'Line Chart', data = [] }: ChartProps) {
  const { styles, theme } = useStyles();

  const { maxValue, points, pathD } = useMemo(() => {
    if (data.length === 0) return { maxValue: 100, points: [], pathD: '' };

    const max = Math.max(...data.map((d) => d.value));
    const width = 100;
    const height = 100;
    const stepX = width / (data.length - 1 || 1);

    const pts = data.map((point, index) => {
      const x = index * stepX;
      const y = height - (point.value / max) * height;
      return { x, y, label: point.label, value: point.value };
    });

    const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

    return { maxValue: max, points: pts, pathD: path };
  }, [data]);

  if (data.length === 0) {
    return (
      <Card className={styles.card} bordered={false}>
        <Flexbox className={styles.header} horizontal align="center" gap={8}>
          <TrendingUp size={20} color={theme.colorPrimary} />
          <Text strong>{title}</Text>
        </Flexbox>
        <div className={styles.content}>
          <Empty description="No data available" />
        </div>
      </Card>
    );
  }

  return (
    <Card className={styles.card} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <TrendingUp size={20} color={theme.colorPrimary} />
        <Text strong>{title}</Text>
      </Flexbox>
      <div className={styles.content}>
        <svg viewBox="0 0 100 100" className={styles.lineContainer} preserveAspectRatio="none">
          <path d={pathD} className={styles.linePath} />
          {points.map((point, index) => (
            <circle
              key={index}
              cx={point.x}
              cy={point.y}
              r={2}
              className={styles.linePoint}
            >
              <title>{`${point.label}: ${point.value}`}</title>
            </circle>
          ))}
        </svg>
        <div className={styles.legend}>
          {data.map((point, index) => (
            <div key={index} className={styles.legendItem}>
              <div className={styles.legendDot} />
              <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                {point.label}: {point.value}
              </Text>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

export default { BarChart, LineChart };
