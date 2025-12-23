# Copied directly from original downloader.py with no naming changes

import os
import requests

def download_image(url: str, output_path: str):
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(8192):
            f.write(chunk)
