
from mcp.server import MCPServer
from pydantic import BaseModel, Field

mcp = MCPServer("Content Publisher")


class PostDraft(BaseModel):
    content: str = Field(min_length=1, max_length=3000)
    platform: str = "linkedin"


@mcp.tool()
def preview_post(content: str) -> dict:
    """Valide un brouillon et renvoie son aperçu."""
    draft = PostDraft(content=content)

    return {
        "platform": draft.platform,
        "content": draft.content,
        "status": "pending_approval",
        "published": False,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
