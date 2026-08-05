#!/usr/bin/env python3
"""Supplement backup with UI bundle and docker-compose for migration."""
from __future__ import annotations

import os
import sys
import time

import paramiko

HOST = "192.168.100.73"
LOCAL_DIR = r"D:\mlnocodb-backup\mlnocodb-100.73-20260730-113755"
REMOTE_TAR = "/tmp/mlnocodb-ui-supplement.tar.gz"


def run(client, cmd, timeout=3600):
    print(f"$ {cmd}")
    _, o, e = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    code = o.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if code:
        print(err, file=sys.stderr)
    return code, out, err


def main():
    pwd = os.environ.get("REMOTE_SSH_PASSWORD", "")
    if not pwd:
        print("REMOTE_SSH_PASSWORD required", file=sys.stderr)
        return 2

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username="root", password=pwd, timeout=30)
    try:
        run(client, f"tar -czf {REMOTE_TAR} -C /opt/mlnocodb ui", timeout=7200)
        run(client, f"ls -lh {REMOTE_TAR}")

        sftp = client.open_sftp()
        local = os.path.join(LOCAL_DIR, "opt-mlnocodb-ui.tar.gz")
        size = sftp.stat(REMOTE_TAR).st_size
        print(f"Downloading ui ({size/(1024**2):.1f} MiB)...")
        sftp.get(REMOTE_TAR, local)
        sftp.close()
        run(client, f"rm -f {REMOTE_TAR}")
    finally:
        client.close()

    compose = """# mlnocodb migration compose (from 192.168.100.73 backup)
# Adjust NC_DB / NC_PUBLIC_URL / NUXT_PUBLIC_NC_BACKEND_URL for target host.

services:
  api:
    image: mlnocodb:0.1.1
    container_name: mlnocodb-api
    restart: always
    ports:
      - "6080:8080"
    environment:
      NC_DB: "pg://192.168.100.93:5432?u=postgres&p=Pass%40w0rd&d=mlnoco"
      NC_DISABLE_TELE: "true"
      NC_PUBLIC_URL: "http://192.168.100.73:6080"
      TZ: Asia/Shanghai
    volumes:
      - ./data:/usr/app/data

  ui:
    image: node:22-slim
    container_name: mlnocodb-ui
    restart: always
    working_dir: /app
    command: ["node", "server/index.mjs"]
    ports:
      - "80:6100"
    environment:
      PORT: "6100"
      NUXT_PUBLIC_NC_BACKEND_URL: "http://192.168.100.73:6080"
      NUXT_PAGE_TRANSITION_DISABLE: "true"
      TZ: Asia/Shanghai
      NITRO_HOST: "0.0.0.0"
      NITRO_PORT: "6100"
    volumes:
      - ./ui:/app:ro
"""
    compose_path = os.path.join(LOCAL_DIR, "docker-compose.yml")
    with open(compose_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(compose)

    restore = """# 迁移恢复步骤 (CentOS / 任意 Docker 主机)

## 1. 上传备份目录到目标服务器
scp -r mlnocodb-100.73-* root@<目标IP>:/opt/

## 2. 加载镜像
cd /opt/mlnocodb-100.73-*
docker load -i image-1-mlnocodb_0.1.1.tar
docker load -i image-2-node_22-slim.tar

## 3. 解压 UI 静态资源
mkdir -p ui data
tar -xzf opt-mlnocodb-ui.tar.gz -C .
# 得到 ./ui/ (nitro 构建产物)

## 4. 修改 docker-compose.yml
# - NC_DB: Meta 数据库连接 (当前生产指向 192.168.100.93:5432/mlnoco)
# - NC_PUBLIC_URL / NUXT_PUBLIC_NC_BACKEND_URL: 改为目标服务器 IP/域名

## 5. 启动
docker compose up -d

## 端口
# API: 6080
# UI:  80 -> 容器 6100

## 说明
# - data 卷在生产环境为空，业务数据在 PostgreSQL Meta (100.93)，迁移时需保证 Meta 可达
# - UI 使用 node:22-slim + 挂载 ui 目录，非独立 UI 镜像
"""
    with open(os.path.join(LOCAL_DIR, "RESTORE.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(restore)

    print("\nSupplement complete:")
    for fn in sorted(os.listdir(LOCAL_DIR)):
        fp = os.path.join(LOCAL_DIR, fn)
        print(f"  {fn}\t{os.path.getsize(fp)/(1024**2):.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
