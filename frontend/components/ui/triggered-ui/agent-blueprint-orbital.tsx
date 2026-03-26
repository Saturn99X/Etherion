import React from 'react';

interface AgentBlueprintOrbitalProps {
  agentName: string;
  blueprintTitle: string;
  systemPromptPreview: React.ReactNode;
  toolsPreview: React.ReactNode;
  capabilitiesPreview: React.ReactNode;
  onApprove: () => void;
  onReject: () => void;
}

class AgentBlueprintOrbital extends React.Component<AgentBlueprintOrbitalProps> {
  render(): React.ReactElement {
    const {
      agentName,
      blueprintTitle,
      systemPromptPreview,
      toolsPreview,
      capabilitiesPreview,
      onApprove,
      onReject,
    } = this.props;

    return (
      <div className="agent-blueprint-orbital">
        {/* Central Agent Core */}
        <div className="agent-core">
          <h2>{agentName}</h2>
          <p>{blueprintTitle}</p>
        </div>

        {/* Orbital Spheres */}
        <div className="orbital-container">
          <div className="orbit-path main-orbit">
            <div className="sphere system-prompt-sphere">
              <div className="sphere-content">
                <h3>System Prompt</h3>
                <div className="preview-card">{systemPromptPreview}</div>
              </div>
            </div>
          </div>

          <div className="orbit-path secondary-orbit">
            <div className="sphere tools-sphere">
              <div className="sphere-content">
                <h3>Tools</h3>
                <div className="preview-card">{toolsPreview}</div>
              </div>
            </div>
          </div>

          <div className="orbit-path tertiary-orbit">
            <div className="sphere capabilities-sphere">
              <div className="sphere-content">
                <h3>Capabilities</h3>
                <div className="preview-card">{capabilitiesPreview}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Control Buttons */}
        <div className="control-buttons">
          <button className="approve-button" onClick={onApprove}>
            Approve
          </button>
          <button className="reject-button" onClick={onReject}>
            Reject
          </button>
        </div>
      </div>
    );
  }
}

export default AgentBlueprintOrbital;
