import json
import sys
import os

# Ensure src is in the path
sys.path.insert(0, os.getcwd())

from src.services.platform_orchestrator import AgentTeamCreator

def test_parse_blueprint_json_robustness():
    creator = AgentTeamCreator(tenant_id=1)
    
    # Case 1: Standard clean JSON
    clean_json = '{"agent_requirements": [], "tool_requirements": [], "team_structure": {}}'
    print("Testing clean JSON...")
    assert creator._parse_blueprint_json(clean_json) == json.loads(clean_json)
    
    # Case 2: Markdown code block
    markdown_json = '```json\n' + clean_json + '\n```'
    print("Testing markdown JSON...")
    assert creator._parse_blueprint_json(markdown_json) == json.loads(clean_json)
    
    # Case 3: Wrapped in text
    wrapped_json = 'Here is your blueprint: ' + clean_json + ' I hope you like it.'
    print("Testing wrapped JSON...")
    assert creator._parse_blueprint_json(wrapped_json) == json.loads(clean_json)
    
    # Case 4: Python-style quotes (the "cranky fallback" case)
    python_dict = "{'agent_requirements': [], 'tool_requirements': [], 'team_structure': {}}"
    print("Testing python-style dict...")
    assert creator._parse_blueprint_json(python_dict) == json.loads(clean_json)

    # Case 5: Gemini "list of parts" stringified
    # This happens when str(res) is called on a response that wraps the content
    gemini_parts = "[{'type': 'text', 'text': '{\\n \"agent_requirements\": []\\n}'}]"
    print("Testing Gemini list-of-parts string...")
    res = creator._parse_blueprint_json(gemini_parts)
    assert "agent_requirements" in res

    # Case 6: Nested dictionary from Gemini output
    gemini_dict = "{'type': 'text', 'text': '{\\n \"agent_requirements\": []\\n}'}"
    print("Testing Gemini dict-of-parts string...")
    res = creator._parse_blueprint_json(gemini_dict)
    assert "agent_requirements" in res

    print("\nALL ROBUSTNESS TESTS PASSED")

if __name__ == "__main__":
    test_parse_blueprint_json_robustness()
