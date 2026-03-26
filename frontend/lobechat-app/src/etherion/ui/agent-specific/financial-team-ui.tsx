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
  positive: css`
    color: #52c41a;
  `,
  negative: css`
    color: #ff4d4f;
  `,
}));

interface Transaction { id: string; description: string; amount: number; type: 'income' | 'expense'; category?: string; date?: string }
interface FinancialData {
  revenue?: number;
  expenses?: number;
  profit?: number;
  cashFlow?: number;
  runway?: number;
  transactions?: Transaction[];
}

interface FinancialTeamUIProps {
  data: FinancialData | null;
  loading?: boolean;
}

const txColumns = [
  { title: 'Description', dataIndex: 'description', key: 'description' },
  {
    title: 'Amount',
    dataIndex: 'amount',
    key: 'amount',
    render: (a: number, r: Transaction) => (
      <span style={{ color: r.type === 'income' ? '#52c41a' : '#ff4d4f' }}>
        {r.type === 'income' ? '+' : '-'}${Math.abs(a).toLocaleString()}
      </span>
    ),
  },
  { title: 'Category', dataIndex: 'category', key: 'category', render: (c?: string) => c ? <Tag>{c}</Tag> : '—' },
  { title: 'Date', dataIndex: 'date', key: 'date', render: (d?: string) => d ?? '—' },
];

export const FinancialTeamUI = ({ data, loading }: FinancialTeamUIProps) => {
  const { styles } = useStyles();

  if (loading) return <Skeleton active paragraph={{ rows: 6 }} />;

  const profit = data?.profit ?? 0;

  return (
    <Flexbox className={styles.container}>
      <h2 className={styles.header}>Financial Dashboard</h2>

      <Flexbox horizontal className={styles.statsRow} wrap="wrap">
        <Card className={styles.statCard} size="small">
          <Statistic title="Revenue" value={data?.revenue ?? 0} prefix="$" valueStyle={{ color: '#52c41a' }} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Expenses" value={data?.expenses ?? 0} prefix="$" valueStyle={{ color: '#ff4d4f' }} />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic
            title="Profit"
            value={Math.abs(profit)}
            prefix={profit >= 0 ? '+$' : '-$'}
            valueStyle={{ color: profit >= 0 ? '#52c41a' : '#ff4d4f' }}
          />
        </Card>
        <Card className={styles.statCard} size="small">
          <Statistic title="Runway" value={data?.runway ?? 0} suffix=" mo" />
        </Card>
      </Flexbox>

      <Card title="Recent Transactions" size="small">
        <Table
          dataSource={data?.transactions ?? []}
          columns={txColumns}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 8, hideOnSinglePage: true }}
        />
      </Card>
    </Flexbox>
  );
};

export default FinancialTeamUI;
