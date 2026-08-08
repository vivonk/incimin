from langchain_core.tools import StructuredTool
from pydantic import create_model, Field

def json_schema_to_pydantic(schema: dict, model_name: str):
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    fields = {}
    for name, prop in properties.items():
        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict
        }
        py_type = type_mapping.get(prop.get("type", "string"), str)
        if name in required:
            fields[name] = (py_type, Field(..., description=prop.get("description", "")))
        else:
            fields[name] = (py_type, Field(None, description=prop.get("description", "")))
    return create_model(model_name, **fields)

def create_mcp_tool_wrapper(session, mcp_tool):
    async def invoke_tool(**kwargs):
        res = await session.call_tool(mcp_tool.name, arguments=kwargs)
        if res.is_error:
            return f"Error: {res.content[0].text if res.content else 'Unknown'}"
        return res.content[0].text if res.content else "Success"
        
    # fallback schema if empty
    schema = getattr(mcp_tool, "input_schema", {}) or {}
    if not schema or "properties" not in schema:
        schema = {"properties": {}}

    pydantic_schema = json_schema_to_pydantic(schema, f"{mcp_tool.name.capitalize()}Schema")
        
    return StructuredTool(
        name=mcp_tool.name,
        description=mcp_tool.description or mcp_tool.name,
        func=lambda **kwargs: "Async only - use ainvoke",
        coroutine=invoke_tool,
        args_schema=pydantic_schema
    )
