import shutil
import threading
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

USER_AGENT = "openqore-patcher/1.0"
DEFAULT_THREADS = 8
MIN_SIZE_FOR_SPLIT = 2 * 1024 * 1024  # don't bother splitting files < 2MiB


def find_on_host(binary_name: str):
    return shutil.which(binary_name)


def _head_info(url: str):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            length = resp.headers.get("Content-Length")
            accept_ranges = resp.headers.get("Accept-Ranges", "").lower() == "bytes"
            return (int(length) if length else None), accept_ranges
    except Exception:
        return None, False


def _download_range(url, start, end, fh, lock, progress, task_id):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Range": f"bytes={start}-{end}",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        pos = start
        while True:
            buf = resp.read(65536)
            if not buf:
                break
            with lock:
                fh.seek(pos)
                fh.write(buf)
            pos += len(buf)
            progress.add(len(buf))


class _Progress:
    def __init__(self, total, on_progress):
        self.total = total
        self.done = 0
        self.lock = threading.Lock()
        self.on_progress = on_progress

    def add(self, n):
        with self.lock:
            self.done += n
            if self.on_progress:
                pct = (self.done / self.total * 100) if self.total else 0.0
                self.on_progress(self.done, self.total, pct)


def download_file(url: str, dest_path, threads: int = DEFAULT_THREADS,
                   on_progress=None, log=print) -> str:
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    total, accept_ranges = _head_info(url)
    log(f"[download] {url}")
    log(f"[download] size={total or 'unknown'} bytes, "
        f"mode={'parallel x' + str(threads) if (accept_ranges and total and total >= MIN_SIZE_FOR_SPLIT) else 'single-stream'}")

    if not total or not accept_ranges or total < MIN_SIZE_FOR_SPLIT or threads <= 1:
        return _download_single(url, dest_path, total, on_progress, log)

    part_size = total // threads
    ranges = []
    for i in range(threads):
        start = i * part_size
        end = (start + part_size - 1) if i < threads - 1 else (total - 1)
        ranges.append((start, end))

    progress = _Progress(total, on_progress)
    lock = threading.Lock()

    with open(dest_path, "wb") as f:
        f.truncate(total)

    errors = []
    with open(dest_path, "r+b") as fh:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = [pool.submit(_download_range, url, s, e, fh, lock, progress, i)
                       for i, (s, e) in enumerate(ranges)]
            for fut in as_completed(futures):
                exc = fut.exception()
                if exc is not None:
                    errors.append(exc)

    if errors:
        log(f"[download] {len(errors)} chunk(s) failed ({errors[0]}), retrying single-threaded...")
        return _download_single(url, dest_path, total, on_progress, log)

    log(f"[download] done: {dest_path} ({total} bytes, {threads} threads)")
    return str(dest_path)


def _download_single(url, dest_path, total, on_progress, log):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    done = 0
    with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as out:
        total = total or (int(resp.headers.get("Content-Length", 0)) or None)
        while True:
            buf = resp.read(65536)
            if not buf:
                break
            out.write(buf)
            done += len(buf)
            if on_progress:
                pct = (done / total * 100) if total else 0.0
                on_progress(done, total or done, pct)
    log(f"[download] done: {dest_path} ({done} bytes, single-stream)")
    return str(dest_path)

GITHUB_API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"


def update_modules_from_github(repo: str, log=print):
    import json as _json
    from . import paths, archives
    import shutil as _shutil

    log(f"[update] fetching latest release info for {repo}...")
    req = urllib.request.Request(GITHUB_API_LATEST.format(repo=repo), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        release = _json.loads(resp.read().decode("utf-8"))

    assets = release.get("assets", [])
    archive_asset = next((a for a in assets if a["name"].endswith((".zip", ".tar.gz"))), None)
    if not archive_asset:
        raise RuntimeError("no archive asset found in the latest release.")

    dl_path = paths.cache_dir() / archive_asset["name"]
    download_file(archive_asset["browser_download_url"], dl_path, log=log)

    extract_dir = paths.cache_dir() / "update_extract"
    archives.extract_archive(dl_path, extract_dir)

    src_json = extract_dir / "modules_json"
    src_py = extract_dir / "modules_py"
    if src_json.exists():
        _shutil.copytree(src_json, paths.modules_json_dir(), dirs_exist_ok=True)
    if src_py.exists():
        _shutil.copytree(src_py, paths.modules_py_dir(), dirs_exist_ok=True)

    _shutil.rmtree(extract_dir, ignore_errors=True)
    log(f"[update] modules updated from release '{release.get('tag_name')}'.")