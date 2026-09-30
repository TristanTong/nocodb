#!/usr/bin/env python3
"""Package mlnocodb release as a version-tagged Docker image tarball.

Default target: v0.1.6 → image mlnocodb:0.1.6 → mlnocodb-0.1.6.tar.gz

Prereq (build machine, not CentOS 7):
  git checkout v0.1.6
  pnpm bootstrap   # if needed
  cd packages/nocodb && pnpm run docker:build

Usage:
  python scripts/compat/package_release_0.1.6.py
  python scripts/compat/package_release_0.1.6.py --tag 0.1.6 --skip-build
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOCO = ROOT / "packages" / "nocodb"
MAIN_JS = NOCO / "docker" / "main.js"
DOCKERFILE = NOCO / "Dockerfile.centos"
OUT_DIR = ROOT / "dist" / "release"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(cwd or ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="0.1.6", help="image/tag version without 'v' prefix")
    ap.add_argument("--skip-build", action="store_true", help="skip pnpm docker:build")
    ap.add_argument("--skip-image", action="store_true", help="only verify main.js")
    args = ap.parse_args()

    image = f"mlnocodb:{args.tag}"
    tarball = OUT_DIR / f"mlnocodb-{args.tag}.tar.gz"

    if not args.skip_build:
        run(["pnpm", "run", "docker:build"], cwd=NOCO)

    if not MAIN_JS.is_file():
        print(f"MISSING {MAIN_JS}", file=sys.stderr)
        return 2

    text = MAIN_JS.read_text(encoding="utf-8", errors="replace")
    checks = {
        "MssqlClient": "MssqlClient" in text,
        "applyMissingPkFallback_or_code": (
            "applyMissingPkFallback" in text or "code$/i" in text or "External U8" in text
        ),
        "Primary key is required": "Primary key is required to delete records" in text,
        "EREQUEST": "EREQUEST" in text,
    }
    for k, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] main.js {k}")
    if not all(checks.values()):
        return 3

    print(f"main.js size={MAIN_JS.stat().st_size}")

    if args.skip_image:
        print("skip-image: done")
        return 0

    if not DOCKERFILE.is_file():
        print(f"MISSING {DOCKERFILE}", file=sys.stderr)
        return 2

    run(
        [
            "docker",
            "build",
            "-t",
            image,
            "-f",
            str(DOCKERFILE),
            str(NOCO),
        ]
    )
    run(
        [
            "docker",
            "run",
            "--rm",
            image,
            "node",
            "-e",
            "require('mssql'); console.log('mssql_ok');"
            "const fs=require('fs');"
            "const t=fs.readFileSync('docker/main.js','utf8');"
            "console.log('MssqlClient', (t.match(/MssqlClient/g)||[]).length);",
        ]
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"writing {tarball}", flush=True)
    # Portable: docker save → Python gzip (Windows often lacks gzip.exe)
    import gzip as gz

    p1 = subprocess.Popen(["docker", "save", image], stdout=subprocess.PIPE)
    assert p1.stdout is not None
    with gz.open(tarball, "wb") as f:
        while True:
            chunk = p1.stdout.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    rc1 = p1.wait()
    if rc1:
        print("docker save failed", rc1, file=sys.stderr)
        return 4

    print(f"OK image={image} tarball={tarball} bytes={tarball.stat().st_size}")
    print("Next on 100.93:")
    print(f"  scp {tarball.name} root@192.168.100.93:/opt/mlnocodb/")
    print(f"  gunzip -c {tarball.name} | docker load")
    print(f"  # edit compose: image: {image}")
    print("  # backup Meta 97, then: docker compose up -d --force-recreate api")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
