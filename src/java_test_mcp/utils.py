# author: Toshihiko Aoki
# licence: MIT

import os
import re
import shutil
import subprocess
import zipfile
import glob
from pathlib import Path
from typing import List, Tuple
import tempfile
import xml.etree.ElementTree as ET
import asyncio
import requests


def download(download_url, file_name):
    response = requests.get(download_url, stream=True)
    if response.status_code == 200:
        with open(file_name, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024):
                file.write(chunk)
    else:
        raise Exception(f"Failed to download file: {response.status_code}")


def extract_files(file_name, extract_to, ext='.jar'):
    with zipfile.ZipFile(file_name, "r") as zip_ref:
        for file in zip_ref.namelist():
            if file.endswith(ext):
                source = zip_ref.open(file)
                target_path = os.path.join(extract_to, os.path.basename(file))

                with open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)


def classspath_from_pom(pom_path, output_file='cp.txt'):
    try:
        pom_path = Path(pom_path).resolve()
        if not pom_path.exists():
            raise ValueError('Not found pom.xml path: ' + pom_path)

        output_path = Path(output_file).resolve()

        cmd = f'mvn -f "{pom_path}" dependency:build-classpath "-Dmdep.outputFile={output_path}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            raise ValueError('mvn command failed. pom.xml path: ' + pom_path)

        if not output_path.exists():
            raise ValueError('file read failed. path: ' + output_path)

        with open(output_path, 'r', encoding='utf-8') as f:
            classpath_string = f.read().strip()
            return classpath_string

    except Exception as e:
        raise ValueError('classpath reference failed. pom.xml path: ' + pom_path)


def resolve_workspace_path(relative_path: str, workspace_path='.') -> str:
    if os.path.isabs(relative_path):
        return relative_path
    return os.path.join(workspace_path, relative_path)


def resolve_classpath(classpath='', workspace_path='.') -> str:
    """
    Resolve classpath entries relative to client workspace
    Handles multiple classpath entries separated by ':' or ';'
    """
    if not classpath:
        return "."

    entries = classpath.split(os.pathsep)
    resolved_entries = []

    for entry in entries:
        resolved_entries.append(resolve_workspace_path(
            relative_path=entry, workspace_path=workspace_path))
    resolved_classpath = os.pathsep.join(resolved_entries)
    return resolved_classpath


def resolve_file_list(files: List[str], workspace_path='.') -> List[str]:
    """
    Resolve a list of files, handling both individual files and wildcards
    """
    resolved_files = []
    for file_path in files:
        if '*' in file_path:
            base_dir = os.path.dirname(file_path)
            base_dir = resolve_workspace_path(base_dir, workspace_path=workspace_path)
            pattern = os.path.join(base_dir, os.path.basename(file_path))
            if '**' in pattern:
                matched_files = glob.glob(pattern, recursive=True)
            else:
                matched_files = glob.glob(pattern)
            resolved_files.extend(matched_files)
        else:
            resolved_files.append(resolve_workspace_path(file_path,
                                                         workspace_path=workspace_path))
    return resolved_files


async def run_command_stderr_from_file(cmd: List[str]) -> Tuple[int, bytes, str]:
    with tempfile.NamedTemporaryFile(mode='w+', delete=True, suffix='.stderr_log') as std_err_file:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=std_err_file
        )

        stdout, _ = await process.communicate()
        stderr_decoded = ""
        if process.returncode != 0:
            std_err_file.seek(0)
            stderr_decoded = std_err_file.read()

    return process.returncode, stdout, stderr_decoded


async def compile_java_files(
    source_files: List[str],
    output_dir: str,
    classpath: str
) -> dict:
    if not source_files:
        raise ValueError("No Java files found to compile")
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        "javac",
        "-d", output_dir,
        "-cp", classpath,
        *source_files
    ]

    returncode, stdout, stderr_decoded = await run_command_stderr_from_file(cmd)

    if stderr_decoded != "":
        error_files = set()
        error_pattern = re.compile(r"(.*\.java):")  # tests/src/com/examples/HelloWorldTest.java:11: error: ...
        for line in stderr_decoded.splitlines():
            match = error_pattern.search(line)
            if match:
                error_files.add(match.group(1))

        error_files = set(error_files)
        source_files = set(source_files) - error_files
        if len(source_files) == 0:
            raise subprocess.CalledProcessError(
                returncode, cmd, stdout, stderr_decoded
            )

        cmd = [
            "javac",
            "-d", output_dir,
            "-cp", classpath,
            *source_files
        ]

        returncode, stdout, stderr_decoded = await run_command_stderr_from_file(cmd)
        if returncode != 0:
            raise subprocess.CalledProcessError(
                returncode, cmd, stdout, stderr_decoded
            )
        return {
            "status": "partial_success",
            "result": {
                "compiled_files": source_files,
                "failed_files": error_files,
                "stderr": stderr_decoded
            },
            "cmd": ' '.join(cmd)
        }
    return {
        "status": "success",
        "result": {
            "compiled_files": source_files,
        },
        "cmd": ' '.join(cmd)
    }


async def java_compile(
    source_files: List[str] = [],
    output_dir: str = 'main/bin',
    classpath: str = '',
    workspace_path='.',
    additional_classpath='',
    **kwargs,
) -> dict:
    resolved_file = resolve_file_list(source_files, workspace_path=workspace_path)
    classpath = resolve_classpath(classpath, workspace_path=workspace_path)
    output_dir = resolve_workspace_path(output_dir, workspace_path=workspace_path)
    classpath_split = os.pathsep
    if additional_classpath:
        classpath = f"{classpath}{classpath_split}{additional_classpath}"
    return await compile_java_files(resolved_file, output_dir, classpath)


async def junit_compile(
    source_files: List[str] = [],
    target_dir: str = 'main/bin',
    test_dir: str = 'test/bin',
    classpath: str = '',
    workspace_path='.',
    additional_classpath='',
    build_path='./junit_jacoco_jar_path',
    junit_jar='junit.jar',
    **kwargs,
) -> dict:

    resolved_file = resolve_file_list(source_files, workspace_path=workspace_path)
    classpath = resolve_classpath(classpath, workspace_path=workspace_path)
    target_dir = resolve_workspace_path(target_dir, workspace_path=workspace_path)
    output_dir = resolve_workspace_path(test_dir, workspace_path=workspace_path)
    jar_path = os.path.join(build_path, junit_jar)
    junit_classpath = f"{target_dir}{os.pathsep}{jar_path}"
    if additional_classpath:
        junit_classpath = f"{junit_classpath}{os.pathsep}{additional_classpath}"
    classpath = f"{classpath}{os.pathsep}{junit_classpath}"
    return await compile_java_files(resolved_file, output_dir, classpath)


def junit_result_summary(stdout_str: str) -> dict:
    result = {}

    summary_pattern = r"\[\s*(\d+)\s+([\w\s]+)\s*\]"
    for line in stdout_str.splitlines():
        match = re.match(summary_pattern, line)
        if match:
            value, key = match.groups()
            result[key.strip()] = int(value)

    return result


async def run_junit(
    package_name: str = '',
    target_dir: str = 'main/bin',
    test_dir: str = 'test/bin',
    test_classes: List[str] = [],
    classpath='',
    workspace_path='.',
    build_path='./junit_jacoco_jar_path',
    additional_classpath='',
    junit_jar='junit.jar',
    jacoco_agent_jar='jacocoagent.jar',
    jacoco_exec='jacoco.exec',
    **kwargs,
) -> dict:

    target_dir = resolve_workspace_path(target_dir, workspace_path=workspace_path)
    test_dir = resolve_workspace_path(test_dir, workspace_path=workspace_path)
    classpath = resolve_classpath(classpath, workspace_path=workspace_path)

    classpath_split = os.pathsep
    if additional_classpath:
        classpath = f"{classpath}{classpath_split}{additional_classpath}"
    junit_includes = f"{package_name}.*" if package_name else ".*"

    jar_path = os.path.join(build_path, junit_jar)
    all_classpath = f"{classpath}{classpath_split}{target_dir}{classpath_split}{test_dir}{classpath_split}{jar_path}"

    javaagent_path = os.path.join(build_path, jacoco_agent_jar)
    destfile_path = os.path.join(build_path, jacoco_exec)

    cmd = [
        "java",
        f"-javaagent:{javaagent_path}=destfile={destfile_path},includes={junit_includes}",
        "-cp",
        all_classpath,
        "org.junit.platform.console.ConsoleLauncher"
    ]

    if test_classes:
        for test_class in test_classes:
            if package_name and not test_class.startswith(package_name):
                cmd.extend(["--select-class", package_name + '.' + test_class])
            else:
                cmd.extend(["--select-class", test_class])

    else:
        cmd.extend(["--scan-classpath", test_dir])

    returncode, stdout, stderr_decoded = await run_command_stderr_from_file(cmd)

    if returncode != 0:
        raise subprocess.CalledProcessError(
            returncode, cmd, stdout, stderr_decoded
        )

    return {
        "cmd": ' '.join(cmd),
        "result" : {
            "summary": junit_result_summary(stdout.decode())
        }
    }


async def report_coverage(
    classfiles_dir: str = 'main/bin',
    package_name: str = '',
    workspace_path='.',
    build_path='./junit_jacoco_jar_path',
    jacococli_jar='jacococli.jar',
    jacoco_exec='jacoco.exec',
    jacoco_report_dir="jacoco-report",
    jacoco_report_file="jacoco.xml",
    ** kwargs,
) -> dict:

    classfiles = resolve_workspace_path(classfiles_dir, workspace_path=workspace_path)
    jacoco_classfiles = f"{classfiles}/{package_name.replace('.', '/')}" if package_name else classfiles

    report_path = os.path.join(workspace_path, jacoco_report_dir)
    os.makedirs(report_path, exist_ok=True)
    jacoco_xml_path = os.path.join(report_path, jacoco_report_file)
    jacococli_path = os.path.join(build_path, jacococli_jar)
    jacoco_exec_path = os.path.join(build_path, jacoco_exec)
    cmd = [
        "java",
        "-jar",
        jacococli_path,
        "report",
        jacoco_exec_path,
        "--classfiles",
        jacoco_classfiles,
        "--sourcefiles",
        ".",
        "--xml",
        jacoco_xml_path
    ]

    returncode, stdout, stderr_decoded = await run_command_stderr_from_file(cmd)

    if returncode != 0:
        raise subprocess.CalledProcessError(
            returncode, cmd, stdout, stderr_decoded
        )
    coverage_data = parse_coverage_report(jacoco_xml_path)
    return {
        "cmd": ' '.join(cmd),
        "result": coverage_data
    }


def parse_coverage_report(jacoco_xml_path) -> dict:
    """
    Parse Jacoco coverage report XML and extract coverage data
    """
    coverage_data = {}
    tree = ET.parse(jacoco_xml_path)
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
