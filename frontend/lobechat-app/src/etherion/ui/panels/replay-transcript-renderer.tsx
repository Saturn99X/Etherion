'use client';

import React from 'react';
import { Typography, Card, Divider, Space } from 'antd';
import { createStyles } from 'antd-style';
import { Markdown } from '@lobehub/ui';
import { FileText, History } from 'lucide-react';

const { Title, Text } = Typography;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    width: 100%;
    background: ${token.colorBgContainer};
    border-radius: ${token.borderRadiusLG}px;
    border: 1px solid ${token.colorBorderSecondary};
    padding: ${token.paddingLG}px;
  `,
    header: css`
    margin-bottom: ${token.marginMD}px;
  `,
}));

interface ReplayTranscriptRendererProps {
    content: string;
    jobId?: string;
}

export const ReplayTranscriptRenderer = ({ content, jobId }: ReplayTranscriptRendererProps) => {
    const { styles, theme } = useStyles();

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <Space size={8}>
                    <History size={18} color={theme.colorPrimary} />
                    <Title level={4} style={{ margin: 0 }}>Execution Transcript</Title>
                </Space>
                {jobId && (
                    <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>
                        Replay for Job: {jobId}
                    </Text>
                )}
            </div>

            <Divider style={{ margin: '16px 0' }} />

            <Markdown>{content}</Markdown>
        </div>
    );
};

export default ReplayTranscriptRenderer;
