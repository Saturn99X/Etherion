"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useSubscription } from '@apollo/client';
import { SUBSCRIBE_TO_UI_EVENTS } from '@/lib/graphql-operations';

interface UIEvent {
  type: string;
  payload: any;
}

interface UIEventContextType {
  lastEvent: UIEvent | null;
}

const UIEventContext = createContext<UIEventContextType>({ lastEvent: null });

export const UIEventProvider: React.FC<{ children: ReactNode; tenantId: number | null }> = ({ children, tenantId }) => {
  const [lastEvent, setLastEvent] = useState<UIEvent | null>(null);
  const { data, loading, error } = useSubscription(SUBSCRIBE_TO_UI_EVENTS, {
    variables: { tenant_id: tenantId ?? 0 },
    shouldResubscribe: true,
    skip: !tenantId,
  });

  useEffect(() => {
    if (data?.subscribeToUIEvents) {
      const rawEvent = data.subscribeToUIEvents.additional_data;
      if (rawEvent) {
        setLastEvent({ type: rawEvent.event_type, payload: rawEvent.payload });
      }
    }
  }, [data]);

  if (loading) {
    // You might want to render a loading state here
  }

  if (error) {
    console.error('UI Event Subscription Error:', error);
    // You might want to render an error state here
  }

  return (
    <UIEventContext.Provider value={{ lastEvent }}>
      {children}
    </UIEventContext.Provider>
  );
};

export const useUIEvents = () => {
  return useContext(UIEventContext);
};
