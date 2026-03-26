'use client';

import React, { useState } from 'react';
import { createStyles } from 'antd-style';
import { Flexbox } from 'react-layout-kit';
import { Card, Button, Input, Select, Typography, App } from 'antd';
import { MessageSquare, Send } from 'lucide-react';
import { useApolloClient } from '@etherion/ui/layout/apollo-provider';
import { SUBMIT_FEEDBACK_MUTATION } from '@etherion/lib/graphql-operations';

const { TextArea } = Input;
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
  formItem: css`
    margin-bottom: ${token.marginMD}px;
  `,
  label: css`
    display: block;
    margin-bottom: ${token.marginXS}px;
    color: ${token.colorText};
    font-weight: 500;
    font-size: ${token.fontSizeSM}px;
  `,
}));

export interface FeedbackFormProps {
  jobId: string;
  goal: string;
  finalOutput: string;
  userId: string;
  onSubmitted?: () => void;
}

interface SubmitFeedbackData {
  submitFeedback: boolean;
}

interface SubmitFeedbackVars {
  feedback_input: {
    jobId: string;
    userId: string;
    goal: string;
    finalOutput: string;
    feedbackScore: number;
    feedbackComment: string;
  };
}

export function FeedbackForm({
  jobId,
  goal,
  finalOutput,
  userId,
  onSubmitted,
}: FeedbackFormProps) {
  const { styles, theme } = useStyles();
  const { message } = App.useApp();
  const client = useApolloClient();
  const [score, setScore] = useState<string>('5');
  const [comment, setComment] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!comment.trim()) {
      message.warning('Please provide a comment');
      return;
    }

    setLoading(true);
    try {
      await client.mutate<SubmitFeedbackData, SubmitFeedbackVars>({
        mutation: SUBMIT_FEEDBACK_MUTATION,
        variables: {
          feedback_input: {
            jobId,
            userId,
            goal,
            finalOutput,
            feedbackScore: parseInt(score, 10),
            feedbackComment: comment,
          },
        },
      });

      message.success('Feedback submitted successfully');
      setComment('');
      setScore('5');
      if (onSubmitted) onSubmitted();
    } catch (error: any) {
      console.error('Feedback submission error:', error);
      message.error(error.message || 'Failed to submit feedback');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className={styles.card} bordered={false}>
      <Flexbox className={styles.header} horizontal align="center" gap={8}>
        <MessageSquare size={20} color={theme.colorPrimary} />
        <Title level={5} style={{ margin: 0 }}>
          How was the result?
        </Title>
      </Flexbox>
      <div className={styles.content}>
        <Flexbox gap={16}>
          {/* Rating */}
          <div className={styles.formItem}>
            <Text className={styles.label}>Rating</Text>
            <Select
              value={score}
              onChange={setScore}
              style={{ width: 120 }}
              options={[
                { label: '1 - Poor', value: '1' },
                { label: '2 - Fair', value: '2' },
                { label: '3 - Good', value: '3' },
                { label: '4 - Very Good', value: '4' },
                { label: '5 - Excellent', value: '5' },
              ]}
            />
          </div>

          {/* Comment */}
          <div className={styles.formItem}>
            <Text className={styles.label}>Comment</Text>
            <TextArea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="What worked well? What needs improvement?"
              rows={4}
              maxLength={1000}
              showCount
            />
          </div>

          {/* Submit Button */}
          <Flexbox horizontal justify="flex-end">
            <Button
              type="primary"
              icon={<Send size={16} />}
              loading={loading}
              disabled={loading || !comment.trim()}
              onClick={handleSubmit}
            >
              {loading ? 'Submitting...' : 'Submit Feedback'}
            </Button>
          </Flexbox>
        </Flexbox>
      </div>
    </Card>
  );
}

export default FeedbackForm;
