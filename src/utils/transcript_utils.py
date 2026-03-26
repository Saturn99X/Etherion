from typing import List, Dict, Any
import json

def generate_markdown_transcript(steps: List[Dict[str, Any]]) -> str:
    """
    Generate a linearized markdown transcript from execution trace steps.
    """
    md = []
    # Header
    if steps:
        job_id = steps[0].get("job_id", "unknown")
        md.append(f"# Execution Transcript - {job_id}")
        md.append(f"Generated at: {steps[0].get('timestamp', '')}")
        md.append("")

    for s in steps:
        actor = (s.get("actor") or "unknown").upper()
        event_type = (s.get("event_type") or "unknown").upper()
        timestamp = s.get("timestamp", "")
        
        md.append(f"## [{timestamp}] {actor} - {event_type}")
        
        if s.get("thought"):
            md.append(f"**Thought:** {s['thought']}")
            md.append("")
            
        if s.get("action_tool"):
            md.append(f"**Tool Call:** `{s['action_tool']}`")
            if s.get("action_input"):
                md.append("```json")
                md.append(json.dumps(s['action_input'], indent=2))
                md.append("```")
            md.append("")
            
        if s.get("observation_result"):
            md.append("**Observation:**")
            md.append("```")
            md.append(str(s['observation_result'])[:5000]) # Cap for readability
            if len(str(s['observation_result'])) > 5000:
                md.append("... (truncated)")
            md.append("```")
            md.append("")

        if s.get("event_type") == "llm_request":
            md.append("<details><summary>LangChain Input Messages</summary>")
            md.append("")
            raw_data = s.get("raw_data") or {}
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except Exception:
                    raw_data = {}
            msgs = raw_data.get("langchain", {}).get("input_messages", [])
            for m in msgs:
                role = m.get("role", "unknown")
                content = m.get("content", "")
                md.append(f"### {role}")
                md.append(content)
                md.append("")
            md.append("</details>")
            md.append("")

        md.append("---")
        md.append("")
        
    return "\n".join(md)
