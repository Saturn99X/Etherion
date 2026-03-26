"use client"

import { useEffect, useRef } from "react"
import { useApolloClient } from "@/components/apollo-provider";
import { SUBSCRIBE_TO_UI_EVENTS } from "@/lib/graphql-operations"

interface TenantUIEventsSubscriberProps {
  tenantId: number
  onEvent?: (evt: any) => void
}

export function TenantUIEventsSubscriber({ tenantId, onEvent }: TenantUIEventsSubscriberProps) {
  const subRef = useRef<any>(null)
  const client = useApolloClient();
  useEffect(() => {
    if (!tenantId) return
    try {
      const observable = client.subscribe({
        query: SUBSCRIBE_TO_UI_EVENTS,
        variables: { tenant_id: tenantId },
      })
      const sub = observable.subscribe({
        next: (result: any) => {
          const evt = result?.data?.subscribeToUIEvents
          if (evt && onEvent) onEvent(evt)
        },
        error: (err: any) => {
          console.error("UI events subscription error:", err)
        },
      })
      subRef.current = sub
    } catch (e) {
      console.error("Failed to subscribe to UI events:", e)
    }
    return () => {
      try {
        subRef.current?.unsubscribe?.()
      } catch {}
      subRef.current = null
    }
  }, [tenantId, onEvent])

  return null
}


