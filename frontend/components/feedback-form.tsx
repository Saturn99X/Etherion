"use client";

import { useState } from "react";
import { useMutation } from "@apollo/client";
import { SUBMIT_FEEDBACK_MUTATION } from "@/lib/graphql-operations";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

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
  const [score, setScore] = useState<string>("5");
  const [comment, setComment] = useState<string>("");
  const [submitFeedback, { loading, error, data }] = useMutation<SubmitFeedbackData, SubmitFeedbackVars>(SUBMIT_FEEDBACK_MUTATION);

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
            feedbackScore: parseInt(score, 10),
            feedbackComment: comment,
          },
        },
      });
      setComment("");
      if (onSubmitted) onSubmitted();
    } catch (e) {
      // handled by error state
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>How was the result?</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-4">
          <Label className="w-24">Rating</Label>
          <Select value={score} onValueChange={setScore}>
            <SelectTrigger className="w-28">
              <SelectValue placeholder="Select" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">1</SelectItem>
              <SelectItem value="2">2</SelectItem>
              <SelectItem value="3">3</SelectItem>
              <SelectItem value="4">4</SelectItem>
              <SelectItem value="5">5</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Comment</Label>
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What worked well? What needs improvement?"
            className="mt-2"
            rows={4}
          />
        </div>
        {error && <div className="text-red-500 text-sm">{String(error.message)}</div>}
        <div className="flex justify-end">
          <Button onClick={onSubmit} disabled={loading || !comment.trim()}>
            {loading ? "Submitting..." : "Submit Feedback"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}