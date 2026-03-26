"use client"

import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Button, Dropdown, Space, Tooltip } from 'antd';
import { ChatInputArea } from '@lobehub/ui/chat';
import { ActionIcon } from '@lobehub/ui';
import { Send, X, Palette, Database, Paperclip, StopCircle, Zap } from 'lucide-react';
import { useRef, useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { sendGoalAndStream } from '../../bridge/chat';
import { useJobStore } from '@etherion/stores/job-store';
import { useChatAttachmentsStore } from '@etherion/stores/chat-attachments-store';
import { GoalService } from '@etherion/lib/services/goal-service';

const useStyles = createStyles(({ token, css }) => ({
  container: css`
    padding: 12px;
    background: ${token.colorBgContainer};
    border-top: 1px solid ${token.colorBorderSecondary};
  `,
  toolbar: css`
    margin-bottom: 8px;
  `,
}));

interface GoalInputBarProps {
  onSubmit?: (message: string, attachments: any[]) => void;
  disabled?: boolean;
  placeholder?: string;
  threadId?: string;
  branchId?: string;
  allowPlatformEntry?: boolean;
  autoFocus?: boolean;
  planMode?: boolean;
  searchForce?: boolean;
  agentTeamId?: string;
  onJobStarted?: (args: { jobId: string; threadId?: string; goal: string; planMode?: boolean; searchForce?: boolean }) => void;
}

export const GoalInputBar = ({
  onSubmit,
  disabled = false,
  placeholder = "Ask Etherion for anything...",
  threadId,
  branchId,
  allowPlatformEntry = true,
  autoFocus = false,
  planMode,
  searchForce,
  agentTeamId,
  onJobStarted,
}: GoalInputBarProps) => {
  const { styles, theme } = useStyles();
  const [message, setMessage] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);
  const [currentJobId, setCurrentJobId] = useState<string | undefined>(undefined);
  const [selectedTone, setSelectedTone] = useState('Professional');
  const [selectedContext, setSelectedContext] = useState('General');

  const { addJob, subscribeToJob, jobs } = useJobStore();
  const getItems = useChatAttachmentsStore((s) => s.getItems);
  const clearItems = useChatAttachmentsStore((s) => s.clear);
  const router = useRouter();

  const tId = threadId || 'default';

  const handleSubmit = async () => {
    if (!message.trim() || disabled || isExecuting) return;

    setIsExecuting(true);
    try {
      if (!allowPlatformEntry) {
        router.push('/studio');
        return;
      }

      const { job } = await sendGoalAndStream({
        threadId: tId,
        branchId,
        text: message,
        context: `${selectedTone} tone, ${selectedContext} context`,
        planMode,
        searchForce,
        teamId: agentTeamId,
        onTextDelta: () => { }
      });

      onSubmit?.(message, getItems(tId, branchId));
      onJobStarted?.({ jobId: job.job_id, threadId: tId, goal: message, planMode, searchForce });

      setMessage('');
      setCurrentJobId(job.job_id);
      clearItems(tId, branchId);
    } catch (error) {
      console.error('Goal execution failed:', error);
    } finally {
      setIsExecuting(false);
    }
  };

  const stopExecution = async () => {
    if (currentJobId) {
      try {
        await GoalService.cancelJob(currentJobId);
      } catch (e) {
        console.error('Failed to cancel job', e);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const toneItems = [
    { key: 'Professional', label: 'Professional', onClick: () => setSelectedTone('Professional') },
    { key: 'Casual', label: 'Casual', onClick: () => setSelectedTone('Casual') },
    { key: 'Creative', label: 'Creative', onClick: () => setSelectedTone('Creative') },
    { key: 'Technical', label: 'Technical', onClick: () => setSelectedTone('Technical') },
  ];

  const contextItems = [
    { key: 'General', label: 'General', onClick: () => setSelectedContext('General') },
    { key: 'Code', label: 'Code', onClick: () => setSelectedContext('Code') },
    { key: 'Research', label: 'Research', onClick: () => setSelectedContext('Research') },
    { key: 'Analysis', label: 'Analysis', onClick: () => setSelectedContext('Analysis') },
  ];

  return (
    <div className={styles.container}>
      <Flexbox className={styles.toolbar} horizontal gap={4} align="center">
        <Dropdown menu={{ items: toneItems }} trigger={['click']}>
          <Button size="small" type="text" icon={<Palette size={14} />}>
            {selectedTone}
          </Button>
        </Dropdown>
        <Dropdown menu={{ items: contextItems }} trigger={['click']}>
          <Button size="small" type="text" icon={<Database size={14} />}>
            {selectedContext}
          </Button>
        </Dropdown>
        <div style={{ flex: 1 }} />
        <ActionIcon icon={Paperclip} size={{ blockSize: 24 }} title="Attach Files" />
      </Flexbox>

      <ChatInputArea
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled || isExecuting}
        autoFocus={autoFocus}
        bottomAddons={
          <Flexbox horizontal justify="flex-end" padding={8} align="center">
            {isExecuting ? (
              <Button
                danger
                type="primary"
                icon={<StopCircle size={16} />}
                onClick={stopExecution}
              >
                Stop
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<Zap size={16} />}
                onClick={handleSubmit}
                disabled={!message.trim()}
                style={{ borderRadius: 8 }}
              >
                Execute
              </Button>
            )}
          </Flexbox>
        }
      />
    </div>
  );
};

export default GoalInputBar;
