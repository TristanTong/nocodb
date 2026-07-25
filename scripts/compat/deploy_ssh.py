#!/usr/bin/env python3
"""SSH/SCP helper for mlnocodb CentOS deploy. Credentials via env only."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import paramiko

HOST = os.environ.get("DEPLOY_HOST", "192.168.100.73")
USER = os.environ.get("DEPLOY_USER", "root")
PASSWORD = os.environ["DEPLOY_PASSWORD"]  # required
PORT = int(os.environ.get("DEPLOY_SSH_PORT", "22"))


def connect() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=30)
    return c


def run(cmd: str, timeout: int = 600, check: bool = True) -> tuple[int, str, str]:
    c = connect()
    try:
        print(f"$ {cmd}", flush=True)
        stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        if out:
            print(out, end="" if out.endswith("\n") else "\n", flush=True)
        if err:
            print(err, end="" if err.endswith("\n") else "\n", flush=True)
        if check and code != 0:
            raise SystemExit(f"remote command failed ({code}): {cmd}")
        return code, out, err
    finally:
        c.close()


def upload(local: str, remote: str) -> None:
    local_p = Path(local)
    if not local_p.exists():
        raise SystemExit(f"missing local file: {local}")
    c = connect()
    try:
        sftp = c.open_sftp()
        # ensure remote dir
        remote_dir = os.path.dirname(remote)
        run(f"mkdir -p {remote_dir}", check=False)
        c2 = connect()
        try:
            sftp2 = c2.open_sftp()
            print(f"UPLOAD {local} -> {remote}", flush=True)
            sftp2.put(str(local_p), remote)
            sftp2.close()
        finally:
            c2.close()
        sftp.close()
    finally:
        c.close()


def upload_dir(local_dir: str, remote_dir: str) -> None:
    """Upload directory recursively via tar stream over SSH exec."""
    import tarfile
    import io
    import tempfile

    local_p = Path(local_dir)
    if not local_p.is_dir():
        raise SystemExit(f"missing local dir: {local_dir}")

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        print(f"TAR {local_dir} -> {tmp_path}", flush=True)
        with tarfile.open(tmp_path, "w:gz") as tar:
            tar.add(str(local_p), arcname=local_p.name)
        remote_tar = f"/tmp/{Path(tmp_path).name}"
        upload(tmp_path, remote_tar)
        run(f"mkdir -p {remote_dir} && tar -xzf {remote_tar} -C {remote_dir} && rm -f {remote_tar}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: deploy_ssh.py run <cmd> | upload <local> <remote> | upload-dir <local> <remote>")
        raise SystemExit(2)
    action = sys.argv[1]
    if action == "run":
        run(" ".join(sys.argv[2:]))
    elif action == "upload":
        upload(sys.argv[2], sys.argv[3])
    elif action == "upload-dir":
        upload_dir(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(f"unknown action {action}")
