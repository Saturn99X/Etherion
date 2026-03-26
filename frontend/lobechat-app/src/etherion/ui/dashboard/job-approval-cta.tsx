'use client';

import { createStyles } from 'antd-style';
import { Button, Tag } from 'antd';
import { CheckCircle } from 'lucide-react';
import { Flexbox } from 'react-layout-kit';
import { useJobStore } from '@etherion/stores/job-store';

const useStyles = createStyles(({ token, css }) => ({
  container: css`
    padding: ${token.paddingSM}px ${token.padding}px;
    background: ${token.colorWarningBg};
    border: 1px solid ${token.colorWarningBorder};
    border-radius: ${token.borderRadius}px;
  `,
  label: css`
    color: ${token.colorWarningText};
    font-size: ${token.fontSizeSM}px;
    font-weight: 500;
  `,
}));

interface JobApprovalCTAProps {
  jobId: string;
  /** Called when the user clicks "Approve". Opens the blueprint modal. */
  onOpenApproval?: (jobId: string) => void;
}

/**
 * Compact CTA banner shown when a job is in PENDING_APPROVAL state.
 * Renders a warning tag + "Review & Approve" button.
 */
export const JobApprovalCTA = ({ jobId, onOpenApproval }: JobApprovalCTAProps) => {
  const { styles } = useStyles();
  const job = useJobStore((s) => s.jobs[jobId]);

  if (!job || job.status !== 'PENDING_APPROVAL') return null;

  return (
    <Flexbox horizontal align="center" justify="space-between" className={styles.container} gap={8}>
      <Flexbox horizontal align="center" gap={8}>
        <Tag color="warning">Waiting for approval</Tag>
        <span className={styles.label}>Job requires your approval to proceed</span>
      </Flexbox>
      <Button
        type="primary"
        size="small"
        icon={<CheckCircle size={14} />}
        onClick={() => onOpenApproval?.(jobId)}
      >
        Review &amp; Approve
      </Button>
    </Flexbox>
  );
};

export default JobApprovalCTA;
