import React, { FC, PropsWithChildren } from 'react';

// Minimal mdx components mapping to pass through MDX rendering
export const mdxComponents: Record<string, any> = {};

export const Pre: FC<PropsWithChildren<{ [k: string]: any }>> = ({ children, ...rest }) => (
  <pre style={{ overflowX: 'auto', padding: 12, background: 'var(--code-bg, #0b1020)', borderRadius: 8 }} {...rest}>
    {children}
  </pre>
);

export const PreSingleLine: FC<PropsWithChildren<{ [k: string]: any }>> = ({ children, ...rest }) => (
  <pre style={{ whiteSpace: 'pre', overflow: 'hidden', textOverflow: 'ellipsis', padding: 8, background: 'var(--code-bg, #0b1020)', borderRadius: 6 }} {...rest}>
    {children}
  </pre>
);
