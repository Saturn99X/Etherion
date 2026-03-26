'use client';

import { useEffect, useState } from 'react';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Card, Table, Typography, Tag, Button, Empty, App } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { History, Eye, RefreshCw } from 'lucide-react';
import { getClient } from '@etherion/lib/apollo-client';
import { GET_JOB_HISTORY_QUERY } from '@etherion/lib/graphql-operations';

const { Text, Title } = Typography;

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
  table: css`
    .ant-table {
      background: transparent;
    }
    
    .ant-table-thead > tr > th {
      background: ${token.colorFillQuaternary};
      color: ${token.colorText};
      font-weight: 600;
      border-bottom: 1px solid ${token.colorBorder};
    }
    
    .ant-table-tbody > tr > td {
      border-bottom: 1px solid ${token.colorBorderSecondary};
    }
    
    .ant-table-tbody > tr:hover > td {
      background: ${token.colorFillTertiary};
    }
  `,
}));

export interface IngestionRecord {
  id: string;
  goal: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'QUEUED';
  createdAt: string;
  completedAt?: string;
  duration?: number;
  totalCost?: number;
  modelUsed?: string;
}

export interface IngestionHistoryProps {
  onViewDetails?: (jobId: string) => void;
  limit?: number;
}

export function IngestionHistory({ onViewDetails, limit = 20 }: IngestionHistoryProps) {
  const { styles, theme } = useStyles();
  const { message } = App.useApp();
  const [records, setRecords] = useState<IngestionRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const client = getClient();
      const { data } = await client.query({
        query: GET_JOB_HISTORY_QUERY,
        variables: { limit, offset: 0 },
        fetchPolicy: 'network-only',
      });
      setRecords(data?.getJobHistory?.jobs || []);
    } catch (err: any) {
      console.error('Failed to fetch job history:', err);
      message.error(err.message || 'Failed to fetch job history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [limit]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return 'success';
      case 'FAILED':
        return 'error';
      case 'RUNNING':
        return 'processing';
      case 'PENDING':
        return 'default';
      default:
        return 'default';
    }
  };

  const columns: ColumnsType<IngestionRecord> = [
    {
      title: 'Job ID',
      dataIndex: 'id',
      key: 'id',
      width: 200,
      render: (jobId: string) => (
        <Text code style={{ fontSize: theme.fontSizeSM }}>
          {jobId.substring(0, 12)}...
        </Text>
      ),
    },
    {
      title: 'Goal',
      dataIndex: 'goal',
      key: 'goal',
      ellipsis: true,
      render: (goal: string) => (
        <Text ellipsis title={goal} style={{ maxWidth: 300 }}>
          {goal}
        </Text>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => <Tag color={getStatusColor(status)}>{status}</Tag>,
    },
    {
      title: 'Model',
      dataIndex: 'modelUsed',
      key: 'modelUsed',
      width: 150,
      render: (model?: string) => model || '-',
    },
    {
      title: 'Started',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 180,
      render: (date: string) => new Date(date).toLocaleString(),
    },
    {
      title: 'Completed',
      dataIndex: 'completedAt',
      key: 'completedAt',
      width: 180,
      render: (date?: string) => (date ? new Date(date).toLocaleString() : '-'),
    },
    {
      title: 'Duration',
      dataIndex: 'duration',
      key: 'duration',
      width: 100,
      render: (duration?: number) => (duration ? `${Math.round(duration)}s` : '-'),
    },
    {
      title: 'Cost',
      dataIndex: 'totalCost',
      key: 'totalCost',
      width: 100,
      render: (cost?: number) => (cost ? `$${cost.toFixed(4)}` : '-'),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Button
          type="link"
          size="small"
          icon={<Eye size={14} />}
          onClick={() => onViewDetails && onViewDetails(record.id)}
        >
          View
        </Button>
      ),
    },
  ];

  return (
    <Card className={styles.card} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" justify="space-between">
        <Flexbox horizontal align="center" gap={8}>
          <History size={20} color={theme.colorPrimary} />
          <Title level={5} style={{ margin: 0 }}>
            Ingestion History
          </Title>
        </Flexbox>
        <Button
          icon={<RefreshCw size={16} />}
          onClick={fetchHistory}
          loading={loading}
          size="small"
        >
          Refresh
        </Button>
      </Flexbox>

      <div className={styles.content}>
        {records.length === 0 && !loading ? (
          <Empty description="No ingestion history found" />
        ) : (
          <div className={styles.table}>
            <Table
              columns={columns}
              dataSource={records}
              rowKey="id"
              loading={loading}
              pagination={{
                pageSize: 10,
                showSizeChanger: true,
                showTotal: (total) => `Total ${total} records`,
              }}
              scroll={{ x: 'max-content' }}
              size="small"
            />
          </div>
        )}
      </div>
    </Card>
  );
}

export default IngestionHistory;
