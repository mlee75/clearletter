"""The same two tools, served over MCP (Model Context Protocol).

Used only by the Claude Code backend: Claude Code starts this small server
and can then call glossary_lookup and readability_check, exactly like the
API backend's tool runner does. The tool logic itself lives in tools.py.

Run by Claude Code as:  python -m clearletter.mcp_tools
"""

from mcp.server.mcpserver import MCPServer

from .tools import lookup_term, readability

server = MCPServer("clearletter")


@server.tool()
def glossary_lookup(term: str) -> str:
    """Look up what a medical abbreviation means in plain English, using a fixed glossary.
    If the term is not in the glossary, do not guess its meaning."""
    return lookup_term(term)


@server.tool()
def readability_check(text: str, language: str) -> str:
    """Score how easy a draft is to read. Target: Reading Ease 70 or more, and for English
    a Flesch-Kincaid grade of 6 or less. language is "en", "fr" or "es"."""
    if language not in ("en", "fr", "es"):
        return "Error: language must be 'en', 'fr' or 'es'."
    return str(readability(text, language))


if __name__ == "__main__":
    server.run()
