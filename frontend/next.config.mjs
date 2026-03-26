import path from 'path';

/** @type {import('next').NextConfig} */
const nextConfig = {
  // TODO: migrate to ESLint 9 flat config; until then, skip ESLint during build to avoid circular JSON error
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: false },
  // Silence monorepo lockfile root inference warning (moved from experimental)
  outputFileTracingRoot: path.resolve(process.cwd(), '..'),
  images: { unoptimized: true },
  webpack: (config) => {
    const root = process.cwd();
    config.resolve = config.resolve || {};
    config.resolve.alias = config.resolve.alias || {};
    // Point @lobechat/* to vendored sources
    config.resolve.alias['@lobechat/const'] = path.resolve(root, 'vendor/lobechat/const');
    config.resolve.alias['@lobechat/model-runtime'] = path.resolve(root, 'vendor/lobechat/model-runtime');
    config.resolve.alias['@lobechat/types'] = path.resolve(root, 'vendor/lobechat/app-types/index.ts');
    config.resolve.alias['@lobechat/types/src'] = path.resolve(root, 'vendor/lobechat/app-types/index.ts');
    config.resolve.alias['@lobechat/utils'] = path.resolve(root, 'vendor/lobechat/shims/utils.ts');
    config.resolve.alias['@lobehub/market-sdk'] = path.resolve(root, 'vendor/lobechat/shims/market-sdk.ts');
    config.resolve.alias['@lobehub/market-types'] = path.resolve(root, 'vendor/lobechat/shims/market-types.ts');
    config.resolve.alias['@lobehub/chat-plugin-sdk'] = path.resolve(root, 'vendor/lobechat/shims/chat-plugin-sdk.ts');
    config.resolve.alias['@lobehub/chat-plugin-sdk/lib/types/market'] = path.resolve(root, 'vendor/lobechat/shims/chat-plugin-sdk.ts');
    // Point model-bank to vendored sources
    config.resolve.alias['model-bank'] = path.resolve(root, 'vendor/lobechat/model-bank');
    // Map Lobe app-level feature/component imports to vendored copies
    config.resolve.alias['@/features/PluginDevModal'] = path.resolve(root, 'vendor/lobechat/features/PluginDevModal');
    config.resolve.alias['@/features/PluginStore'] = path.resolve(root, 'vendor/lobechat/features/PluginStore');
    config.resolve.alias['@/features/AgentSetting/AgentPlugin'] = path.resolve(root, 'vendor/lobechat/features/AgentSetting/AgentPlugin');
    config.resolve.alias['@/features/AgentPlugin'] = path.resolve(root, 'vendor/lobechat/features/AgentSetting/AgentPlugin');
    config.resolve.alias['@/features/AgentSetting'] = path.resolve(root, 'vendor/lobechat/features/AgentSetting');
    config.resolve.alias['@/features/ChatInput/ActionBar/Model'] = path.resolve(root, 'vendor/lobechat/features/ChatInput/ActionBar/Model');
    config.resolve.alias['@/features/ChatInput/ActionBar/Search'] = path.resolve(root, 'vendor/lobechat/features/ChatInput/ActionBar/Search');
    config.resolve.alias['@/features/ChatInput/ActionBar/Token'] = path.resolve(root, 'vendor/lobechat/features/ChatInput/ActionBar/Token');
    config.resolve.alias['@/store'] = path.resolve(root, 'vendor/lobechat/store');
    config.resolve.alias['@/components/InfoTooltip'] = path.resolve(root, 'vendor/lobechat/components/InfoTooltip');
    config.resolve.alias['@/components/Loading/UpdateLoading'] = path.resolve(root, 'vendor/lobechat/components/Loading/UpdateLoading');
    config.resolve.alias['@/components/mdx'] = path.resolve(root, 'vendor/lobechat/components/mdx');
    config.resolve.alias['@/components/Menu'] = path.resolve(root, 'vendor/lobechat/components/Menu');
    config.resolve.alias['@/components/Plugins'] = path.resolve(root, 'vendor/lobechat/components/Plugins');
    config.resolve.alias['@/components/PublishedTime'] = path.resolve(root, 'vendor/lobechat/components/PublishedTime.tsx');
    config.resolve.alias['@/components/ManifestPreviewer'] = path.resolve(root, 'vendor/lobechat/components/ManifestPreviewer');
    config.resolve.alias['@/components/InlineTable'] = path.resolve(root, 'vendor/lobechat/components/InlineTable');
    config.resolve.alias['@/components/KeyValueEditor'] = path.resolve(root, 'vendor/lobechat/components/KeyValueEditor');
    config.resolve.alias['@/components/MCPStdioCommandInput'] = path.resolve(root, 'vendor/lobechat/components/MCPStdioCommandInput');
    config.resolve.alias['@/config'] = path.resolve(root, 'vendor/lobechat/config');
    config.resolve.alias['@/utils/merge'] = path.resolve(root, 'vendor/lobechat/const/utils/merge.ts');
    config.resolve.alias['@/types'] = path.resolve(root, 'vendor/lobechat/app-types');
    config.resolve.alias['@/libs'] = path.resolve(root, 'libs');
    config.resolve.alias['@/const'] = path.resolve(root, 'vendor/lobechat/const');
    config.resolve.alias['@/services'] = path.resolve(root, 'vendor/lobechat/services');
    config.resolve.alias['@/utils'] = path.resolve(root, 'vendor/lobechat/utils');
    config.resolve.alias['@/features/ModelSelect'] = path.resolve(root, 'vendor/lobechat/features/ModelSelect');
    config.resolve.alias['@/features/ModelSwitchPanel'] = path.resolve(root, 'vendor/lobechat/features/ModelSwitchPanel');
    config.resolve.alias['@/hooks'] = path.resolve(root, 'hooks');
    config.resolve.alias['@lobechat/web-crawler'] = path.resolve(root, 'vendor/lobechat/shims/web-crawler.ts');
    config.resolve.alias['@lobechat/python-interpreter'] = path.resolve(root, 'vendor/lobechat/shims/python-interpreter.ts');
    return config;
  },
};

export default nextConfig;
