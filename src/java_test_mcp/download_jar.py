import requests
import zipfile
import os
import shutil


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
