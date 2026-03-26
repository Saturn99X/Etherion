"""
Mandatory KB Paradigm Instructions for Team Orchestrators and Specialists.

These instructions are forcefully appended to system prompts to ensure all agents
understand the Knowledge Base architecture and retrieval best practices.
"""

MANDATORY_KB_PARADIGM_INSTRUCTIONS = """
## KNOWLEDGE BASE PARADIGM (MANDATORY SYSTEM DIRECTIVE)

You have access to a BigQuery-native multimodal Knowledge Base. Understanding how to use it is CRITICAL.

### How the KB Works
1. **Semantic Search** (`unified_research_tool` or `multimodal_kb_search`): Returns document metadata and ranked relevance scores from BigQuery vector embeddings
2. **Content Retrieval** (`fetch_document_content`): Downloads the **full content** of a specific document from GCS

### GOLDEN RULE: Retrieve ONE File At A Time
- NEVER retrieve multiple files in parallel
- Retrieve the HIGHEST-RANKED result from your semantic search FIRST
- Analyze it COMPLETELY before deciding if you need another file
- If it doesn't contain what you need, THEN retrieve the next highest-ranked result

### Why This Matters
- Full document retrieval is expensive (cost + latency)
- Most answers are contained in the top 1-2 results
- Parallel retrieval wastes resources and confuses synthesis

### Semantic Search Best Practices
- Be VERY DETAILED in your search queries
- Include domain vocabulary, synonyms, expected content
- Use multiple search strategies if first attempt fails:
  - Try synonyms and related terms
  - Search for specific concepts mentioned in the user's goal
  - Consider what section headings or keywords might appear in the relevant document

### Citation Requirements
- Always cite the doc_id or filename when referencing KB content
- Never fabricate document content or citations
"""


def get_mandatory_tool_instructions(tool_names: list, tool_schemas: dict = None) -> str:
    """Generate mandatory tool usage instructions with schemas.
    
    Args:
        tool_names: List of approved tool names for this agent
        tool_schemas: Optional dict of {tool_name: schema_dict} for detailed instructions
    
    Returns:
        String to append to system prompt
    """
    if not tool_names:
        return "\n## APPROVED TOOLS\nNo tools are approved for this agent. You can only reason and synthesize."
    
    schema_text = ""
    if tool_schemas:
        for name, schema in tool_schemas.items():
            if schema:
                schema_text += f"\n### {name}\n"
                if isinstance(schema, dict):
                    if schema.get("description"):
                        schema_text += f"Description: {schema['description']}\n"
                    if schema.get("input_schema"):
                        schema_text += f"Input Schema: {schema['input_schema']}\n"
                    if schema.get("usage"):
                        schema_text += f"Usage: {schema['usage']}\n"
                else:
                    schema_text += f"{schema}\n"
    
    return f"""
## APPROVED TOOLS (MANDATORY)

You MUST only use tools that are in your approved list:
{', '.join(tool_names)}

If a tool is not in this list, you CANNOT use it. Do not hallucinate tool names.
{schema_text if schema_text else ''}
If you don\'t know how to use a tool, call `get_tool_usage_schema(tool_name)` first.
"""
