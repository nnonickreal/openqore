import os
import tarfile
import zipfile
from pathlib import Path


def extract_archive(archive_path, dest_dir):
    archive_path = Path(archive_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = archive_path.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as z:
            z.extractall(dest_dir)
    elif name.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar")):
        with tarfile.open(archive_path) as t:
            t.extractall(dest_dir)
    else:
        raise ValueError(f"unsupported archive format: {archive_path.name}")
    return dest_dir


def find_file_in_dir(root_dir, filename):
    for root, _dirs, files in os.walk(root_dir):
        if filename in files:
            return Path(root) / filename
    return None