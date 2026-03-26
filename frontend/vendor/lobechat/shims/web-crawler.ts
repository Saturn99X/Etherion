// Minimal types to satisfy '@lobechat/web-crawler' imports from vendored Lobe app-types
// Mirrors Lobe package definitions found in packages/web-crawler/src/type.ts
export interface CrawlSuccessResult {
  content?: string;
  contentType: 'text' | 'json';
  description?: string;
  length?: number;
  siteName?: string;
  title?: string;
  url: string;
}

export interface CrawlErrorResult {
  content: string;
  errorMessage?: string;
  errorType?: string;
  url?: string;
}

export interface CrawlUniformResult {
  crawler: string;
  data: CrawlSuccessResult | CrawlErrorResult;
  originalUrl: string;
  transformedUrl?: string;
}
