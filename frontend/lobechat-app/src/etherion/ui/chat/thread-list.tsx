'use client';

import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Button, List, Typography, Spin } from 'antd';
import { MessageSquare, Plus } from 'lucide-react';
import { useEffect, useState } from 'react';
import { getThreads, ThreadSummary } from '../../bridge/session';

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    height: 100%;
    background: ${token.colorBgContainer};
    border-right: 1px solid ${token.colorBorderSecondary};
    display: flex;
    flex-direction: column;
  `,
    header: css`
    padding: ${token.padding}px;
    border-bottom: 1px solid ${token.colorBorderSecondary};
  `,
    listContainer: css`
    flex: 1;
    overflow-y: auto;
    padding: ${token.paddingXS}px;
  `,
    item: css`
    border-radius: ${token.borderRadius}px;
    margin-bottom: 4px;
    cursor: pointer;
    transition: all 0.2s;
    padding: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    color: ${token.colorTextSecondary};

    &:hover {
      background: ${token.colorFillTertiary};
      color: ${token.colorText};
    }
  `,
    activeItem: css`
    background: ${token.colorFillSecondary};
    color: ${token.colorText};
    font-weight: 500;
  `,
}));

interface ThreadListProps {
    activeThreadId?: string;
    onThreadSelect: (id: string) => void;
    onNewChat: () => void;
}

export const ThreadList = ({ activeThreadId, onThreadSelect, onNewChat }: ThreadListProps) => {
    const { styles, cx } = useStyles();
    const [threads, setThreads] = useState<ThreadSummary[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchThreads = async () => {
            try {
                setLoading(true);
                const data = await getThreads(50);
                setThreads(data || []);
            } catch (e) {
                console.error('Failed to fetch threads', e);
            } finally {
                setLoading(false);
            }
        };
        fetchThreads();
    }, []);

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <Button
                    type="primary"
                    block
                    icon={<Plus size={16} />}
                    onClick={onNewChat}
                    style={{
                        height: 36,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                    }}
                >
                    New Chat
                </Button>
            </div>
            <div className={styles.listContainer}>
                {loading ? (
                    <Flexbox align="center" justify="center" style={{ height: '100%' }}>
                        <Spin size="small" />
                    </Flexbox>
                ) : (
                    <List
                        dataSource={threads}
                        renderItem={(item) => (
                            <div
                                key={item.id}
                                className={cx(styles.item, activeThreadId === item.id && styles.activeItem)}
                                onClick={() => onThreadSelect(item.id)}
                            >
                                <MessageSquare size={16} style={{ flexShrink: 0 }} />
                                <Typography.Text
                                    ellipsis
                                    style={{
                                        flex: 1,
                                        color: 'inherit',
                                        fontSize: 14
                                    }}
                                >
                                    {item.title}
                                </Typography.Text>
                            </div>
                        )}
                        locale={{ emptyText: <Typography.Text type="secondary" style={{ padding: 16, display: 'block', textAlign: 'center' }}>No conversations yet</Typography.Text> }}
                    />
                )}
            </div>
        </div>
    );
};

export default ThreadList;
