# Phase E UI Component Tests

This directory contains comprehensive unit tests for all Phase E UI components, verifying integration with Etherion bridges, stores, and GraphQL operations.

## Running Tests

### Run all tests
```bash
cd frontend/lobechat-app
npm run test
```

### Run tests in watch mode (for development)
```bash
npm run test:watch
```

### Run tests with coverage
```bash
npm run test:coverage
```

### Run specific test file
```bash
npm run test knowledge-browser
```

### Run tests for a specific section
```bash
npm run test -- __tests__/knowledge/
npm run test -- __tests__/registry/
npm run test -- __tests__/dashboard/
```

## Test Structure

```
__tests__/
├── setup.ts                    # Global test setup
├── mocks/
│   ├── bridges.ts              # Mock bridge implementations
│   ├── stores.ts               # Mock store implementations
│   └── apollo.ts               # Mock Apollo Client
├── knowledge/
│   └── knowledge-browser.test.tsx
├── registry/
│   ├── agent-registry.test.tsx
│   └── ...
├── dashboard/
│   ├── jobs-dashboard.test.tsx
│   └── ...
└── ... (other sections)
```

## Writing Tests

### Pattern 1: Bridge Integration Test

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { App } from 'antd';
import { YourComponent } from '../path/to/component';
import { mockBridgeFunction, setupBridgeMocks } from './mocks/bridges';

vi.mock('@etherion/bridge/module', () => ({
  bridgeFunction: mockBridgeFunction,
}));

describe('YourComponent', () => {
  beforeEach(() => {
    setupBridgeMocks();
  });

  it('should call bridge function on mount', async () => {
    render(
      <App>
        <YourComponent />
      </App>
    );

    await waitFor(() => {
      expect(mockBridgeFunction).toHaveBeenCalledWith(expectedParams);
    });
  });
});
```

### Pattern 2: Apollo Client Integration Test

```typescript
import { MockedProvider } from '@apollo/client/testing';
import { createApolloMocks } from './mocks/apollo';

describe('YourComponent', () => {
  it('should fetch data via GraphQL', async () => {
    const mocks = createApolloMocks();

    render(
      <MockedProvider mocks={mocks} addTypename={false}>
        <App>
          <YourComponent />
        </App>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Expected Data')).toBeInTheDocument();
    });
  });
});
```

### Pattern 3: Store Integration Test

```typescript
import { setupStoreMocks, mockJobStore } from './mocks/stores';

vi.mock('@etherion/stores/job-store', () => ({
  useJobStore: (selector?: any) => {
    if (typeof selector === 'function') {
      return selector(mockJobStore);
    }
    return mockJobStore;
  },
}));

describe('YourComponent', () => {
  beforeEach(() => {
    setupStoreMocks();
  });

  it('should read from store', () => {
    render(
      <App>
        <YourComponent jobId="job-1" />
      </App>
    );

    expect(screen.getByText(/job-1/i)).toBeInTheDocument();
  });
});
```

## Test Coverage Requirements

- **Line Coverage**: 80%+
- **Branch Coverage**: 70%+
- **Function Coverage**: 75%+
- **Statement Coverage**: 80%+

## Coverage Reports

After running `npm run test:coverage`, open the HTML report:

```bash
open coverage/app/index.html
```

## Mocking Guidelines

### Bridge Mocks

- Located in `mocks/bridges.ts`
- Use `setupBridgeMocks()` to initialize default mocks
- Use `resetBridgeMocks()` to clear mocks between tests
- Customize per-test with `mockBridgeFunction.mockResolvedValue(customData)`

### Store Mocks

- Located in `mocks/stores.ts`
- Use `setupStoreMocks()` to initialize default mocks
- Access mock stores directly: `mockJobStore`, `mockAuthStore`, etc.
- Update state: `mockJobStore.jobs['job-1'] = { ... }`

### Apollo Mocks

- Located in `mocks/apollo.ts`
- Use `createApolloMocks()` for default mocks
- Add custom mocks: `createApolloMocks([customMock])`
- Create error mocks: `createErrorMock(query, variables, errorMessage)`

## Common Issues

### Issue: "Cannot find module '@etherion/bridge/...'"

**Solution**: Make sure the bridge module is mocked before importing the component:

```typescript
vi.mock('@etherion/bridge/knowledge', () => ({
  listKnowledgeItems: mockListKnowledgeItems,
}));
```

### Issue: "AntD component not rendering"

**Solution**: Wrap component in `<App>` provider:

```typescript
render(
  <App>
    <YourComponent />
  </App>
);
```

### Issue: "Apollo query not resolving"

**Solution**: Use `waitFor()` for async operations:

```typescript
await waitFor(() => {
  expect(screen.getByText('Data')).toBeInTheDocument();
});
```

### Issue: "Store selector not working"

**Solution**: Make sure the mock store returns the selector result:

```typescript
vi.mock('@etherion/stores/job-store', () => ({
  useJobStore: (selector?: any) => {
    if (typeof selector === 'function') {
      return selector(mockJobStore);
    }
    return mockJobStore;
  },
}));
```

## Best Practices

1. **Always wrap components in `<App>` provider** for AntD components
2. **Use `waitFor()` for async operations** (bridge calls, GraphQL queries)
3. **Reset mocks between tests** with `beforeEach()` hooks
4. **Test user interactions** with `userEvent` from `@testing-library/user-event`
5. **Test error states** by mocking rejected promises
6. **Test loading states** by mocking delayed promises
7. **Test empty states** by mocking empty data arrays
8. **Keep tests focused** - one assertion per test when possible
9. **Use descriptive test names** - "should do X when Y happens"
10. **Avoid testing implementation details** - test behavior, not internals

## CI/CD Integration

Tests run automatically on:
- Every push to `main` or `develop` branches
- Every pull request

PRs are blocked if:
- Any test fails
- Coverage drops below thresholds

## Resources

- [Vitest Documentation](https://vitest.dev/)
- [React Testing Library](https://testing-library.com/react)
- [Apollo Client Testing](https://www.apollographql.com/docs/react/development-testing/testing/)
- [Zustand Testing](https://docs.pmnd.rs/zustand/guides/testing)
- [AntD Testing](https://ant.design/docs/react/testing)
