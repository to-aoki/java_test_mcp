import requests
import zipfile
import os
import shutil
import subprocess
from pathlib import Path

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
