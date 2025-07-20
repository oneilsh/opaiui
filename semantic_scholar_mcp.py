from mcp.server.fastmcp import FastMCP
from semanticscholar import SemanticScholar

mcp = FastMCP("Semantic Scholar MCP Server")


@mcp.tool()
def search_papers(search_query: str) -> list[dict]:
    """Search for papers using Semantic Scholar."""
    sch = SemanticScholar()
    return sch.search_paper(search_query, fields=["title", "year", "citationCount", "authors", "publicationVenue", "tldr"]).raw_data


@mcp.tool()
def search_authors(search_query: str) -> str:
    """Search for authors using Semantic Scholar."""
    sch = SemanticScholar()
    return sch.search_author(search_query).raw_data


if __name__ == "__main__":
    mcp.run()
