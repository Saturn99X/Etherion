'use client';

import { createStyles } from 'antd-style';
import { Card, Progress, Skeleton, Statistic, Table, Tag } from 'antd';
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
}));

interface Campaign { id: string; name: string; channel: string; status: 'active' | 'paused' | 'completed'; budget?: number; spent?: number; roi?: number }
interface MarketingData {
  totalCampaigns?: number;
  activeCampaigns?: number;
  totalBudget?: number;
  totalSpent?: number;
  avgRoi?: number;
  campaigns?: Campaign[];
}

interface MarketingTeamUIProps {
  data: MarketingData | null;
  loading?: boolean;
}

const statusColors: Record<string, string> = { active: 'success', paused: 'warning', completed: 'default' };

const campaignColumns = [
  { title: 'Campaign', dataIndex: 'name', key: 'name' },
  { title: 'Channel', dataIndex: 'channel', key: 'channel', render: (c: string) => <Tag>{c}</Tag> },
  {
    title: 'Status',
    dataIndex: 'status',
    key: 'status',
    render: (s: string) => <Tag color={statusColors[s]}>{s}</Tag>,
  },
  {
    title: 'Budget',
    key: 'budget',
    render: (_: unknown, r: Campaign) =>
      r.budget ? (
        <Progress
          percent={Math.round(((r.spent ?? 0) / r.budget) * 100)}
          size="small"
          format={() => `$${(r.spent ?? 0).toLocaleString()} / $${r.budget!.toLocaleString()}`}
        />
      ) : '—',
  },
  { title: 'ROI', dataIndex: 'roi', key: 'roi', render: (r?: number) => r != null ? `${r.toFixed(1)}x` : '—' },
];

export const MarketingTeamUI = ({ data, loading }: MarketingTeamUIProps) => {
  const { styles } = useStyles();

  if (loading) return <Skeleton active paragraph={{ rows: 6 }} />;

  return (
    <Flexbox className={styles.container}>
      <h2 className={styles.header}>Marketing Dashboard</h2>

      <Flexbox horizontal className={styles.statsRow} wrap="wrap">
        <Card className={styles.statCard} size="small">
          <Statistic title="Total Campaigns" value={data?.totalCampaigns ?? 0} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Active" value={data?.activeCampaigns ?? 0} valueStyle={{ color: '#52c41a' }} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Total Budget" value={data?.totalBudget ?? 0} prefix="$" />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Avg ROI" value={data?.avgRoi ?? 0} suffix="x" precision={1} />
        </Card>
      </Flexbox>

      <Card title="Campaigns" size="small">
        <Table
          dataSource={data?.campaigns ?? []}
          columns={campaignColumns}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 8, hideOnSinglePage: true }}
        />
      </Card>
    </Flexbox>
  );
};

export default MarketingTeamUI;
