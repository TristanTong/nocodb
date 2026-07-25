# CentOS 7.6 内网快速部署

| 项 | 内容 |
|----|------|
| 适用系统 | CentOS 7.6（内网服务器） |
| 推荐方式 | **Docker 单容器**（含后端 + `/dashboard` UI） |
| 源码基线 | mlnocodb `0.301.2` / tag `v0.1.1` |
| 不推荐 | 在 CentOS 7 上直接安装 Node.js 22（glibc 过旧，易失败） |

---

## 1. 为什么用 Docker

| 方式 | 结论 |
|------|------|
| 本机装 Node 22 + pnpm | CentOS 7.6 通常 **不可行**（glibc 2.17，Node 22 需要更新） |
| Docker 跑应用 | **推荐**：镜像内自带 Node 22，与宿主内核分离 |
| 官方 `nocodb/nocodb:latest` | 可用，但 **不含** 本仓库 Vastbase FK 等补丁 |
| 本仓库自建镜像 | **内网推荐**：带上 `PgClient` 等本地修复 |

访问入口（单容器默认）：

| 用途 | URL |
|------|-----|
| UI | `http://<服务器IP>:6080/dashboard` |
| 健康检查 | `http://<服务器IP>:6080/api/v1/health` |
| 版本 | `http://<服务器IP>:6080/api/v1/version` |

> 说明：内网快速上线优先用容器内置 UI（`/dashboard`）。独立 `6100` 前端生产包可后续再加，不是第一天必做项。

---

## 2. 部署前准备

### 2.1 服务器与网络

- CentOS 7.6，能访问：
  - Meta PostgreSQL（例如 `192.168.100.89:5432`，库 `mlnoco`）
  - 业务库（如海量 Vastbase `192.168.100.99:5432`）
- 开放入站端口：`6080/tcp`（或你们改成的映射端口）
- 磁盘：建议 ≥ 20GB 可用；附件目录单独挂卷

### 2.2 在一台「构建机」上准备镜像（不要用 CentOS 7 编译）

构建机可用：Windows（已装 Docker Desktop）/ Rocky 8+ / Ubuntu 20.04+。

```bash
# 获取本仓库（示例：已打 tag v0.1.1）
git clone <你们的仓库地址> mlnocodb
cd mlnocodb
git checkout v0.1.1

# 安装 Node ≥22、pnpm 9，完成依赖与后端产物
pnpm bootstrap
# 按仓库脚本构建 nocodb 生产包（生成 packages/nocodb/docker/main 等）
cd packages/nocodb
pnpm run build   # 或项目惯用的 docker:build / start:prod 前置构建命令
```

若构建命令因环境差异失败，也可在能跑通本地 Backend 的机器上确认 `packages/nocodb/docker/main.js`（或 `docker/main`）已生成后再 `docker build`。

```bash
# 在 packages/nocodb 目录构建镜像
docker build -t mlnocodb:0.1.1 -f Dockerfile .

# 导出给内网（无私有仓库时）
docker save mlnocodb:0.1.1 | gzip > mlnocodb-0.1.1.tar.gz
```

把 `mlnocodb-0.1.1.tar.gz` 拷到 CentOS 服务器（scp/U 盘/内网文件站均可）。

---

## 3. CentOS 7.6 安装 Docker（一次性）

CentOS 7 已 EOL，请使用 vault 源；以下为常用路径，按内网策略微调。

```bash
sudo yum install -y yum-utils device-mapper-persistent-data lvm2
# 若官方源不可用，改用公司内部 Docker yum 源或离线 rpm
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install -y docker-ce docker-ce-cli containerd.io
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER   # 重新登录后生效
```

加载镜像：

```bash
gunzip -c mlnocodb-0.1.1.tar.gz | docker load
docker images | grep mlnocodb
```

---

## 4. 一键启动（对接已有 Meta PG）

在服务器上建目录：

```bash
sudo mkdir -p /opt/mlnocodb/data
cd /opt/mlnocodb
```

创建 `docker-compose.yml`（Docker Compose v1/v2 均可；无 Compose 时用下面的 `docker run`）：

```yaml
version: "2.4"
services:
  mlnocodb:
    image: mlnocodb:0.1.1
    container_name: mlnocodb
    restart: always
    ports:
      - "6080:8080"
    environment:
      NC_DB: "pg://192.168.100.89:5432?u=postgres&p=Pass%40w0rd&d=mlnoco"
      NC_DISABLE_TELE: "true"
      NC_PUBLIC_URL: "http://<服务器IP>:6080"
      # 建议生产必设，多机/重启后登录会话一致：
      # NC_AUTH_JWT_SECRET: "<长随机串>"
      TZ: "Asia/Shanghai"
    volumes:
      - /opt/mlnocodb/data:/usr/app/data
```

> 密码中的 `@` 必须 URL 编码为 `%40`。按实际 Meta 地址/账号修改；**不要把含真实密码的文件提交进 Git**。

启动：

```bash
# Compose
docker-compose up -d
# 或 Docker Compose V2
docker compose up -d

# 无 Compose 时：
docker run -d --name mlnocodb --restart always \
  -p 6080:8080 \
  -e NC_DB='pg://192.168.100.89:5432?u=postgres&p=Pass%40w0rd&d=mlnoco' \
  -e NC_DISABLE_TELE=true \
  -e NC_PUBLIC_URL='http://<服务器IP>:6080' \
  -e TZ=Asia/Shanghai \
  -v /opt/mlnocodb/data:/usr/app/data \
  mlnocodb:0.1.1
```

验收：

```bash
curl -s http://127.0.0.1:6080/api/v1/health
curl -s http://127.0.0.1:6080/api/v1/version
# 浏览器打开：http://<服务器IP>:6080/dashboard
```

防火墙（若开启 firewalld）：

```bash
sudo firewall-cmd --permanent --add-port=6080/tcp
sudo firewall-cmd --reload
```

---

## 5. 内网最快路径（总结）

```text
构建机：checkout v0.1.1 → 构建后端产物 → docker build → docker save
    ↓ 拷贝 tar.gz
CentOS7：docker load → docker run / compose（NC_DB 指已有 PG）
    ↓
浏览器：http://服务器:6080/dashboard
```

预计耗时：镜像已就绪时，服务器侧通常 **10～30 分钟**（含装 Docker）；含首次构建镜像则视机器性能 **1～数小时**。

---

## 6. 可选增强

### 6.1 Nginx 反代（统一 80 端口）

```nginx
server {
  listen 80;
  server_name nocodb.internal.example;

  client_max_body_size 100m;

  location / {
    proxy_pass http://127.0.0.1:6080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

同时把 `NC_PUBLIC_URL` 改成对外访问根地址（如 `http://nocodb.internal.example`）。

### 6.2 发布最新 6100 UI（可以，且推荐与本地一致）

**可以发布。** 本地 `http://localhost:6100/` 用的就是 `nc-gui` 生产构建（`.output`），内网同样可以挂到服务器 **6100**。

`6080/dashboard` 是后端自带的 **nc-lib-gui 静态包**，往往比你们当前源码 UI **旧一截**；要「和本地 6100 一样新」，请单独发布前端。

#### 方式 A：独立 6100 服务（推荐，与本地一致）

在**构建机**（非 CentOS 7）：

```bash
cd mlnocodb
git checkout v0.1.1   # 或当前发布分支

# 后端 API 地址写成「浏览器能打开的内网地址」（不要填 localhost）
export NUXT_PUBLIC_NC_BACKEND_URL=http://<服务器IP>:6080
export NUXT_PAGE_TRANSITION_DISABLE=true
pnpm --filter=nc-gui run build
```

产物目录：`packages/nc-gui/.output/`。打包并拷到服务器：

```bash
tar -czf nc-gui-output.tar.gz -C packages/nc-gui .output
# 服务器上：
sudo mkdir -p /opt/mlnocodb
tar -xzf nc-gui-output.tar.gz -C /opt/mlnocodb
sudo rm -rf /opt/mlnocodb/ui-output
sudo mv /opt/mlnocodb/.output /opt/mlnocodb/ui-output
```

使用仓库模板（API + UI）：`docker-compose/centos-internal/docker-compose.yml`  
改好 `NC_DB`、`NUXT_PUBLIC_NC_BACKEND_URL`、`NC_PUBLIC_URL` 后：

```bash
cd /opt/mlnocodb
docker compose up -d
```

或仅启动 UI（API 已在跑）：

```bash
docker run -d --name mlnocodb-ui --restart always \
  -p 6100:6100 \
  -e NITRO_HOST=0.0.0.0 -e NITRO_PORT=6100 -e PORT=6100 \
  -e NUXT_PUBLIC_NC_BACKEND_URL=http://<服务器IP>:6080 \
  -e NUXT_PAGE_TRANSITION_DISABLE=true \
  -v /opt/mlnocodb/ui-output:/app:ro \
  -w /app \
  node:22-slim \
  node server/index.mjs
```

验收与防火墙：

```bash
curl -sI http://127.0.0.1:6100/ | head -5
# 浏览器打开：http://<服务器IP>:6100/
sudo firewall-cmd --permanent --add-port=6100/tcp && sudo firewall-cmd --reload
```

| 入口 | 内容 |
|------|------|
| `http://IP:6100/` | **最新 UI**（与本地 6100 同源构建） |
| `http://IP:6080/dashboard` | 后端内置 GUI（可能较旧，可作备用） |

#### 方式 B：打进 `/dashboard`（单端口，可选）

把前端打进 `nc-lib-gui` 再重建后端镜像，可只开 6080。步骤更长；想快请用方式 A。

#### 注意

1. `NUXT_PUBLIC_NC_BACKEND_URL` 必须是用户浏览器能访问的后端地址。
2. 前端变更后：重建 `.output` → 覆盖 `/opt/mlnocodb/ui-output` → `docker restart mlnocodb-ui`。
3. CentOS 7 宿主不必装 Node，UI 用 `node:22-slim` 容器即可。

### 6.3 升级

```bash
# 构建机出新镜像 mlnocodb:0.1.2 → 传到服务器 docker load
docker stop mlnocodb-api && docker rm mlnocodb-api
# 用新镜像重新 run / compose up（数据在 /opt/mlnocodb/data 与 Meta PG，一般可保留）
# 若使用 6100 UI：同步更新 ui-output 并 docker restart mlnocodb-ui
```

升级前建议：`pg_dump` Meta 库 `mlnoco`。

---

## 7. 常见问题

| 现象 | 处理 |
|------|------|
| 容器起不来 / DB 连不上 | 服务器能否 `telnet 192.168.100.89 5432`；PG `pg_hba.conf` 是否允许该服务器网段；密码是否 `%40` 编码 |
| 页面空白或登录跳转错 | 检查 `NC_PUBLIC_URL` 是否与浏览器地址一致 |
| 海量库加数据源仍报 FK SQL 错 | 确认跑的是 **自建 mlnocodb 镜像**，不是 Docker Hub 官方 `nocodb/nocodb` |
| CentOS 装不上 Docker | 使用内网离线 Docker rpm；或换 Rocky/AlmaLinux 8+ 作宿主（更省事） |
| SELinux 导致卷挂载异常 | 测试可临时 `setenforce 0`，生产用正确 `chcon`/`:z` 卷标签 |

---

## 8. 与本地开发的差异

| 项 | 本地开发 | CentOS 内网生产（本方案） |
|----|----------|---------------------------|
| Backend | `6080` 热更新 | 容器内 `8080` → 宿主 `6080` |
| UI | `6100` 生产包 / `6110` HMR | **可发布** `6100`（挂载 `.output`）；`6080/dashboard` 为备用旧 GUI |
| Meta | `.env` 中 `NC_DB` | 容器环境变量 `NC_DB` |
| 补丁 | 源码直接跑 | **必须打进自建镜像** |

Compose 模板：`docker-compose/centos-internal/docker-compose.yml`（API + 6100 UI）。

更完整的备份、巡检见 [08-系统运维手册.md](./08-系统运维手册.md)。
