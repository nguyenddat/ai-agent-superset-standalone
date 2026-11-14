import asyncio
import sys
import unittest

from mcp import StdioServerParameters
from mcp.client import Client

from backend.mcp_server.server import mcp


class McpServerTests(unittest.TestCase):
    def test_in_memory_handshake_has_no_tools_yet(self) -> None:
        async def check() -> None:
            async with Client(mcp) as client:
                self.assertEqual((await client.list_tools()).tools, [])
                self.assertEqual((await client.list_resources()).resources, [])

        asyncio.run(check())

    def test_stdio_handshake_has_no_tools_yet(self) -> None:
        async def check() -> None:
            process = StdioServerParameters(
                command=sys.executable, args=["-m", "backend.mcp_server"],
            )
            async with Client(process) as client:
                self.assertEqual((await client.list_tools()).tools, [])
                self.assertEqual((await client.list_resources()).resources, [])

        asyncio.run(check())
