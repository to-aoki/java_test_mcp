import asyncio
import os
import subprocess
import xml.etree.ElementTree as ET
from typing import Optional, List
import glob
import re

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

server = Server("java_test_mcp")

workspace_path = os.environ.get('JAVA_BUILD_WORKSPACE', './junit_jacoco_jar_path')
client_workspace_path = os.environ.get("CLIENT_WORKSPACE", '.')
default_class_path = os.environ.get("DEFAULT_CLASSPATH_PATH", '')
pom_xml_path = os.environ.get("POM_XML_PATH", '')

if not os.path.isdir(workspace_path):
    from .utils import download, extract_files
    jacoco_url = "https://search.maven.org/remotecontent?filepath=org/jacoco/jacoco/0.8.12/jacoco-0.8.12.zip"
    junit_url =  "https://oss.sonatype.org/content/repositories/snapshots/org/junit/platform/junit-platform-console-standalone/1.10.6-SNAPSHOT/junit-platform-console-standalone-1.10.6-20241004.130129-1.jar"
    temp_jacoco_file = os.path.join(workspace_path, jacoco_url.split("/")[-1])
    os.makedirs(workspace_path)
    download(jacoco_url, temp_jacoco_file)
    extract_files(temp_jacoco_file, workspace_path)
    os.remove(temp_jacoco_file)
    download(junit_url, os.path.join(workspace_path, "junit.jar"))

if pom_xml_path:
    from .utils import classspath_from_pom
    classpath_str = classspath_from_pom(pom_xml_path)
    if classpath_str:
        default_class_path = default_class_path + os.pathsep + classpath_str
    default_class_path = classpath_str

def resolve_workspace_path(relative_path: str) -> str:
    if os.path.isabs(relative_path):
        return relative_path
    return os.path.join(client_workspace_path, relative_path)

def resolve_classpath(classpath: Optional[str]) -> str:
    """
    Resolve classpath entries relative to client workspace
    Handles multiple classpath entries separated by ':' or ';'
    """
    if not classpath:
        if default_class_path != '':
            return default_class_path
        return "."

    entries = classpath.split(os.pathsep)
    resolved_entries = []

    for entry in entries:
        resolved_entries.append(resolve_workspace_path(entry))
    resolved_classpath = os.pathsep.join(resolved_entries)
    if default_class_path != '':
        return resolved_classpath + os.pathsep + default_class_path
    return resolved_classpath

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
            name="java_compile",
            description="Compile Java source files",
            inputSchema={
                "type": "object",
                "properties": {
                    "java_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of Java source files or patterns (e.g. src/Hello.java, src/**/*.java)"
                    },
                    "classpath": {"type": "string",
                                  "description": "List of jar files or patterns (e.g. path/to/a.jar:path/to/lib/*)"},
                    "output_dir": {"type": "string", "description": "default values: main/bin"},
                },
                "required": ["java_files"]
            },
        ),
        types.Tool(
            name="junit_compile",
            description="Compile JUnit test files",
            inputSchema={
                "type": "object",
                "properties": {
                    "java_test_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of JUnit source files or patterns (e.g. src/HelloTest.java, src/**/*Test.java)"                    },
                    "classpath": {"type": "string",
                                  "description": "List of jar files or patterns (e.g. path/to/a.jar:path/to/lib/*)"},
                    "target_dir": {"type": "string", "description": "default values: main/bin"},
                    "output_dir": {"type": "string", "description": "default values: test/bin"},
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
                    "classpath": {"type": "string",
                                  "description": "List of jar files or patterns (e.g. path/to/a.jar:path/to/lib/*)"},
                    "target_dir": {"type": "string", "description": "default values: main/bin"},
                    "test_dir": {"type": "string", "description": "default values: test/bin"},
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
        if name == "java_compile":
            return await java_compile(arguments)
        elif name == "junit_compile":
            return await junit_compile(arguments)
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


async def compile_java_files(
    files: List[str],
    output_dir: str,
    classpath: str,
    additional_classpath: str = ""
) -> list[types.TextContent]:
    resolved_files = resolve_file_list(files)
    if not resolved_files:
        raise ValueError("No Java files found to compile")

    os.makedirs(output_dir, exist_ok=True)
    classpath_split = os.pathsep

    full_classpath = classpath
    if additional_classpath:
        full_classpath = f"{full_classpath}{classpath_split}{additional_classpath}"

    cmd = [
        "javac",
        "-d", output_dir,
        "-cp", full_classpath,
        *resolved_files
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        try:
            stderr_decoded = stderr.decode('utf-8')
        except UnicodeDecodeError:
            stderr_decoded = stderr.decode('utf-8', errors='replace')
        error_files = set()
        error_pattern = re.compile(r"(.*\.java):")  # tests/src/com/examples/HelloWorldTest.java:11: error: ...
        for line in stderr_decoded.splitlines():
            match = error_pattern.search(line)
            if match:
                error_files.add(match.group(1))

        error_files = set(error_files)
        resolved_files = set(resolved_files) - error_files
        if len(resolved_files) == 0:
            raise subprocess.CalledProcessError(
                process.returncode, cmd, stdout, stderr
            )

        cmd = [
            "javac",
            "-d", output_dir,
            "-cp", full_classpath,
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
        error_files_str = ", ".join(error_files)
        resolved_files_str = '.'.join(resolved_files)
        return [
            types.TextContent(
                type="text",
                text=f"Successfully compiled {resolved_files_str}. Compilation failed files: {error_files_str}"
            )
        ]
    return [
        types.TextContent(
            type="text",
            text=f"Successfully compiled {len(resolved_files)} files"
        )
    ]


async def java_compile(arguments: dict) -> list[types.TextContent]:
    java_files = arguments.get("java_files", [])
    output_dir = resolve_workspace_path(arguments.get("output_dir", "main/bin"))
    classpath = resolve_classpath(arguments.get("classpath"))

    return await compile_java_files(java_files, output_dir, classpath)


async def junit_compile(arguments: dict) -> list[types.TextContent]:
    test_files = arguments.get("java_test_files", [])
    target_dir = resolve_workspace_path(arguments.get("target_dir", "main/bin"))
    output_dir = resolve_workspace_path(arguments.get("output_dir", "test/bin"))
    classpath = resolve_classpath(arguments.get("classpath"))
    junit_classpath = f"{target_dir}:{workspace_path}/junit.jar"

    return await compile_java_files(test_files, output_dir, classpath, junit_classpath)

async def run_junit(arguments: dict) -> list[types.TextContent]:
    package_name = arguments.get("package_name", "")
    target_dir = resolve_workspace_path(arguments.get("target_dir", "main/bin"))
    test_dir = resolve_workspace_path(arguments.get("test_dir", "test/bin"))
    classpath = resolve_classpath(arguments.get("classpath", ""))
    test_classes = arguments.get("test_classes", [])

    junit_includes = f"{package_name}.*" if package_name else ".*"

    classpath_split = os.pathsep

    cmd = [
        "java",
        f"-javaagent:{workspace_path}/jacocoagent.jar=destfile={workspace_path}/jacoco.exec,includes={junit_includes}",
        "-cp",
        f"{target_dir}{classpath_split}{test_dir}{classpath_split}{workspace_path}/{classpath}{classpath_split}{workspace_path}/junit.jar",
        "org.junit.platform.console.ConsoleLauncher",
    ]

    if test_classes:
        for test_class in test_classes:
            cmd.extend(["--select-class", package_name + '.' + test_class])
    else:
        cmd.extend(["--scan-classpath", test_dir])
    
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
    classfiles = resolve_workspace_path(arguments.get("classfiles_root_path", "main/bin"))
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
