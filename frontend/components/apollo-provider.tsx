"use client";

import React, { createContext, useContext, useEffect, useState } from 'react';
import { getClient } from '@/lib/apollo-client';
import { ApolloClient, ApolloProvider as ApolloRootProvider } from '@apollo/client';

// Export a shared client reference for modules that cannot use hooks (e.g., stores)
export let apolloClient: ApolloClient<any> | null = null;

// Create a context for optional direct client access in custom hooks
const ApolloClientContext = createContext(null as ApolloClient<any> | null);

interface ApolloProviderProps {
  children: React.ReactNode;
}

export function ApolloProvider({ children }: ApolloProviderProps) {
  const [client, setClient] = useState<ApolloClient<any> | null>(null);

  useEffect(() => {
    const c = getClient();
    apolloClient = c;
    setClient(c);
  }, []);

  if (!client) {
    return null; // Or a loading spinner
  }

  // Wrap with the official ApolloProvider so useQuery/useMutation work,
  // and keep our custom context for components using useApolloClient().
  return (
    <ApolloRootProvider client={client}>
      <ApolloClientContext.Provider value={client}>
        {children}
      </ApolloClientContext.Provider>
    </ApolloRootProvider>
  );
}

// Custom hook to use Apollo Client directly (optional)
export function useApolloClient() {
  const client = useContext(ApolloClientContext);
  if (!client) {
    throw new Error('useApolloClient must be used within an ApolloProvider');
  }
  return client;
}
