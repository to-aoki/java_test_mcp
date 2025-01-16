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
                "compile_java", {
                    "java_files": [os.getcwd() + "/tests/src/com/examples/HelloWorld.java"],
                    "output_dir": os.getcwd() + "/bin"
                }
            )
            print(result)
            result = await session.call_tool(
                "compile_junit", {
                    "java_test_files": [os.getcwd() + "/tests/src/**/*Test.java"],
                    "output_dir": os.getcwd() + "/bin"
                }
            )
            print(result)
            result = await session.call_tool(
                "run_junit", {
                    "output_dir": os.getcwd() + "/bin",
                    "package_name": "com.example"
                }
            )
            print(result)
            result = await session.call_tool(
                "generate_coverage", {
                    "output_dir": os.getcwd() + "/bin",
                    "package_name": "com.example"
                }
            )
            print(result)


asyncio.run(main())