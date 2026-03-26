'use client';

import { useEffect, useState, useCallback } from 'react';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Card, Progress, Typography, Alert, Button, Tag, App } from 'antd';
import { Database, Clock, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { useJobStore } from '@etherion/stores/job-store';

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
  stageInfo: css`
    background: ${token.colorFillQuaternary};
    padding: ${token.paddingSM}px ${token.paddingMD}px;
    border-radius: ${token.borderRadius}px;
    border: 1px solid ${token.colorBorder};
  `,
  statusTag: css`
    font-size: ${token.fontSizeSM}px;
  `,
}));

export interface IngestionMonitorProps {
  jobId: string;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

export function IngestionMonitor({
  jobId,
  onComplete,
  onError,
}: IngestionMonitorProps) {
  const { styles, theme } = useStyles();
  const { message } = App.useApp();
  const job = useJobStore((state) => state.jobs[jobId]);
  const subscribeToJob = useJobStore((state) => state.subscribeToJob);
  const unsubscribeFromJob = useJobStore((state) => state.unsubscribeFromJob);
  const [hasNotified, setHasNotified] = useState(false);

  useEffect(() => {
    // Subscribe to job updates
    subscribeToJob(jobId);

    return () => {
      unsubscribeFromJob(jobId);
    };
  }, [jobId, subscribeToJob, unsubscribeFromJob]);

  useEffect(() => {
    if (!job || hasNotified) return;

    if (job.isCompleted) {
      message.success('Ingestion completed successfully');
      if (onComplete) onComplete();
      setHasNotified(true);
    } else if (job.isFailed) {
      const errorMsg = job.errorMessage || 'Ingestion failed';
      message.error(errorMsg);
      if (onError) onError(errorMsg);
      setHasNotified(true);
    }
  }, [job, hasNotified, onComplete, onError, message]);

  const getStatusIcon = () => {
    if (!job) return <RefreshCw size={20} color={theme.colorPrimary} />;
    if (job.isFailed) {
      return <AlertCircle size={20} color={theme.colorError} />;
    }
    if (job.isCompleted) {
      return <CheckCircle size={20} color={theme.colorSuccess} />;
    }
    return <RefreshCw size={20} color={theme.colorPrimary} className="animate-spin" />;
  };

  const getStatusColor = () => {
    if (!job) return 'default';
    if (job.isFailed) return 'error';
    if (job.isCompleted) return 'success';
    return 'processing';
  };

  return (
    <Card className={styles.card}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <Database size={20} color={theme.colorPrimary} />
        <Title level={5} style={{ margin: 0 }}>
          Ingestion Monitor
        </Title>
        <Tag color={getStatusColor()} className={styles.statusTag} style={{ marginLeft: 'auto' }}>
          {job?.status || 'LOADING'}
        </Tag>
      </Flexbox>

      <div className={styles.content}>
        <Flexbox gap={16}>
          {/* Error Alert */}
          {job?.isFailed && job.errorMessage && (
            <Alert
              type="error"
              message="Ingestion Failed"
              description={job.errorMessage}
              showIcon
            />
          )}

          {/* Progress Bar */}
          {job && (
            <>
              <Progress
                percent={job.progressPercentage || 0}
                status={
                  job.isCompleted
                    ? 'success'
                    : job.isFailed
                      ? 'exception'
                      : 'active'
                }
                strokeColor={theme.colorPrimary}
              />

              {/* Stage Information */}
              <div className={styles.stageInfo}>
                <Flexbox gap={8}>
                  <Flexbox horizontal align="center" gap={8}>
                    {getStatusIcon()}
                    <Text strong>Status: {job.status}</Text>
                  </Flexbox>
                  {job.currentStep && (
                    <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                      Current Step: {job.currentStep}
                    </Text>
                  )}
                  <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                    Started: {job.createdAt.toLocaleString()}
                  </Text>
                  {job.completedAt && (
                    <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
                      Completed: {job.completedAt.toLocaleString()}
                    </Text>
                  )}
                </Flexbox>
              </div>
            </>
          )}

          {!job && (
            <Alert
              type="info"
              message="Loading job status..."
              showIcon
            />
          )}

          {/* Job ID */}
          <Flexbox horizontal align="center" gap={8}>
            <Text type="secondary" style={{ fontSize: theme.fontSizeSM }}>
              Job ID:
            </Text>
            <Text code style={{ fontSize: theme.fontSizeSM }}>
              {jobId}
            </Text>
          </Flexbox>
        </Flexbox>
      </div>
    </Card>
  );
}

export default IngestionMonitor;
