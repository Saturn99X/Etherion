'use client';

import { createStyles } from 'antd-style';
import { Badge, Card, Skeleton, Statistic, Table, Tag } from 'antd';
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
  pipelineStage: css`
    padding: ${token.paddingSM}px ${token.padding}px;
    background: ${token.colorBgContainer};
    border-radius: ${token.borderRadius}px;
    border: 1px solid ${token.colorBorder};
    flex: 1;
    text-align: center;
    font-size: ${token.fontSizeSM}px;
    color: ${token.colorTextSecondary};
  `,
  stageCount: css`
    font-size: ${token.fontSizeLG}px;
    font-weight: 600;
    color: ${token.colorText};
  `,
}));

interface PipelineStage { stage: string; count: number; value: number }
interface TopDeal { id: string; name: string; value: number; stage: string; probability: number }
interface SalesData {
  totalDeals?: number;
  activeDeals?: number;
  closedDeals?: number;
  totalRevenue?: number;
  conversionRate?: number;
  pipeline?: PipelineStage[];
  topDeals?: TopDeal[];
}

interface SalesTeamUIProps {
  data: SalesData | null;
  loading?: boolean;
}

const dealColumns = [
  { title: 'Deal', dataIndex: 'name', key: 'name' },
  { title: 'Value', dataIndex: 'value', key: 'value', render: (v: number) => `$${v.toLocaleString()}` },
  { title: 'Stage', dataIndex: 'stage', key: 'stage', render: (s: string) => <Tag>{s}</Tag> },
  {
    title: 'Probability',
    dataIndex: 'probability',
    key: 'probability',
    render: (p: number) => <Badge status={p >= 70 ? 'success' : p >= 40 ? 'processing' : 'default'} text={`${p}%`} />,
  },
];

export const SalesTeamUI = ({ data, loading }: SalesTeamUIProps) => {
  const { styles } = useStyles();

  if (loading) return <Skeleton active paragraph={{ rows: 6 }} />;

  return (
    <Flexbox className={styles.container}>
      <h2 className={styles.header}>Sales Dashboard</h2>

      <Flexbox horizontal className={styles.statsRow} wrap="wrap">
        <Card className={styles.statCard} size="small">
          <Statistic title="Total Deals" value={data?.totalDeals ?? 0} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Active Deals" value={data?.activeDeals ?? 0} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Total Revenue" value={data?.totalRevenue ?? 0} prefix="$" />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Conversion Rate" value={data?.conversionRate ?? 0} suffix="%" precision={1} />
        </Card>
      </Flexbox>

      <Card title="Pipeline" size="small" style={{ marginBottom: 16 }}>
        <Flexbox horizontal gap={8} wrap="wrap">
          {(data?.pipeline ?? []).map((s) => (
            <Flexbox key={s.stage} className={styles.pipelineStage}>
              <span>{s.stage}</span>
              <span className={styles.stageCount}>{s.count}</span>
              <span>${(s.value / 1000).toFixed(0)}k</span>
            </Flexbox>
          ))}
        </Flexbox>
      </Card>

      <Card title="Top Deals" size="small">
        <Table
          dataSource={data?.topDeals ?? []}
          columns={dealColumns}
          rowKey="id"
          size="small"
          pagination={false}
        />
      </Card>
    </Flexbox>
  );
};

export default SalesTeamUI;
