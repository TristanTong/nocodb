#!/usr/bin/env python3
"""Export NocoDB Docker deployment from remote CentOS host via SSH/SFTP."""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time

import paramiko


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 3600) -> tuple[int, str, str]:
    print(f"$ {cmd[:200]}{'...' if len(cmd) > 200 else ''}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip() and code != 0:
        print(err.rstrip(), file=sys.stderr)
    return code, out, err


def sftp_get(sftp: paramiko.SFTPClient, remote: str, local: str) -> None:
    os.makedirs(os.path.dirname(local), exist_ok=True)
    size = sftp.stat(remote).st_size
    print(f"Downloading {remote} ({size / (1024**3):.2f} GiB) -> {local}")
    sftp.get(remote, local, callback=_progress(size))


def _progress(total: int):
    last = {"t": time.time(), "n": 0}

    def cb(done: int, _total: int) -> None:
        now = time.time()
        if now - last["t"] >= 5 or done == total:
            pct = 100.0 * done / total if total else 0
            print(f"  ... {done / (1024**2):.0f} MiB / {total / (1024**2):.0f} MiB ({pct:.1f}%)")
            last["t"] = now

    return cb


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="192.168.100.73")
    p.add_argument("--user", default="root")
    p.add_argument("--password", default=os.environ.get("REMOTE_SSH_PASSWORD", ""))
    p.add_argument("--local-dir", default=r"D:\mlnocodb-backup")
    args = p.parse_args()

    if not args.password:
        print("Set REMOTE_SSH_PASSWORD or --password", file=sys.stderr)
        return 2

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    remote_dir = f"/tmp/mlnocodb-backup-{stamp}"
    local_dir = os.path.join(args.local_dir, f"mlnocodb-100.73-{stamp}")
    os.makedirs(local_dir, exist_ok=True)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting {args.user}@{args.host} ...")
    client.connect(args.host, username=args.user, password=args.password, timeout=30)

    try:
        run(client, "docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'")
        run(client, "docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}'")

        code, out, _ = run(
            client,
            "docker ps --format '{{.Names}}|{{.Image}}' | grep -E 'mlnocodb|nocodb' || true",
        )
        lines = [ln.strip() for ln in out.splitlines() if "|" in ln]
        images: set[str] = set()
        for ln in lines:
            _, img = ln.split("|", 1)
            images.add(img.strip())

        if not images:
            _, out2, _ = run(client, "docker ps --format '{{.Image}}'")
            images = {x.strip() for x in out2.splitlines() if x.strip()}

        if not images:
            print("No running docker images found", file=sys.stderr)
            return 1

        print("Images to export:", ", ".join(sorted(images)))
        run(client, f"mkdir -p {remote_dir}")

        manifest_lines = [
            f"# mlnocodb backup from {args.host}",
            f"# created {stamp}",
            "",
            "## docker ps",
        ]
        _, ps_out, _ = run(client, "docker ps -a")
        manifest_lines.append(ps_out.strip())
        manifest_lines.append("\n## docker images")
        _, img_out, _ = run(client, "docker images")
        manifest_lines.append(img_out.strip())

        for i, img in enumerate(sorted(images)):
            safe = img.replace("/", "_").replace(":", "_")
            remote_tar = f"{remote_dir}/image-{i+1}-{safe}.tar"
            code, _, err = run(client, f"docker save -o {remote_tar} {img}", timeout=7200)
            if code != 0:
                print(f"Failed to save {img}: {err}", file=sys.stderr)
                return 1

        # Optional migration assets
        for path, name in [
            ("/opt/mlnocodb/docker-compose.yml", "docker-compose.yml"),
            ("/opt/mlnocodb/data", "data-volume"),
            ("/opt/mlnocodb/ui-output", "ui-output"),
        ]:
            _, check_out, _ = run(client, f"test -e {path} && echo yes || echo no")
            if "yes" in check_out:
                if name == "data-volume":
                    run(
                        client,
                        f"tar -czf {remote_dir}/opt-mlnocodb-data.tar.gz -C /opt/mlnocodb data",
                        timeout=7200,
                    )
                elif name == "ui-output":
                    run(
                        client,
                        f"tar -czf {remote_dir}/opt-mlnocodb-ui-output.tar.gz -C /opt/mlnocodb ui-output",
                        timeout=7200,
                    )
                else:
                    run(client, f"cp {path} {remote_dir}/{name}")

        run(client, f"ls -lh {remote_dir}")

        sftp = client.open_sftp()
        try:
            for fname in sftp.listdir(remote_dir):
                sftp_get(sftp, f"{remote_dir}/{fname}", os.path.join(local_dir, fname))
        finally:
            sftp.close()

        manifest_path = os.path.join(local_dir, "README-backup.txt")
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write("\n".join(manifest_lines))
            f.write("\n\n## Restore\n")
            f.write("docker load -i image-*.tar\n")
            f.write("# then deploy with docker-compose.yml and extracted ui-output/data\n")

        run(client, f"rm -rf {remote_dir}")
        print(f"\nBackup complete: {local_dir}")
        for fn in sorted(os.listdir(local_dir)):
            fp = os.path.join(local_dir, fn)
            print(f"  {fn}\t{os.path.getsize(fp)/(1024**2):.1f} MiB")
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
