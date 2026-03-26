'use client';

import { createStyles } from 'antd-style';
import { Card, Skeleton, Statistic, Table, Tag } from 'antd';
import { Flexbox } from 'react-layout-kit';

const useStyles = createStyles(({ token, css }) => ({
  container: css`
    padding: ${token.padding}px;
    background: ${token.colorBgLayout};
    min-height: 100%;
  `,
  header: css`
    margin-bottom: ${token.marginLG}px;
    color: ${token.colorText};
    font-size: ${token.fontSizeLG}px;
    font-weight: 600;
  `,
  statsRow: css`
    gap: ${token.margin}px;
    margin-bottom: ${token.marginLG}px;
  `,
  statCard: css`
    flex: 1;
    min-width: 140px;
  `,
  metricBar: css`
    height: 8px;
    border-radius: 4px;
    background: ${token.colorPrimary};
    margin-top: 4px;
  `,
}));

interface MetricRow { name: string; value: number; trend: 'up' | 'down' | 'flat'; unit?: string }
interface AnalyticsData {
  totalUsers?: number;
  activeUsers?: number;
  pageViews?: number;
  avgSessionDuration?: number;
  bounceRate?: number;
  metrics?: MetricRow[];
}

interface AnalyticsTeamUIProps {
  data: AnalyticsData | null;
  loading?: boolean;
}

const trendColors: Record<string, string> = { up: 'green', down: 'red', flat: 'default' };

const metricColumns = [
  { title: 'Metric', dataIndex: 'name', key: 'name' },
  {
    title: 'Value',
    dataIndex: 'value',
    key: 'value',
    render: (v: number, r: MetricRow) => `${v.toLocaleString()}${r.unit ?? ''}`,
  },
  {
    title: 'Trend',
    dataIndex: 'trend',
    key: 'trend',
    render: (t: string) => <Tag color={trendColors[t]}>{t}</Tag>,
  },
];

export const AnalyticsTeamUI = ({ data, loading }: AnalyticsTeamUIProps) => {
  const { styles } = useStyles();

  if (loading) return <Skeleton active paragraph={{ rows: 6 }} />;

  return (
    <Flexbox className={styles.container}>
      <h2 className={styles.header}>Analytics Dashboard</h2>

      <Flexbox horizontal className={styles.statsRow} wrap="wrap">
        <Card className={styles.statCard} size="small">
          <Statistic title="Total Users" value={data?.totalUsers ?? 0} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Active Users" value={data?.activeUsers ?? 0} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Page Views" value={data?.pageViews ?? 0} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Bounce Rate" value={data?.bounceRate ?? 0} suffix="%" precision={1} />
        </Card>
      </Flexbox>

      {(data?.metrics ?? []).length > 0 && (
        <Card title="Key Metrics" size="small">
          <Table
            dataSource={data?.metrics ?? []}
            columns={metricColumns}
            rowKey="name"
            size="small"
            pagination={false}
          />
        </Card>
      )}
    </Flexbox>
  );
};

export default AnalyticsTeamUI;
