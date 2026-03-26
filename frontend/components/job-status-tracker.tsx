"use client";

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  PlayCircle,
  AlertCircle,
  Brain,
  X,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import { useJobStore } from '@/lib/stores/job-store';
import { GoalService } from '@/lib/services/goal-service';
import { useApolloClient } from "@/components/apollo-provider";
import { SUBSCRIBE_TO_JOB_STATUS, SUBSCRIBE_TO_EXECUTION_TRACE } from '@/lib/graphql-operations';
import { cn } from '@/lib/utils';
import { FeedbackForm } from '@/components/feedback-form';
import { useToast } from '@/hooks/use-toast';

interface JobStatusTrackerProps {
  jobId: string;
  onClose?: () => void;
  className?: string;
}

export function JobStatusTracker({ jobId, onClose, className }: JobStatusTrackerProps) {
  const { jobs, removeJob } = useJobStore();
  const [isExpanded, setIsExpanded] = useState(false);
  const [executionSteps, setExecutionSteps] = useState<string[]>([]);
  const [subscriptionActive, setSubscriptionActive] = useState(false);
  const { toast } = useToast();
  const client = useApolloClient();
  const job = jobs[jobId];

  // Subscribe to real-time updates when component mounts
  useEffect(() => {
    if (!job || subscriptionActive) return;

    setSubscriptionActive(true);

    const subscribeToUpdates = async () => {
      try {
        // Subscribe to job status updates
        const statusSubscription = client.subscribe({
          query: SUBSCRIBE_TO_JOB_STATUS,
          variables: { job_id: jobId },
        });

        // Subscribe to execution trace updates
        const traceSubscription = client.subscribe({
          query: SUBSCRIBE_TO_EXECUTION_TRACE,
          variables: { job_id: jobId },
        });

        const statusUnsubscribe = statusSubscription.subscribe({
          next: (result: any) => {
            if (result.data && result.data.subscribeToJobStatus) {
              const update = result.data.subscribeToJobStatus;
              useJobStore.getState().updateJob(jobId, update);

              // Add to execution steps if there's a step description
              if (update.current_step_description) {
                setExecutionSteps(prev => [...prev, update.current_step_description!]);
              }

              // Toasts on completion or failure
              const status = (update.status || '').toString().toUpperCase();
              if (status === 'COMPLETED') {
                toast({ title: 'Job Completed', description: `Job ${jobId} finished successfully.` });
              } else if (status === 'FAILED' || status === 'ERROR') {
                toast({ title: 'Job Failed', description: update.error_message || `Job ${jobId} failed.`, variant: 'destructive' as any });
              }
            }
          },
          error: (error: any) => {
            console.error('Job status subscription error:', error);
          },
        });

        const traceUnsubscribe = traceSubscription.subscribe({
          next: (result: any) => {
            if (result.data && result.data.subscribeToExecutionTrace) {
              const update = result.data.subscribeToExecutionTrace;
              if (update.current_step_description) {
                setExecutionSteps(prev => [...prev, update.current_step_description!]);
              }
            }
          },
          error: (error: any) => {
            console.error('Execution trace subscription error:', error);
          },
        });

        // Cleanup function
        return () => {
          statusUnsubscribe.unsubscribe();
          traceUnsubscribe.unsubscribe();
          setSubscriptionActive(false);
        };
      } catch (error) {
        console.error('Subscription setup error:', error);
        setSubscriptionActive(false);
      }
    };

    let cleanup: (() => void) | undefined;

    subscribeToUpdates().then(cleanupFn => {
      cleanup = cleanupFn;
    });

    return () => {
      if (cleanup) cleanup();
    };
  }, [jobId, job, subscriptionActive]);

  // Load archived trace when job completes
  useEffect(() => {
    if (job?.isCompleted && !job.archivedTrace) {
      GoalService.getArchivedTraceSummary(jobId).then(trace => {
        if (trace) {
          useJobStore.getState().setArchivedTrace(jobId, trace);
        }
      });
    }
  }, [job?.isCompleted, job?.archivedTrace, jobId]);

  if (!job) {
    return null;
  }

  const getStatusIcon = () => {
    switch (job.status) {
      case 'COMPLETED':
        return <CheckCircle className="h-4 w-4 text-green-400" />;
      case 'FAILED':
      case 'ERROR':
        return <XCircle className="h-4 w-4 text-red-400" />;
      case 'RUNNING':
        return <Loader2 className="h-4 w-4 text-cyan-400 animate-spin" />;
      case 'QUEUED':
        return <Clock className="h-4 w-4 text-yellow-400" />;
      default:
        return <PlayCircle className="h-4 w-4 text-gray-400" />;
    }
  };

  const getStatusColor = () => {
    switch (job.status) {
      case 'COMPLETED':
        return 'bg-green-500';
      case 'FAILED':
      case 'ERROR':
        return 'bg-red-500';
      case 'RUNNING':
        return 'bg-cyan-500';
      case 'QUEUED':
        return 'bg-yellow-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getProgressPercentage = () => {
    if (job.isCompleted) return 100;
    if (job.isFailed) return 0;
    return job.progressPercentage || 0;
  };

  return (
    <Card className={cn("glass-card border-white/20 relative", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-white">
            <Brain className="h-5 w-5 text-white" />
            <span className="text-white">Job: {jobId.slice(0, 8)}...</span>
          </CardTitle>

          <div className="flex items-center gap-2">
            {onClose && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onClose}
                className="h-8 w-8 p-0 text-white/70 hover:text-white"
              >
                <X className="h-4 w-4" />
              </Button>
            )}

            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
              className="h-8 w-8 p-0 text-white/70 hover:text-white"
            >
              {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {getStatusIcon()}
          <Badge
            variant="secondary"
            className={cn("text-white border-0", getStatusColor())}
          >
            {job.status}
          </Badge>
          {job.errorMessage && (
            <Badge variant="destructive" className="text-white">
              <AlertCircle className="h-3 w-3 mr-1" />
              Error
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Progress Bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm text-white/70">
            <span>Progress</span>
            <span>{getProgressPercentage()}%</span>
          </div>
          <Progress value={getProgressPercentage()} className="h-2" />
        </div>

        {/* Current Step */}
        {job.currentStep && (
          <div className="space-y-1">
            <p className="text-sm font-medium text-white/90">Current Step:</p>
            <p className="text-sm text-white/70 bg-white/5 p-2 rounded">
              {job.currentStep}
            </p>
          </div>
        )}

        {/* Error Message */}
        {job.errorMessage && (
          <div className="space-y-1">
            <p className="text-sm font-medium text-red-400">Error:</p>
            <p className="text-sm text-red-300 bg-red-500/10 p-2 rounded border border-red-500/20">
              {job.errorMessage}
            </p>
          </div>
        )}

        {/* Execution Steps (Expanded View) */}
        {isExpanded && executionSteps.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium text-white/90">Execution Steps:</p>
            <ScrollArea className="h-32">
              <div className="space-y-1">
                {executionSteps.map((step, index) => (
                  <div key={index} className="text-xs text-white/70 bg-white/5 p-2 rounded">
                    {step}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Archived Trace */}
        {isExpanded && job.archivedTrace && (
          <div className="space-y-2">
            <p className="text-sm font-medium text-white/90">Final Result:</p>
            <ScrollArea className="h-32">
              <div className="text-sm text-white/80 bg-white/5 p-3 rounded whitespace-pre-wrap">
                {job.archivedTrace}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Timestamps */}
        <div className="grid grid-cols-2 gap-4 text-xs text-white/60 pt-2 border-t border-white/10">
          <div>
            <span className="font-medium">Created:</span>
            <br />
            {job.createdAt.toLocaleString()}
          </div>
          {job.completedAt && (
            <div>
              <span className="font-medium">Completed:</span>
              <br />
              {job.completedAt.toLocaleString()}
            </div>
          )}
        </div>
      </CardContent>
      {/* Feedback Form on completion */}
      {job.status === 'COMPLETED' && (
        <CardContent className="space-y-4">
          <FeedbackForm
            jobId={jobId}
            userId={(job as any).userId || ''}
            goal={(job as any).input?.goal || ''}
            finalOutput={(job as any).output?.final_result || job.archivedTrace || ''}
          />
        </CardContent>
      )}
    </Card>
  );
}
