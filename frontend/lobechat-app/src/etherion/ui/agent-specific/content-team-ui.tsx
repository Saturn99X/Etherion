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

interface ContentItem {
  id: string;
  title: string;
  type: string;
  status: 'draft' | 'review' | 'published';
  author?: string;
  wordCount?: number;
}
interface ContentData {
  totalPieces?: number;
  published?: number;
  inReview?: number;
  drafts?: number;
  avgEngagement?: number;
  items?: ContentItem[];
}

interface ContentTeamUIProps {
  data: ContentData | null;
  loading?: boolean;
}

const statusColors: Record<string, string> = { draft: 'default', review: 'processing', published: 'success' };

const contentColumns = [
  { title: 'Title', dataIndex: 'title', key: 'title' },
  { title: 'Type', dataIndex: 'type', key: 'type', render: (t: string) => <Tag>{t}</Tag> },
  {
    title: 'Status',
    dataIndex: 'status',
    key: 'status',
    render: (s: string) => <Badge status={statusColors[s] as any} text={s} />,
  },
  { title: 'Words', dataIndex: 'wordCount', key: 'wordCount', render: (w?: number) => w?.toLocaleString() ?? '—' },
];

export const ContentTeamUI = ({ data, loading }: ContentTeamUIProps) => {
  const { styles } = useStyles();

  if (loading) return <Skeleton active paragraph={{ rows: 6 }} />;

  return (
    <Flexbox className={styles.container}>
      <h2 className={styles.header}>Content Dashboard</h2>

      <Flexbox horizontal className={styles.statsRow} wrap="wrap">
        <Card className={styles.statCard} size="small">
          <Statistic title="Total Pieces" value={data?.totalPieces ?? 0} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Published" value={data?.published ?? 0} valueStyle={{ color: '#52c41a' }} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="In Review" value={data?.inReview ?? 0} valueStyle={{ color: '#1677ff' }} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Drafts" value={data?.drafts ?? 0} />
        </Card>
      </Flexbox>

      <Card title="Content Items" size="small">
        <Table
          dataSource={data?.items ?? []}
          columns={contentColumns}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 8, hideOnSinglePage: true }}
        />
      </Card>
    </Flexbox>
  );
};

export default ContentTeamUI;
