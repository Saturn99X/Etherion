"use client";

import { useState } from "react";
import { useMutation } from "@apollo/client";
import { SUBMIT_FEEDBACK_MUTATION } from "@etherion/lib/graphql-operations";
import { Card, Button, Input, Rate, Space, Typography } from "antd";
import { createStyles } from "antd-style";

const { Text, Title } = Typography;
const { TextArea } = Input;

const useStyles = createStyles(({ token, css }) => ({
  card: css`
    background: ${token.colorFillQuaternary};
    border: 1px solid ${token.colorBorderSecondary};
    border-radius: ${token.borderRadius}px;
    padding: 12px;
  `,
}));

interface FeedbackFormProps {
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

export function FeedbackForm({ jobId, goal, finalOutput, userId, onSubmitted }: FeedbackFormProps) {
  const { styles } = useStyles();
  const [score, setScore] = useState<number>(5);
  const [comment, setComment] = useState<string>("");
  const [submitFeedback, { loading, error }] = useMutation<SubmitFeedbackData, SubmitFeedbackVars>(SUBMIT_FEEDBACK_MUTATION);

  const onSubmit = async () => {
    if (!comment.trim()) return;
    try {
      await submitFeedback({
        variables: {
          feedback_input: {
            jobId,
            userId,
            goal,
            finalOutput,
            feedbackScore: score,
            feedbackComment: comment,
          },
        },
      });
      setComment("");
      if (onSubmitted) onSubmitted();
    } catch { }
  };

  return (
    <div className={styles.card}>
      <Space direction="vertical" className="w-full" size={8}>
        <Title level={5} style={{ margin: 0, fontSize: 14 }}>How was the result?</Title>
        <Flexbox horizontal align="center" gap={8}>
          <Text style={{ fontSize: 12 }}>Rating:</Text>
          <Rate value={score} onChange={setScore} style={{ fontSize: 16 }} />
        </Flexbox>
        <TextArea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="What worked well? What needs improvement?"
          rows={3}
          style={{ fontSize: 12 }}
        />
        {error && <Text type="danger" style={{ fontSize: 12 }}>{error.message}</Text>}
        <Flexbox horizontal justify="flex-end">
          <Button type="primary" size="small" onClick={onSubmit} loading={loading} disabled={!comment.trim()}>
            Submit Feedback
          </Button>
        </Flexbox>
      </Space>
    </div>
  );
}

import { Flexbox } from "react-layout-kit";