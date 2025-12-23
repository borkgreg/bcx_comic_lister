# Copied directly from original utils.py with no naming changes

import os

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)
