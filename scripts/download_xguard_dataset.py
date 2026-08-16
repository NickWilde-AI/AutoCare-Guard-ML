from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path


DEFAULT_URL = "https://huggingface.co/datasets/Alibaba-AAIG/XGuard-Train-Open-200K/resolve/main/xguard_train_open_200k.jsonl"


def download(url: str, out: Path, *, force: bool = False) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 0 and not force:
        print(f"exists: {out}")
        return
    tmp = out.with_suffix(out.suffix + ".tmp")
    print(f"downloading: {url}")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(out)
    print(f"saved: {out}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download XGuard-Train-Open-200K into the local ignored data directory.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default="data/external/xguard_train_open_200k.jsonl")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    download(args.url, Path(args.out), force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
