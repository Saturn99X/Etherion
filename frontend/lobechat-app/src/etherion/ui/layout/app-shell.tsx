"use client";

import React from 'react';
import { ApolloProvider } from './apollo-provider';
import { AuthBootstrap } from './auth-bootstrap';
import { UIEventDispatcherProvider } from './ui-event-dispatcher';
import { TenantBridge } from './tenant-bridge';

import { AuthGuard } from '../auth/auth-guard';

/**
 * AppShell wraps the application with all necessary Etherion context providers.
 * It should be mounted high in the layout tree.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
    return (
        <ApolloProvider>
            <AuthBootstrap>
                <AuthGuard>
                    <TenantBridge>
                        <UIEventDispatcherProvider>
                            {children}
                        </UIEventDispatcherProvider>
                    </TenantBridge>
                </AuthGuard>
            </AuthBootstrap>
        </ApolloProvider>
    );
}
