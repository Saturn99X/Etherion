import { render, screen } from "@testing-library/react";
import { ExecutionTraceUI } from "@/components/ui/triggered-ui/execution-trace-ui";

jest.mock("@/lib/apollo-client", () => {
  const subscribe = jest.fn(() => ({ subscribe: jest.fn(() => ({ unsubscribe: jest.fn() })) }));
  return { apolloClient: { subscribe } };
});

describe("ExecutionTraceUI", () => {
  it("renders card heading", () => {
    render(<ExecutionTraceUI jobId="job_test" />);
    expect(screen.getByText(/Execution Trace/i)).toBeInTheDocument();
  });
});


