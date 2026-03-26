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
}));

interface Task { id: string; title: string; priority: 'low' | 'medium' | 'high' | 'critical'; status: string; assignee?: string }
interface DevelopmentData {
  openIssues?: number;
  closedIssues?: number;
  pullRequests?: number;
  deployments?: number;
  testCoverage?: number;
  tasks?: Task[];
}

interface DevelopmentTeamUIProps {
  data: DevelopmentData | null;
  loading?: boolean;
}

const priorityColors: Record<string, string> = {
  low: 'default',
  medium: 'processing',
  high: 'warning',
  critical: 'error',
};

const taskColumns = [
  { title: 'Title', dataIndex: 'title', key: 'title' },
  {
    title: 'Priority',
    dataIndex: 'priority',
    key: 'priority',
    render: (p: string) => <Badge status={priorityColors[p] as any} text={p} />,
  },
  { title: 'Status', dataIndex: 'status', key: 'status', render: (s: string) => <Tag>{s}</Tag> },
  { title: 'Assignee', dataIndex: 'assignee', key: 'assignee', render: (a?: string) => a ?? '—' },
];

export const DevelopmentTeamUI = ({ data, loading }: DevelopmentTeamUIProps) => {
  const { styles } = useStyles();

  if (loading) return <Skeleton active paragraph={{ rows: 6 }} />;

  return (
    <Flexbox className={styles.container}>
      <h2 className={styles.header}>Development Dashboard</h2>

      <Flexbox horizontal className={styles.statsRow} wrap="wrap">
        <Card className={styles.statCard} size="small">
          <Statistic title="Open Issues" value={data?.openIssues ?? 0} valueStyle={{ color: '#ff4d4f' }} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Closed Issues" value={data?.closedIssues ?? 0} valueStyle={{ color: '#52c41a' }} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Pull Requests" value={data?.pullRequests ?? 0} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Test Coverage" value={data?.testCoverage ?? 0} suffix="%" precision={1} />
        </Card>
      </Flexbox>

      <Card title="Tasks" size="small">
        <Table
          dataSource={data?.tasks ?? []}
          columns={taskColumns}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 8, hideOnSinglePage: true }}
        />
      </Card>
    </Flexbox>
  );
};

export default DevelopmentTeamUI;
