# author: Toshihiko Aoki
# licence: MIT

import os
import subprocess

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

from .utils import (
    download,
    extract_files,
    classspath_from_pom,
    java_compile,
    junit_compile,
    run_junit,
    report_coverage,
)

server = Server("java_test_mcp")

build_path = os.environ.get('JAVA_BUILD_WORKSPACE', './junit_jacoco_jar_path')
workspace_path = os.environ.get("CLIENT_WORKSPACE", '.')
default_class_path = os.environ.get("DEFAULT_CLASSPATH_PATH", '')
pom_xml_path = os.environ.get("POM_XML_PATH", '')

if not os.path.isdir(build_path):
    jacoco_url = "https://search.maven.org/remotecontent?filepath=org/jacoco/jacoco/0.8.12/jacoco-0.8.12.zip"
    junit_url = "https://oss.sonatype.org/content/repositories/snapshots/org/junit/platform/junit-platform-console-standalone/1.10.6-SNAPSHOT/junit-platform-console-standalone-1.10.6-20241004.130129-1.jar"
    temp_jacoco_file = os.path.join(build_path, jacoco_url.split("/")[-1])
    os.makedirs(build_path)
    download(jacoco_url, temp_jacoco_file)
    extract_files(temp_jacoco_file, build_path)
    os.remove(temp_jacoco_file)
    download(junit_url, os.path.join(build_path, "junit.jar"))

if pom_xml_path:
    classpath_str = classspath_from_pom(pom_xml_path)
    if default_class_path:
        if classpath_str:
            default_class_path = default_class_path + os.pathsep + classpath_str
    else:
        default_class_path = classpath_str

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available Java testing tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="java_compile",
            description="Compile Java source files",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of Java source files or patterns (e.g. src/Hello.java, src/**/*.java)"
                    },
                    "classpath": {"type": "string",
                                  "description": "List of jar files or patterns (e.g. path/to/a.jar:path/to/lib/*)"},
                    "output_dir": {"type": "string", "description": "default values: main/bin"},
                },
                "required": ["source_files"]
            },
        ),
        types.Tool(
            name="junit_compile",
            description="Compile JUnit source files",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description":
                            "List of JUnit source files or patterns (e.g. src/HelloTest.java, src/**/*Test.java)"
                    },
                    "classpath": {
                        "type": "string",
                        "description": "List of jar files or patterns (e.g. path/to/a.jar:path/to/lib/*)"
                    },
                    "target_dir": {
                        "type": "string",
                        "description": "Compiled class directory to test (default: main/bin)",
                    },
                    "test_dir": {
                        "type": "string", "description": "Directory to output Junit classes (default: test/bin)",
                    },
                },
                "required": ["source_files"]
            },
        ),
        types.Tool(
            name="run_junit",
            description="Execute JUnit tests",
            inputSchema={
                "type": "object",
                "properties": {
                    "classpath": {"type": "string",
                                  "description": "List of jar files or patterns (e.g. path/to/a.jar:path/to/lib/*)"},
                    "target_dir": {"type": "string",
                                   "description": "Compiled class directory to test (default: main/bin)"
                    },
                    "test_dir": {
                        "type": "string",
                        "description": "Directory to output Junit classes (default: test/bin)"
                    },
                    "package_name": {"type": "string"},
                    "test_classes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of specific test classes to run (optional)"
                    }
                },
                "required": ["target_dir"]
            },
        ),
        types.Tool(
            name="report_coverage",
            description="Generate Jacoco coverage report",
            inputSchema={
                "type": "object",
                "properties": {
                    "classfiles_dir": {
                        "type": "string",
                        "description": "Compiled class directory to test (default: main/bin)",
                    },
                    "package_name": {
                        "type": "string",
                        "description": "Report target (e.g. com.example.report.target)",
                    },
                },
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle Java test tool execution requests.
    """
    if not arguments:
        raise ValueError("Missing arguments")

    if arguments.get('workspace_path') is None:
        arguments['workspace_path'] = workspace_path
    if arguments.get('build_path') is None:
        arguments['build_path'] = build_path
    if arguments.get('additional_classpath') is None:
        arguments['additional_classpath'] = default_class_path

    try:
        if name == "java_compile":
            result = await java_compile(**arguments)
            return [
                types.TextContent(
                    type="text",
                    text=str(result["result"])
                )
            ]
        elif name == "junit_compile":
            result = await junit_compile(**arguments)
            return [
                types.TextContent(
                    type="text",
                    text=str(result["result"])
                )
            ]
        elif name == "run_junit":
            result = await run_junit(**arguments)
            return [
                types.TextContent(
                    type="text",
                    text=str(result["result"])
                )
            ]
        elif name == "report_coverage":
            result = await report_coverage(**arguments)
            return [
                types.TextContent(
                    type="text",
                    text=str(result["result"])
                )
            ]
        else:
            raise ValueError(f"Unknown tool: {name}")
    except subprocess.CalledProcessError as e:
        std_error = 'unknown (decode failed).'
        if isinstance(e.stderr, str):
            std_error = e.stderr
        else:
            try:
                std_error = e.stderr.decode()
            except:
                pass
        return [
            types.TextContent(
                type="text",
                text=f"Command failed with exit code {e.returncode}:\n{std_error}",
            )
        ]
    except Exception as e:
        return [
            types.TextContent(
                type="text",
                text=f"Error: {str(e)}"
            )
        ]


async def main():
    """
    Main entry point for the Java MCP server
    """
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="java_test_mcp",
                server_version="0.1.1",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
