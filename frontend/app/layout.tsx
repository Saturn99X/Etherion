import type React from "react"
import type { Metadata } from "next"
import { ThemeProvider } from "@/components/theme-provider"
import { ApolloProvider } from "@/components/apollo-provider"
import { AuthBootstrap } from "@/components/auth-bootstrap"
import { UIEventHandler } from "@/components/ui/ui-event-handler"
import { TenantBridge } from "@/components/tenant-bridge"
import { Suspense } from "react"
import Script from "next/script"
import { Toaster } from "@/components/ui/toaster"
import 'antd/dist/reset.css'
import "./globals.css"

// Force dynamic rendering so runtime env is injected at request time
export const dynamic = "force-dynamic"
export const revalidate = 0


export const metadata: Metadata = {
  title: "Etherion",
  description: "High-tech AI platform",
  generator: "v0.app",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  // Runtime env for client-side code; values are provided by Cloud Run env vars
  const runtimeEnv = {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "",
    NEXT_PUBLIC_GRAPHQL_ENDPOINT: process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT || "",
    NEXT_PUBLIC_GRAPHQL_WS_ENDPOINT: process.env.NEXT_PUBLIC_GRAPHQL_WS_ENDPOINT || "",
    NEXT_PUBLIC_AUTH_CALLBACK_URL: process.env.NEXT_PUBLIC_AUTH_CALLBACK_URL || "",
    NEXT_PUBLIC_GOOGLE_CLIENT_ID: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "",
    NEXT_PUBLIC_GITHUB_CLIENT_ID: process.env.NEXT_PUBLIC_GITHUB_CLIENT_ID || "",
    NEXT_PUBLIC_MICROSOFT_CLIENT_ID: process.env.NEXT_PUBLIC_MICROSOFT_CLIENT_ID || "",
    NEXT_PUBLIC_MICROSOFT_TENANT_ID: process.env.NEXT_PUBLIC_MICROSOFT_TENANT_ID || "",
    NEXT_PUBLIC_BYPASS_AUTH: process.env.NEXT_PUBLIC_BYPASS_AUTH || "",
  };

  return (
    <html lang="en">
      <body className={`font-sans antialiased`}>
        {/* Inject runtime env early, but place within <body> to satisfy HTML structure */}
        <Script
          id="runtime-env"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: `window.ENV = ${JSON.stringify(runtimeEnv)};` }}
        />
        <Suspense fallback={null}>
          <AuthBootstrap>
            <ApolloProvider>
              <TenantBridge>
                <ThemeProvider>
                  {children}
                  {/* Existing handler (legacy confirmation modal path) */}
                  <UIEventHandler />
                  {/* Global toast notifications */}
                  <Toaster />
                </ThemeProvider>
              </TenantBridge>
            </ApolloProvider>
          </AuthBootstrap>
        </Suspense>
        {/* runtime ENV injected via beforeInteractive Script above */}
        {/* Analytics component removed */}
      </body>
    </html>
  )
}
