"use client";

import React, { useEffect, useState } from 'react';
import { useSubscription } from '@apollo/client';
import { SUBSCRIBE_TO_EXECUTION_TRACE } from '@/lib/graphql-operations';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';

interface ExecutionTraceProps {
  jobId: string;
}

interface TraceEvent {
  timestamp: string;
  message: string;
  step_type: string;
  additional_data: any;
}

export const ExecutionTrace: React.FC<ExecutionTraceProps> = ({ jobId }) => {
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const { data, loading, error } = useSubscription(SUBSCRIBE_TO_EXECUTION_TRACE, {
    variables: { jobId },
    shouldResubscribe: true,
  });

  useEffect(() => {
    if (data?.subscribeToExecutionTrace) {
      const newEvent = {
        timestamp: data.subscribeToExecutionTrace.timestamp,
        message: data.subscribeToExecutionTrace.current_step_description,
        step_type: data.subscribeToExecutionTrace.additional_data?.step_type || 'INFO',
        additional_data: data.subscribeToExecutionTrace.additional_data,
      };
      setTrace((prevTrace) => [...prevTrace, newEvent]);
    }
  }, [data]);

  if (loading) {
    return <div>Loading execution trace...</div>;
  }

  if (error) {
    return <div>Error loading execution trace: {error.message}</div>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Live Execution Trace</CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-96 w-full rounded-md border p-4">
          {trace.map((event, index) => (
            <div key={index} className="mb-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{event.step_type}</Badge>
                  <span className="text-xs text-muted-foreground">{new Date(event.timestamp).toLocaleTimeString()}</span>
                </div>
              </div>
              <p className="text-sm mt-1">{event.message}</p>
            </div>
          ))}
        </ScrollArea>
      </CardContent>
    </Card>
  );
};
