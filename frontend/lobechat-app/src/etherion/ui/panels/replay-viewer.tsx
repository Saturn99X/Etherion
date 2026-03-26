'use client';

import { useEffect, useState } from 'react';
import {
    Card, Button, Typography, Space, App,
    Empty, Skeleton, Divider, Tabs
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
    History, Download, FileJson, FileText,
    RefreshCw, PlayCircle
} from 'lucide-react';

import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { LIST_REPOSITORY_ASSETS } from '@etherion/lib/graphql-operations';
import { ReplayTranscriptRenderer } from './replay-transcript-renderer';

const { Title, Text } = Typography;

const useStyles = createStyles(({ token, css }) => ({
    container: css`
    padding: ${token.paddingLG}px;
  `,
    header: css`
    margin-bottom: ${token.marginLG}px;
  `,
    content: css`
    max-width: 1000px;
    margin: 0 auto;
  `,
}));

interface RepoAsset {
    assetId: string;
    filename: string;
    mimeType: string;
    downloadUrl?: string | null;
}

export const ReplayViewer = ({ jobId }: { jobId: string }) => {
    const { styles, theme } = useStyles();
    const { message } = App.useApp();
    const client = useApolloClient();

    const [loading, setLoading] = useState(true);
    const [transcriptContent, setTranscriptContent] = useState<string | null>(null);
    const [traceUrl, setTraceUrl] = useState<string | null>(null);

    const loadReplayData = async () => {
        try {
            setLoading(true);
            const { data } = await client.query({
                query: LIST_REPOSITORY_ASSETS,
                variables: { jobId, limit: 10, include_download: true },
                fetchPolicy: 'network-only'
            });

            const assets: RepoAsset[] = data.listRepositoryAssets;

            // Find transcript and trace
            const transcriptAsset = assets.find(a => a.filename.endsWith('transcript.md'));
            const traceAsset = assets.find(a => a.filename.endsWith('trace.jsonl'));

            if (transcriptAsset?.downloadUrl) {
                const res = await fetch(transcriptAsset.downloadUrl);
                if (res.ok) setTranscriptContent(await res.text());
            }

            if (traceAsset?.downloadUrl) {
                setTraceUrl(traceAsset.downloadUrl);
            }
        } catch (err) {
            message.error("Failed to load replay data");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (jobId) loadReplayData();
    }, [jobId]);

    if (loading) return <div className={styles.container}><Skeleton active /></div>;

    if (!transcriptContent && !traceUrl) {
        return (
            <div className={styles.container}>
                <Empty description="No replay data found for this job" />
            </div>
        );
    }

    return (
        <div className={styles.container}>
            <Flexbox className={styles.header} horizontal align="center" justify="space-between">
                <Space size={12}>
                    <PlayCircle size={24} color={theme.colorPrimary} />
                    <div>
                        <Title level={3} style={{ margin: 0 }}>Job Replay</Title>
                        <Text type="secondary">Historical execution context and artifacts</Text>
                    </div>
                </Space>
                {traceUrl && (
                    <Button
                        type="primary"
                        icon={<Download size={14} />}
                        href={traceUrl}
                        download={`job_${jobId}_trace.jsonl`}
                    >
                        Download Raw Trace
                    </Button>
                )}
            </Flexbox>

            <div className={styles.content}>
                {transcriptContent ? (
                    <ReplayTranscriptRenderer content={transcriptContent} jobId={jobId} />
                ) : (
                    <Card>
                        <Empty description="Transcript not available, please download raw trace for details." />
                    </Card>
                )}
            </div>
        </div>
    );
};

export default ReplayViewer;
