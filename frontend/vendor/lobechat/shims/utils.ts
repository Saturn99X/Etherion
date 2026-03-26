// Minimal shims for @lobechat/utils used in Lobe mcp.ts
export const isLocalOrPrivateUrl = (url: string): boolean => {
  try {
    const u = new URL(url);
    const host = u.hostname;
    if (host === 'localhost' || host === '127.0.0.1' || host === '::1') return true;
    // Basic private network checks
    if (/^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)/.test(host)) return true;
    // IP literal
    if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) return true;
    return host.endsWith('.local');
  } catch {
    return false;
  }
};

export const safeParseJSON = <T = any>(str: string, fallback?: T): T | null => {
  try {
    return JSON.parse(str) as T;
  } catch {
    return fallback ?? null;
  }
};
