'use client';

import { useEffect, useState } from 'react';
import {
  Card, Progress, Badge, Button,
  Typography, Space, App, Divider,
  Skeleton
} from 'antd';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import {
  CheckCircle, XCircle, Clock, Loader2,
  PlayCircle, AlertCircle, Brain, X,
  ChevronDown, ChevronUp, History,
  Terminal
} from 'lucide-react';

import { useJobStore } from '@etherion/stores/job-store';
import { GoalService } from '@etherion/lib/services/goal-service';
import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { SUBSCRIBE_TO_JOB_STATUS, SUBSCRIBE_TO_EXECUTION_TRACE } from '@etherion/lib/graphql-operations';
import { FeedbackForm } from './feedback-form';

const { Text, Title, Paragraph } = Typography;

const useStyles = createStyles(({ token, css }) => ({
  card: css`
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorderSecondary};
    box-shadow: ${token.boxShadowTertiary};
    border-radius: ${token.borderRadiusLG}px;
    width: 100%;
    max-width: 400px;
  `,
  header: css`
    padding: ${token.paddingSM}px ${token.paddingMD}px;
    border-bottom: 1px solid ${token.colorBorderSecondary};
  `,
  content: css`
    padding: ${token.paddingMD}px;
  `,
  stepItem: css`
    padding: 8px;
    background: ${token.colorFillQuaternary};
    border-radius: ${token.borderRadiusSM}px;
    font-size: 11px;
    font-family: ${token.fontFamilyCode};
    margin-bottom: 4px;
    border: 1px solid ${token.colorBorderSecondary};
  `,
  traceArea: css`
    max-height: 150px;
    overflow-y: auto;
    margin-top: 12px;
  `,
  errorBox: css`
    background: ${token.colorErrorBg};
    border: 1px solid ${token.colorErrorBorder};
    padding: 8px;
    border-radius: ${token.borderRadiusSM}px;
    margin-top: 12px;
  `,
}));

interface JobStatusTrackerProps {
  jobId: string;
  onClose?: () => void;
  className?: string;
}

export const JobStatusTracker = ({ jobId, onClose, className }: JobStatusTrackerProps) => {
  const { styles, theme } = useStyles();
  const { jobs, updateJob, setArchivedTrace } = useJobStore();
  const { message, notification } = App.useApp();
  const client = useApolloClient();

  const [isExpanded, setIsExpanded] = useState(false);
  const [subscriptionActive, setSubscriptionActive] = useState(false);

  const job = jobs[jobId];

  useEffect(() => {
    if (!job || subscriptionActive) return;

    // Use the centralized subscription from useJobStore
    useJobStore.getState().subscribeToJob(jobId);
    setSubscriptionActive(true);

    return () => {
      // We don't necessarily want to unsubscribe on unmount if we want to keep tracking 
      // but for this component, let's keep it simple.
      // useJobStore.getState().unsubscribeFromJob(jobId);
    };
  }, [jobId, job, subscriptionActive]);

  useEffect(() => {
    if (job?.status === 'COMPLETED' && !job.archivedTrace) {
      GoalService.getArchivedTraceSummary(jobId).then(trace => {
        if (trace) setArchivedTrace(jobId, trace);
      });
    }
  }, [job?.status, job?.archivedTrace, jobId]);

  if (!job) return null;

  const getStatusIcon = () => {
    switch (job.status?.toUpperCase()) {
      case 'COMPLETED': return <CheckCircle size={14} color={theme.colorSuccess} />;
      case 'RUNNING': return <Loader2 size={14} className="animate-spin" color={theme.colorPrimary} />;
      case 'QUEUED': return <Clock size={14} color={theme.colorWarning} />;
      case 'FAILED':
      case 'ERROR': return <XCircle size={14} color={theme.colorError} />;
      default: return <PlayCircle size={14} />;
    }
  };

  const progress = job.status === 'COMPLETED' ? 100 : job.progressPercentage || 0;

  return (
    <div className={`${styles.card} ${className}`}>
      <Flexbox className={styles.header} horizontal align="center" justify="space-between">
        <Space size={8}>
          <Brain size={16} color={theme.colorPrimary} />
          <Text strong style={{ fontSize: 13 }}>Job: {jobId.slice(0, 8)}</Text>
        </Space>
        <Space size={4}>
          <Button type="text" size="small" icon={<X size={14} />} onClick={onClose} />
          <Button
            type="text"
            size="small"
            icon={isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            onClick={() => setIsExpanded(!isExpanded)}
          />
        </Space>
      </Flexbox>

      <div className={styles.content}>
        <Flexbox horizontal justify="space-between" align="center" style={{ marginBottom: 8 }}>
          <Space size={6}>
            {getStatusIcon()}
            <Badge
              count={job.status}
              style={{
                backgroundColor: job.status === 'COMPLETED' ? theme.colorSuccess :
                  job.status === 'RUNNING' ? theme.colorPrimary :
                    theme.colorFillSecondary,
                fontSize: 10
              }}
            />
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>{progress}%</Text>
        </Flexbox>

        <Progress percent={progress} size="small" showInfo={false} strokeColor={theme.colorPrimary} />

        {job.currentStep && (
          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ fontSize: 11 }}>Active Step:</Text>
            <Paragraph style={{ fontSize: 12, margin: 0 }}>{job.currentStep}</Paragraph>
          </div>
        )}

        {job.errorMessage && (
          <div className={styles.errorBox}>
            <Space size={4} align="start">
              <AlertCircle size={12} style={{ marginTop: 2, color: theme.colorError }} />
              <Text type="danger" style={{ fontSize: 11 }}>{job.errorMessage}</Text>
            </Space>
          </div>
        )}

        {isExpanded && (
          <div className={styles.traceArea}>
            <Divider plain style={{ margin: '12px 0 8px 0', fontSize: 10 }}>Execution Trace</Divider>
            {job.executionTrace.map((step, idx) => (
              <div key={idx} className={styles.stepItem}>{step.summary}</div>
            ))}
            {job.archivedTrace && (
              <div style={{ marginTop: 12 }}>
                <Text strong style={{ fontSize: 11 }}>Summary Output:</Text>
                <Paragraph style={{
                  fontSize: 11,
                  background: theme.colorFillSecondary,
                  padding: 8,
                  borderRadius: 4,
                  whiteSpace: 'pre-wrap'
                }}>
                  {job.archivedTrace}
                </Paragraph>
              </div>
            )}
          </div>
        )}

        {job.status === 'COMPLETED' && (
          <>
            <Divider style={{ margin: '16px 0' }} />
            <FeedbackForm
              jobId={jobId}
              goal={(job as any).input?.goal || ''}
              finalOutput={job.archivedTrace || ''}
              userId={(job as any).userId || ''}
            />
          </>
        )}
      </div>
    </div>
  );
};

export default JobStatusTracker;
