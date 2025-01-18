import asyncio
import os
import subprocess
import xml.etree.ElementTree as ET
from typing import Optional, List
import glob

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

server = Server("java_test_mcp")

workspace_path = os.environ.get('JAVA_BUILD_WORKSPACE', './junit_jacoco_jar_path')
client_workspace_path = os.environ.get("CLIENT_WORKSPACE", '.')

if not os.path.isdir(workspace_path):
    from .download_jar import download, extract_files
    jacoco_url = "https://search.maven.org/remotecontent?filepath=org/jacoco/jacoco/0.8.12/jacoco-0.8.12.zip"
    junit_url =  "https://oss.sonatype.org/content/repositories/snapshots/org/junit/platform/junit-platform-console-standalone/1.10.6-SNAPSHOT/junit-platform-console-standalone-1.10.6-20241004.130129-1.jar"
    temp_jacoco_file = os.path.join(workspace_path, jacoco_url.split("/")[-1])
    os.makedirs(workspace_path)
    download(jacoco_url, temp_jacoco_file)
    extract_files(temp_jacoco_file, workspace_path)
    os.remove(temp_jacoco_file)
    download(junit_url, os.path.join(workspace_path, "junit.jar"))

def resolve_workspace_path(relative_path: str) -> str:
    if os.path.isabs(relative_path):
        return relative_path
    return os.path.join(client_workspace_path, relative_path)

def resolve_classpath(classpath: Optional[str]) -> str:
    """
    Resolve classpath entries relative to client workspace
    Handles multiple classpath entries separated by ':'
    """
    if not classpath:
        return "."
        
    entries = classpath.split(":")
    resolved_entries = []
    
    for entry in entries:
        if '*' in entry:
            base_dir = os.path.dirname(entry)
            base_dir = resolve_workspace_path(base_dir)
            pattern = os.path.join(base_dir, os.path.basename(entry))
            if '**' in pattern:
                matched_files = glob.glob(pattern, recursive=True)
            else:
                matched_files = glob.glob(pattern)
            resolved_entries.extend(matched_files)
        else:
            resolved_entries.append(resolve_workspace_path(entry))
            
    return ":".join(resolved_entries)

def resolve_file_list(files: List[str]) -> List[str]:
    """
    Resolve a list of files, handling both individual files and wildcards
    """
    resolved_files = []
    for file_path in files:
        if '*' in file_path:
            base_dir = os.path.dirname(file_path)
            base_dir = resolve_workspace_path(base_dir)
            pattern = os.path.join(base_dir, os.path.basename(file_path))
            if '**' in pattern:
                matched_files = glob.glob(pattern, recursive=True)
            else:
                matched_files = glob.glob(pattern)
            resolved_files.extend(matched_files)
        else:
            resolved_files.append(resolve_workspace_path(file_path))
    return resolved_files

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available Java testing tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="compile_java",
            description="Compile Java source files",
            inputSchema={
                "type": "object",
                "properties": {
                    "java_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of Java source files or patterns (e.g. src/**/*.java)"
                    },
                    "classpath": {"type": "string"},
                    "output_dir": {"type": "string", "description": "default values: ./bin"},
                },
                "required": ["java_files"]
            },
        ),
        types.Tool(
            name="compile_junit",
            description="Compile JUnit test files",
            inputSchema={
                "type": "object",
                "properties": {
                    "java_test_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of Java test files or patterns (e.g. test/**/*Test.java)"
                    },
                    "classpath": {"type": "string"},
                    "output_dir": {"type": "string", "description": "default values: ./bin"},
                },
                "required": ["java_test_files"]
            },
        ),
        types.Tool(
            name="run_junit",
            description="Execute JUnit tests",
            inputSchema={
                "type": "object",
                "properties": {
                    "classpath": {"type": "string"},
                    "output_dir": {"type": "string", "description": "default values: ./bin"},
                    "package_name": {"type": "string"},
                    "test_classes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of specific test classes to run (optional)"
                    }
                },
                "required": ["output_dir"]
            },
        ),
        types.Tool(
            name="generate_coverage",
            description="Generate Jacoco coverage report",
            inputSchema={
                "type": "object",
                "properties": {
                    "classfiles_root_path": {"type": "string"},
                    "package_name": {"type": "string"}
                },
                "required": ["classfiles_root_path"]
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

    try:
        if name == "compile_java":
            return await compile_java(arguments)
        elif name == "compile_junit":
            return await compile_junit(arguments)
        elif name == "run_junit":
            return await run_junit(arguments)
        elif name == "generate_coverage":
            return await generate_coverage(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")
    except subprocess.CalledProcessError as e:
        raise e
        return [
            types.TextContent(
                type="text",
                text=f"Command failed with exit code {e.returncode}:\n{e.stderr.decode()}"
            )
        ]
    except Exception as e:
        return [
            types.TextContent(
                type="text",
                text=f"Error: {str(e)}"
            )
        ]

async def compile_java(arguments: dict) -> list[types.TextContent]:
    java_files = arguments.get("java_files", [])
    output_dir = resolve_workspace_path(arguments.get("output_dir", "bin"))
    classpath = resolve_classpath(arguments.get("classpath"))

    resolved_files = resolve_file_list(java_files)
    if not resolved_files:
        raise ValueError("No Java files found to compile")

    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        "javac",
        "-d", output_dir,
        "-cp", f".:{classpath}",
        *resolved_files
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, cmd, stdout, stderr
        )
    
    return [
        types.TextContent(
            type="text",
            text=f"Successfully compiled {len(resolved_files)} Java files"
        )
    ]

async def compile_junit(arguments: dict) -> list[types.TextContent]:
    test_files = arguments.get("java_test_files", [])
    output_dir = resolve_workspace_path(arguments.get("output_dir", "bin"))
    classpath = resolve_classpath(arguments.get("classpath"))

    resolved_files = resolve_file_list(test_files)
    if not resolved_files:
        raise ValueError("No test files found to compile")
    
    os.makedirs(output_dir, exist_ok=True)
    
    cmd = [
        "javac",
        "-d", output_dir,
        "-cp", f".:{classpath}:{output_dir}:{workspace_path}/junit.jar",
        *resolved_files
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, cmd, stdout, stderr
        )
    
    return [
        types.TextContent(
            type="text",
            text=f"Successfully compiled {len(resolved_files)} test files"
        )
    ]

async def run_junit(arguments: dict) -> list[types.TextContent]:
    package_name = arguments.get("package_name", "")
    output_dir = resolve_workspace_path(arguments.get("output_dir", "bin"))
    classpath = resolve_classpath(arguments.get("classpath", ""))
    test_classes = arguments.get("test_classes", [])

    junit_includes = f"{package_name}.*" if package_name else ".*"
    
    cmd = [
        "java",
        f"-javaagent:{workspace_path}/jacocoagent.jar=destfile={workspace_path}/jacoco.exec,includes={junit_includes}",
        "-cp",
        f"{output_dir}:{workspace_path}/{classpath}:{workspace_path}/junit.jar",
        "org.junit.platform.console.ConsoleLauncher",
    ]

    if test_classes:
        for test_class in test_classes:
            cmd.extend(["--select-class", package_name + '.' + test_class])
    else:
        cmd.extend(["--scan-classpath", output_dir])
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, cmd, stdout, stderr
        )
    
    return [
        types.TextContent(
            type="text",
            text=f"JUnit test execution completed:\n{stdout.decode()}"
        )
    ]

async def generate_coverage(arguments: dict) -> list[types.TextContent]:
    classfiles = resolve_workspace_path(arguments.get("classfiles_root_path", "bin"))
    package_name = arguments.get("package_name", "")
    
    jacoco_classfiles = f"{classfiles}/{package_name.replace('.', '/')}" if package_name else classfiles
    os.makedirs(f"{workspace_path}/jacoco-report", exist_ok=True)
    
    cmd = [
        "java",
        "-jar",
        f"{workspace_path}/jacococli.jar",
        "report",
        f"{workspace_path}/jacoco.exec",
        "--classfiles",
        jacoco_classfiles,
        "--sourcefiles",
        ".",
        "--xml",
        f"{workspace_path}/jacoco-report/jacoco.xml"
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, cmd, stdout, stderr
        )
    
    coverage_data = parse_coverage_report()
    return [
        types.TextContent(
            type="text",
            text=f"Coverage report generated successfully:\n{coverage_data}"
        )
    ]

def parse_coverage_report() -> dict:
    """
    Parse Jacoco coverage report XML and extract coverage data
    """
    coverage_data = {}
    tree = ET.parse(f"{workspace_path}/jacoco-report/jacoco.xml")
    root = tree.getroot()
    
    for package in root.findall(".//package"):
        package_name = package.get("name")
        coverage_data[package_name] = {}
        
        for class_element in package.findall("class"):
            class_name = class_element.get("name")
            line_coverage = 0
            line_covered = 0
            
            for counter in class_element.findall("counter"):
                if counter.get("type") == "LINE":
                    line_coverage = int(counter.get("missed")) + int(counter.get("covered"))
                    line_covered = int(counter.get("covered"))
                    break
            
            coverage_percentage = (line_covered / line_coverage) * 100 if line_coverage > 0 else 0
            coverage_data[package_name][class_name] = {
                "coverage_percentage": round(coverage_percentage, 2),
                "lines_covered": line_covered,
                "total_lines": line_coverage
            }
    
    return coverage_data

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
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
