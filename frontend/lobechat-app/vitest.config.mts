import { join, resolve } from 'node:path';
import { coverageConfigDefaults, defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      '@etherion/lib': resolve(__dirname, './src/etherion/lib'),
      '@etherion/stores': resolve(__dirname, './src/etherion/stores'),
      '@etherion/components': resolve(__dirname, './src/etherion/components'),
      '@etherion/vendor': resolve(__dirname, '../vendor/lobechat'),
      '@lobechat/const': resolve(__dirname, './packages/const/src'),
      '@lobechat/model-runtime': resolve(__dirname, './packages/model-runtime/src'),
      '@lobechat/types': resolve(__dirname, './packages/types/src'),
      'nanoid/non-secure': resolve(__dirname, './src/vendor/shims/nanoid-non-secure.ts'),
    },
  },
  optimizeDeps: {
    exclude: ['crypto', 'util', 'tty'],
    include: ['@lobehub/tts'],
  },
  test: {
    alias: {
      /* eslint-disable sort-keys-fix/sort-keys-fix */
      '@/database/_deprecated': resolve(__dirname, './src/database/_deprecated'),
      '@/database': resolve(__dirname, './packages/database/src'),
      '@/utils/client/switchLang': resolve(__dirname, './src/utils/client/switchLang'),
      '@/const/locale': resolve(__dirname, './src/const/locale'),
      // TODO: after refactor the errorResponse, we can remove it
      '@/utils/errorResponse': resolve(__dirname, './src/utils/errorResponse'),
      '@/utils/unzipFile': resolve(__dirname, './src/utils/unzipFile'),
      '@/utils': resolve(__dirname, './packages/utils/src'),
      '@/types': resolve(__dirname, './packages/types/src'),
      '@/const': resolve(__dirname, './packages/const/src'),
      '@': resolve(__dirname, './src'),
      '~test-utils': resolve(__dirname, './tests/utils.tsx'),
      '@etherion/lib': resolve(__dirname, './src/etherion/lib'),
      '@etherion/stores': resolve(__dirname, './src/etherion/stores'),
      '@etherion/components': resolve(__dirname, './src/etherion/components'),
      '@etherion/vendor': resolve(__dirname, '../vendor/lobechat'),
      '@lobechat/const': resolve(__dirname, './packages/const/src'),
      '@lobechat/model-runtime': resolve(__dirname, './packages/model-runtime/src'),
      '@lobechat/types': resolve(__dirname, './packages/types/src'),
      'nanoid/non-secure': resolve(__dirname, './src/vendor/shims/nanoid-non-secure.ts'),
      /* eslint-enable */
    },
    coverage: {
      all: false,
      exclude: [
        // https://github.com/lobehub/lobe-chat/pull/7265
        ...coverageConfigDefaults.exclude,
        '__mocks__/**',
        '**/packages/**',
        // just ignore the migration code
        // we will use pglite in the future
        // so the coverage of this file is not important
        'src/database/client/core/db.ts',
        'src/utils/fetch/fetchEventSource/*.ts',
      ],
      provider: 'v8',
      reporter: ['text', 'json', 'lcov', 'text-summary'],
      reportsDirectory: './coverage/app',
    },
    environment: 'happy-dom',
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/build/**',
      '**/apps/desktop/**',
      '**/apps/mobile/**',
      '**/packages/**',
      '**/e2e/**',
    ],
    globals: true,
    server: {
      deps: {
        inline: ['vitest-canvas-mock'],
      },
    },
    setupFiles: join(__dirname, './tests/setup.ts'),
  },
});
