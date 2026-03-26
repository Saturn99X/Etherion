import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentBlueprintOrbital } from "@/components/ui/triggered-ui/agent-blueprint-orbital";

const mockAgentBlueprint = {
  id: "bp1",
  name: "Content Marketing Agent",
  description: "Automated content creation and distribution",
  agents: [
    { id: "a1", name: "Content Writer", role: "content", status: "ready" },
    { id: "a2", name: "SEO Optimizer", role: "seo", status: "ready" },
    { id: "a3", name: "Social Publisher", role: "social", status: "ready" },
  ],
  workflow: {
    steps: [
      { id: "step1", name: "Research", agent: "a1" },
      { id: "step2", name: "Write Content", agent: "a1" },
      { id: "step3", name: "Optimize SEO", agent: "a2" },
      { id: "step4", name: "Publish", agent: "a3" },
    ],
  },
  estimatedCost: 25.5,
  estimatedTime: 45,
};

describe("AgentBlueprintOrbital", () => {
  describe("Rendering", () => {
    it("should render without crashing", () => {
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      expect(screen.getByText(/agent blueprint/i)).toBeInTheDocument();
    });

    it("should display blueprint name", () => {
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      expect(screen.getByText("Content Marketing Agent")).toBeInTheDocument();
    });

    it("should show blueprint description", () => {
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      expect(
        screen.getByText(/automated content creation/i),
      ).toBeInTheDocument();
    });

    it("should display all agents in orbit", () => {
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      expect(screen.getByText("Content Writer")).toBeInTheDocument();
      expect(screen.getByText("SEO Optimizer")).toBeInTheDocument();
      expect(screen.getByText("Social Publisher")).toBeInTheDocument();
    });

    it("should display loading state during animation", () => {
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          isAnimating={true}
        />,
      );
      expect(screen.getByRole("progressbar")).toBeInTheDocument();
    });

    it("should handle missing blueprint gracefully", () => {
      render(<AgentBlueprintOrbital blueprint={null} />);
      expect(screen.getByText(/no blueprint available/i)).toBeInTheDocument();
    });
  });

  describe("Orbital Animation", () => {
    it("should have orbital animation classes", () => {
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      const orbitContainer = screen.getByTestId("orbit-container");
      expect(orbitContainer).toHaveClass("orbital-animation");
    });

    it("should animate agents in different orbits", () => {
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      const agents = screen.getAllByTestId(/agent-sphere-/);
      expect(agents).toHaveLength(3);
      agents.forEach((agent, index) => {
        expect(agent).toHaveClass(`orbit-${index}`);
      });
    });

    it("should pause animation on hover", async () => {
      const user = userEvent.setup();
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);

      const orbitContainer = screen.getByTestId("orbit-container");
      await user.hover(orbitContainer);

      expect(orbitContainer).toHaveClass("animation-paused");
    });

    it("should resume animation when hover ends", async () => {
      const user = userEvent.setup();
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);

      const orbitContainer = screen.getByTestId("orbit-container");
      await user.hover(orbitContainer);
      await user.unhover(orbitContainer);

      expect(orbitContainer).not.toHaveClass("animation-paused");
    });

    it("should support different rotation speeds", () => {
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          rotationSpeed="fast"
        />,
      );
      const orbitContainer = screen.getByTestId("orbit-container");
      expect(orbitContainer).toHaveClass("rotation-fast");
    });
  });

  describe("Agent Information Display", () => {
    it("should show agent preview card on hover", async () => {
      const user = userEvent.setup();
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);

      const agent = screen.getByText("Content Writer");
      await user.hover(agent);

      await waitFor(() => {
        expect(screen.getByText(/role: content/i)).toBeInTheDocument();
        expect(screen.getByText(/status: ready/i)).toBeInTheDocument();
      });
    });

    it("should hide preview card on unhover", async () => {
      const user = userEvent.setup();
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);

      const agent = screen.getByText("Content Writer");
      await user.hover(agent);
      await user.unhover(agent);

      await waitFor(() => {
        expect(screen.queryByText(/role: content/i)).not.toBeInTheDocument();
      });
    });

    it("should show agent details on click", async () => {
      const user = userEvent.setup();
      const onAgentClick = jest.fn();
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          onAgentClick={onAgentClick}
        />,
      );

      const agent = screen.getByText("Content Writer");
      await user.click(agent);

      expect(onAgentClick).toHaveBeenCalledWith("a1");
    });

    it("should display agent status indicator", () => {
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      const statusIndicators = screen.getAllByTestId(/agent-status-/);
      expect(statusIndicators).toHaveLength(3);
      statusIndicators.forEach((indicator) => {
        expect(indicator).toHaveClass("status-ready");
      });
    });
  });

  describe("Workflow Visualization", () => {
    it("should display workflow steps", () => {
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showWorkflow={true}
        />,
      );
      expect(screen.getByText("Research")).toBeInTheDocument();
      expect(screen.getByText("Write Content")).toBeInTheDocument();
      expect(screen.getByText("Optimize SEO")).toBeInTheDocument();
      expect(screen.getByText("Publish")).toBeInTheDocument();
    });

    it("should show connections between agents", () => {
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showConnections={true}
        />,
      );
      const connections = screen.getAllByTestId(/connection-line-/);
      expect(connections.length).toBeGreaterThan(0);
    });

    it("should highlight workflow path on agent hover", async () => {
      const user = userEvent.setup();
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showWorkflow={true}
        />,
      );

      const agent = screen.getByText("Content Writer");
      await user.hover(agent);

      await waitFor(() => {
        const highlightedSteps = screen.getAllByTestId(/step-highlighted-/);
        expect(highlightedSteps.length).toBeGreaterThan(0);
      });
    });
  });

  describe("Blueprint Approval Controls", () => {
    it("should display approve and reject buttons", () => {
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showControls={true}
        />,
      );
      expect(
        screen.getByRole("button", { name: /approve/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /reject/i }),
      ).toBeInTheDocument();
    });

    it("should call onApprove when approve button is clicked", async () => {
      const user = userEvent.setup();
      const onApprove = jest.fn();
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showControls={true}
          onApprove={onApprove}
        />,
      );

      const approveButton = screen.getByRole("button", { name: /approve/i });
      await user.click(approveButton);

      expect(onApprove).toHaveBeenCalledWith("bp1");
    });

    it("should call onReject when reject button is clicked", async () => {
      const user = userEvent.setup();
      const onReject = jest.fn();
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showControls={true}
          onReject={onReject}
        />,
      );

      const rejectButton = screen.getByRole("button", { name: /reject/i });
      await user.click(rejectButton);

      expect(onReject).toHaveBeenCalledWith("bp1");
    });

    it("should show confirmation dialog before approval", async () => {
      const user = userEvent.setup();
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showControls={true}
          requireConfirmation={true}
        />,
      );

      const approveButton = screen.getByRole("button", { name: /approve/i });
      await user.click(approveButton);

      await waitFor(() => {
        expect(screen.getByText(/confirm approval/i)).toBeInTheDocument();
      });
    });

    it("should disable controls during processing", () => {
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showControls={true}
          isProcessing={true}
        />,
      );

      const approveButton = screen.getByRole("button", { name: /approve/i });
      const rejectButton = screen.getByRole("button", { name: /reject/i });

      expect(approveButton).toBeDisabled();
      expect(rejectButton).toBeDisabled();
    });
  });

  describe("Cost and Time Estimates", () => {
    it("should display estimated cost", () => {
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showEstimates={true}
        />,
      );
      expect(screen.getByText(/\$25\.50/)).toBeInTheDocument();
    });

    it("should display estimated time", () => {
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showEstimates={true}
        />,
      );
      expect(screen.getByText(/45.*minutes/i)).toBeInTheDocument();
    });

    it("should show cost breakdown on hover", async () => {
      const user = userEvent.setup();
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showEstimates={true}
        />,
      );

      const costElement = screen.getByText(/\$25\.50/);
      await user.hover(costElement);

      await waitFor(() => {
        expect(screen.getByText(/cost breakdown/i)).toBeInTheDocument();
      });
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels", () => {
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      expect(
        screen.getByRole("region", { name: /agent blueprint/i }),
      ).toBeInTheDocument();
    });

    it("should have keyboard accessible agent spheres", async () => {
      const user = userEvent.setup();
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);

      await user.tab();
      const firstAgent = screen.getByText("Content Writer");
      expect(firstAgent.closest("button")).toHaveFocus();
    });

    it("should support keyboard navigation between agents", async () => {
      const user = userEvent.setup();
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);

      await user.tab();
      await user.tab();
      await user.tab();

      const thirdAgent = screen.getByText("Social Publisher");
      expect(thirdAgent.closest("button")).toHaveFocus();
    });

    it("should announce blueprint status to screen readers", () => {
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      expect(screen.getByRole("status")).toHaveTextContent(
        /blueprint ready for review/i,
      );
    });

    it("should have proper ARIA labels on controls", () => {
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showControls={true}
        />,
      );

      const approveButton = screen.getByRole("button", { name: /approve/i });
      const rejectButton = screen.getByRole("button", { name: /reject/i });

      expect(approveButton).toHaveAttribute("aria-label");
      expect(rejectButton).toHaveAttribute("aria-label");
    });

    it("should support reduced motion preferences", () => {
      // Mock prefers-reduced-motion
      window.matchMedia = jest.fn().mockImplementation((query) => ({
        matches: query === "(prefers-reduced-motion: reduce)",
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      }));

      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      const orbitContainer = screen.getByTestId("orbit-container");
      expect(orbitContainer).toHaveClass("motion-reduced");
    });
  });

  describe("Responsive Behavior", () => {
    it("should adapt layout for mobile screens", () => {
      global.innerWidth = 375;
      global.dispatchEvent(new Event("resize"));

      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      const container = screen.getByRole("region", {
        name: /agent blueprint/i,
      });
      expect(container).toHaveClass("mobile-layout");
    });

    it("should reduce orbit size on small screens", () => {
      global.innerWidth = 375;
      global.dispatchEvent(new Event("resize"));

      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      const orbitContainer = screen.getByTestId("orbit-container");
      expect(orbitContainer).toHaveClass("orbit-small");
    });

    it("should hide workflow details on mobile", () => {
      global.innerWidth = 375;
      global.dispatchEvent(new Event("resize"));

      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          showWorkflow={true}
        />,
      );
      expect(screen.queryByText(/workflow details/i)).not.toBeVisible();
    });
  });

  describe("Performance", () => {
    it("should render multiple agents efficiently", () => {
      const manyAgents = Array.from({ length: 20 }, (_, i) => ({
        id: `a${i}`,
        name: `Agent ${i}`,
        role: "worker",
        status: "ready",
      }));

      const largeBlueprint = {
        ...mockAgentBlueprint,
        agents: manyAgents,
      };

      const startTime = performance.now();
      render(<AgentBlueprintOrbital blueprint={largeBlueprint} />);
      const endTime = performance.now();

      expect(endTime - startTime).toBeLessThan(1000);
    });

    it("should use CSS animations for smooth performance", () => {
      render(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);
      const orbitContainer = screen.getByTestId("orbit-container");

      const computedStyle = window.getComputedStyle(orbitContainer);
      expect(computedStyle.animation).toBeTruthy();
    });

    it("should not re-render unnecessarily", () => {
      const { rerender } = render(
        <AgentBlueprintOrbital blueprint={mockAgentBlueprint} />,
      );
      const renderSpy = jest.fn();

      jest.spyOn(React, "createElement").mockImplementation(renderSpy);
      rerender(<AgentBlueprintOrbital blueprint={mockAgentBlueprint} />);

      expect(renderSpy).not.toHaveBeenCalled();
    });
  });

  describe("Interactive Features", () => {
    it("should zoom in on agent focus", async () => {
      const user = userEvent.setup();
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          enableZoom={true}
        />,
      );

      const agent = screen.getByText("Content Writer");
      await user.click(agent);

      await waitFor(() => {
        const orbitContainer = screen.getByTestId("orbit-container");
        expect(orbitContainer).toHaveClass("zoomed-in");
      });
    });

    it("should allow manual rotation control", async () => {
      const user = userEvent.setup();
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          allowManualRotation={true}
        />,
      );

      const orbitContainer = screen.getByTestId("orbit-container");

      fireEvent.mouseDown(orbitContainer, { clientX: 100 });
      fireEvent.mouseMove(orbitContainer, { clientX: 200 });
      fireEvent.mouseUp(orbitContainer);

      expect(orbitContainer).toHaveAttribute("data-rotated", "true");
    });

    it("should support pinch-to-zoom on touch devices", () => {
      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          enableZoom={true}
        />,
      );

      const orbitContainer = screen.getByTestId("orbit-container");

      fireEvent.touchStart(orbitContainer, {
        touches: [{ clientX: 100 }, { clientX: 200 }],
      });
      fireEvent.touchMove(orbitContainer, {
        touches: [{ clientX: 50 }, { clientX: 250 }],
      });

      expect(orbitContainer).toHaveClass("zoomed-in");
    });
  });

  describe("Error Handling", () => {
    it("should handle invalid agent data gracefully", () => {
      const invalidBlueprint = {
        ...mockAgentBlueprint,
        agents: [{ id: "a1", name: null, role: undefined }],
      };

      render(<AgentBlueprintOrbital blueprint={invalidBlueprint} />);
      expect(screen.getByText(/invalid agent data/i)).toBeInTheDocument();
    });

    it("should show error state on animation failure", () => {
      const consoleError = jest.spyOn(console, "error").mockImplementation();

      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          simulateAnimationError={true}
        />,
      );

      expect(screen.getByText(/animation error/i)).toBeInTheDocument();
      consoleError.mockRestore();
    });
  });

  describe("Integration with Blueprint System", () => {
    it("should display blueprint metadata", () => {
      const blueprintWithMeta = {
        ...mockAgentBlueprint,
        createdAt: "2024-01-15T10:00:00Z",
        createdBy: "John Doe",
        version: "1.0.0",
      };

      render(
        <AgentBlueprintOrbital
          blueprint={blueprintWithMeta}
          showMetadata={true}
        />,
      );

      expect(screen.getByText(/created by: john doe/i)).toBeInTheDocument();
      expect(screen.getByText(/version: 1\.0\.0/i)).toBeInTheDocument();
    });

    it("should support blueprint comparison mode", async () => {
      const user = userEvent.setup();
      const alternativeBlueprint = {
        ...mockAgentBlueprint,
        id: "bp2",
        name: "Alternative Blueprint",
      };

      render(
        <AgentBlueprintOrbital
          blueprint={mockAgentBlueprint}
          comparisonBlueprint={alternativeBlueprint}
          enableComparison={true}
        />,
      );

      const compareButton = screen.getByRole("button", { name: /compare/i });
      await user.click(compareButton);

      await waitFor(() => {
        expect(screen.getByText("Alternative Blueprint")).toBeInTheDocument();
      });
    });
  });
});
