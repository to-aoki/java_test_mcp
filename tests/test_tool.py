import asyncio
import os
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    async with stdio_client(
        StdioServerParameters(command="uv", args=["run", "java_test_mcp"])
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools
            tools = await session.list_tools()
            for t in tools:
                if t[0] == 'tools':
                    for tool in t[1]:
                        print(tool)

            # Call tool
            result = await session.call_tool(
                "java_compile", {
                    "source_files": [os.getcwd() + "/tests/main/src/com/examples/*.java"],
                    "output_dir": os.getcwd() + "/main/bin"
                }
            )
            print(result)
            result = await session.call_tool(
                "junit_compile", {
                    "source_files": [os.getcwd() + "/tests/main/test/**/*Test.java"],
                    "target_dir": os.getcwd() + "/main/bin",
                    "output_dir": os.getcwd() + "/test/bin"
                }
            )
            print(result)
            result = await session.call_tool(
                "run_junit", {
                    "target_dir": os.getcwd() + "/main/bin",
                    "test_dir": os.getcwd() + "/test/bin",
                    "package_name": "com.example"
                }
            )
            print(result)
            result = await session.call_tool(
                "report_coverage", {
                    "classfiles_dir": os.getcwd() + "/main/bin",
                    "package_name": "com.example",
                }
            )
            print(result)


asyncio.run(main())