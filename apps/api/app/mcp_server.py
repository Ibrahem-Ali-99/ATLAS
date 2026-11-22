def main() -> None:
    """Serve read-only business tools over MCP stdio.

    Logging stays on stderr. Stdout is the JSON-RPC stream.
    """

    import logging
    import os
    import sys
    import uuid

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, force=True)
    from app.integrations.business_tools import build_server

    organization_id = uuid.UUID(os.environ["ATLAS_MCP_ORGANIZATION_ID"])
    build_server(organization_id).run(transport="stdio")


if __name__ == "__main__":
    main()
