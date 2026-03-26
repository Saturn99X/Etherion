'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
    Badge, Card, Table, Input, Select,
    Button, Typography, Space, App,
    Pagination, ConfigProvider, theme
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
    Search, Filter, ChevronLeft, ChevronRight,
    Eye, MessageSquare, History, Activity
} from 'lucide-react';

import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { GET_JOB_HISTORY_QUERY, GET_JOB_DETAILS_QUERY } from '@etherion/lib/graphql-operations';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    padding: ${token.paddingLG}px;
    background: ${token.colorBgLayout};
    min-height: 100vh;
  `,
    header: css`
    margin-bottom: ${token.marginLG}px;
  `,
    filterCard: css`
    margin-bottom: ${token.marginLG}px;
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
  `,
    tableCard: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
  `,
    jobId: css`
    font-family: ${token.fontFamilyCode};
    font-size: 12px;
    color: ${token.colorTextDescription};
  `,
    goalText: css`
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    display: block;
  `,
}));

interface JobHistoryItem {
    id: string;
    goal: string;
    status: string;
    createdAt: string;
    completedAt?: string;
    duration: string;
    totalCost: string;
    modelUsed?: string;
    threadId?: string;
}

const getStatusBadge = (status: string) => {
    const s = status.toUpperCase();
    if (s === 'COMPLETED') return <Badge status="success" text="Completed" />;
    if (s === 'RUNNING') return <Badge status="processing" text="Running" />;
    if (s === 'FAILED' || s === 'ERROR') return <Badge status="error" text="Failed" />;
    if (s === 'PENDING_APPROVAL') return <Badge status="warning" text="Approval Needed" />;
    return <Badge status="default" text={status} />;
};

export const JobsDashboard = () => {
    const { styles, theme: token } = useStyles();
    const router = useRouter();
    const { message } = App.useApp();
    const client = useApolloClient();

    const [jobs, setJobs] = useState<JobHistoryItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState("");
    const [statusFilter, setStatusFilter] = useState<string>("all");
    const [currentPage, setCurrentPage] = useState(1);
    const [totalCount, setTotalCount] = useState(0);
    const itemsPerPage = 10;

    const fetchJobHistory = async () => {
        try {
            setLoading(true);
            const { data } = await client.query({
                query: GET_JOB_HISTORY_QUERY,
                variables: {
                    limit: itemsPerPage,
                    offset: (currentPage - 1) * itemsPerPage,
                    status: statusFilter === "all" ? null : statusFilter,
                },
                fetchPolicy: 'network-only'
            });

            const history = (data as any).getJobHistory;
            setJobs(history.jobs);
            setTotalCount(history.totalCount);
        } catch (err) {
            message.error('Failed to load job history');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchJobHistory();
    }, [currentPage, statusFilter]);

    const handleOpenChat = (threadId?: string) => {
        if (threadId) {
            router.push(`/interact?thread=${encodeURIComponent(threadId)}`);
        } else {
            message.warning('Execution thread not found');
        }
    };

    const columns = [
        {
            title: 'Job ID',
            dataIndex: 'id',
            key: 'id',
            render: (id: string) => <span className={styles.jobId}>{id.slice(0, 8)}...</span>,
        },
        {
            title: 'Goal',
            dataIndex: 'goal',
            key: 'goal',
            render: (goal: string) => <Text className={styles.goalText} title={goal}>{goal}</Text>,
        },
        {
            title: 'Status',
            dataIndex: 'status',
            key: 'status',
            render: (status: string) => getStatusBadge(status),
        },
        {
            title: 'Created At',
            dataIndex: 'createdAt',
            key: 'createdAt',
            render: (date: string) => <Text type="secondary" style={{ fontSize: 12 }}>{new Date(date).toLocaleString()}</Text>,
        },
        {
            title: 'Cost',
            dataIndex: 'totalCost',
            key: 'totalCost',
            render: (cost: string) => <Text strong>{cost}</Text>,
        },
        {
            title: 'Actions',
            key: 'actions',
            render: (_: any, record: JobHistoryItem) => (
                <Space size="small">
                    <Button
                        size="small"
                        type="text"
                        icon={<History size={14} />}
                        onClick={() => message.info('Trace viewer coming soon')}
                    >
                        Trace
                    </Button>
                    <Button
                        size="small"
                        type="text"
                        icon={<MessageSquare size={14} />}
                        onClick={() => handleOpenChat(record.threadId)}
                        disabled={!record.threadId}
                    >
                        Chat
                    </Button>
                </Space>
            ),
        },
    ];

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <div>
                    <Title level={2} style={{ margin: 0 }}>Threads Dashboard</Title>
                    <Text type="secondary">Central hub for monitoring and managing AI goal executions</Text>
                </div>
                <Button icon={<Activity size={14} />} onClick={fetchJobHistory}>Refresh Feed</Button>
            </Flexbox>

            <Card className={styles.filterCard} size="small">
                <Flexbox horizontal gap={16} align="center">
                    <Input
                        prefix={<Search size={14} />}
                        placeholder="Search by goal..."
                        value={searchTerm}
                        onChange={e => setSearchTerm(e.target.value)}
                        style={{ flex: 1 }}
                    />
                    <Select
                        value={statusFilter}
                        onChange={setStatusFilter}
                        style={{ width: 180 }}
                        placeholder="Filter by status"
                    >
                        <Option value="all">All Statuses</Option>
                        <Option value="completed">Completed</Option>
                        <Option value="running">Running</Option>
                        <Option value="failed">Failed</Option>
                        <Option value="pending_approval">Pending Approval</Option>
                    </Select>
                </Flexbox>
            </Card>

            <Card className={styles.tableCard} bodyStyle={{ padding: 0 }}>
                <Table
                    columns={columns}
                    dataSource={jobs}
                    loading={loading}
                    pagination={false}
                    rowKey="id"
                    size="middle"
                />
                <div style={{ padding: '16px', display: 'flex', justifyContent: 'flex-end' }}>
                    <Pagination
                        current={currentPage}
                        total={totalCount}
                        pageSize={itemsPerPage}
                        onChange={setCurrentPage}
                        showSizeChanger={false}
                    />
                </div>
            </Card>
        </div>
    );
};

export default JobsDashboard;
