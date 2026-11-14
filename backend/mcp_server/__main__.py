import argparse
import ipaddress

from .server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Superset AI MCP server")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.transport == "streamable-http":
        try:
            if not ipaddress.ip_address(args.host).is_loopback:
                parser.error("MCP HTTP hiện chỉ được phép lắng nghe trên địa chỉ loopback.")
        except ValueError:
            parser.error("--host phải là địa chỉ IP loopback.")
        mcp.run(
            transport="streamable-http", host=args.host, port=args.port,
            stateless_http=True, json_response=True,
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
