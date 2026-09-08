# CentOS 7.6 内网快速部署

| 项 | 内容 |
|----|------|
| 适用系统 | CentOS 7.6（内网服务器） |
| 推荐方式 | **Docker 双容器**：API `6080` + 最新 UI `6100` |
| 源码基线 | mlnocodb `0.301.2`+；推荐里程碑 tag **`v0.1.6`**（MSSQL 稳定：meta-diff/count、无主键自然键、EREQUEST） |
| 推荐 Dockerfile | `packages/nocodb/Dockerfile.centos`（官方 `0.301.2` + 自研 `main.js` + **`mssql` 驱动**） |
| 镜像标签约定 | **必须**带版本号：`mlnocodb:0.1.6`（勿只用 `latest` / 勿 compose 写死 digest） |
| 不推荐 | 在 CentOS 7 上直接安装 Node.js 22（glibc 过旧，易失败） |

关联文档：[08-系统运维手册.md](./08-系统运维手册.md)、[12-SQLServer数据源支持开发方案.md](./12-SQLServer数据源支持开发方案.md)。

---

## 1. 为什么用 Docker

| 方式 | 结论 |
|------|------|
| 本机装 Node 22 + pnpm | CentOS 7.6 通常 **不可行**（glibc 2.17，Node 22 需要更新） |
| Docker 跑应用 | **推荐**：镜像内自带 Node 22，与宿主内核分离 |
| 官方 `nocodb/nocodb:0.301.2` | 可用作**基础层**，但 **不含** 本仓库 Vastbase / SQL Server 补丁，且 **无 `mssql` 包** |
| 本仓库 `Dockerfile.centos` | **内网推荐**：覆盖 `main.js` + 安装 `mssql`，支持海量 FK 与 SQL Server 外部源 |

访问入口（推荐双容器）：

| 用途 | URL |
|------|-----|
| **最新 UI（日常）** | `http://<服务器IP>:6100/` |
| API / 健康 | `http://<服务器IP>:6080/api/v1/health` |
| 版本 | `http://<服务器IP>:6080/api/v1/version` |
| 内置备用 GUI | `http://<服务器IP>:6080/dashboard`（`nc-lib-gui`，可能偏旧） |

> 生产示例（历史环境）：UI 映射到宿主 **80** 时，对外仍是最新 `.output`；本文以 `6100` 说明，按需改端口映射即可。

---

## 2. 部署前准备

### 2.1 服务器与网络

- CentOS 7.6，能访问：
  - **Meta PostgreSQL**（开发示例 `192.168.100.89`；生产示例 `192.168.100.93`，库 `mlnoco`）
  - 业务库按需：海量 Vastbase、**SQL Server**（默认 `1433`，或自定义端口如 `5678`）等
- 开放入站：`6080/tcp`、`6100/tcp`（或 Nginx 仅开 `80`）
- 出站：应用主机 → Meta / 业务库端口（含 SQL Server）
- 磁盘：建议 ≥ 20GB 可用；附件目录单独挂卷 `/opt/mlnocodb/data`

### 2.2 在「构建机」上准备镜像（不要用 CentOS 7 编译）

构建机可用：Windows（Docker Desktop）/ Rocky 8+ / Ubuntu 20.04+。

```bash
git clone <你们的仓库地址> mlnocodb
cd mlnocodb
# 推荐发布点
git checkout v0.1.6

pnpm bootstrap

# 生成后端 docker/main.js（以仓库实际脚本为准）
cd packages/nocodb
pnpm run build        # 或 pnpm run docker:build
# 确认存在：packages/nocodb/docker/main.js
```

用 **CentOS 专用 Dockerfile** 构建（会安装 `mssql`），**标签带版本号**：

```bash
cd packages/nocodb
docker build -t mlnocodb:0.1.6 -f Dockerfile.centos .

# 或一键：python scripts/compat/package_release_0.1.6.py

# 验收驱动（构建阶段已执行；也可运行时再验）
docker run --rm mlnocodb:0.1.6 node -e "require('mssql'); console.log('mssql_ok')"

# 导出给内网（无私有仓库时）
docker save mlnocodb:0.1.6 | gzip > mlnocodb-0.1.6.tar.gz
```

> 勿使用未改的官方镜像直接当生产：缺 Vastbase 补丁且 **`require('mssql')` 会失败**，SQL Server 数据源不可用。

把 `mlnocodb-0.1.6.tar.gz` 拷到 CentOS 服务器（scp / U 盘 / 内网文件站）。

生产 100.93 升级步骤见 [13-生产100.93升级到v0.1.6.md](./13-生产100.93升级到v0.1.6.md)。

---

## 3. CentOS 7.6 安装 Docker（一次性）

CentOS 7 已 EOL，请使用 vault 源或内网镜像源。

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
gunzip -c mlnocodb-0.1.6.tar.gz | docker load
docker images | grep mlnocodb
```

---

## 4. 推荐：API + 最新 UI（双容器）

模板：`docker-compose/centos-internal/docker-compose.yml`。

### 4.1 服务器目录

```bash
sudo mkdir -p /opt/mlnocodb/data /opt/mlnocodb/ui-output
cd /opt/mlnocodb
```

### 4.2 构建并发布 6100 UI（构建机）

```bash
cd mlnocodb
# 与后端同一发布点
export NUXT_PUBLIC_NC_BACKEND_URL=http://<服务器IP>:6080
export NUXT_PAGE_TRANSITION_DISABLE=true
pnpm --filter=nc-gui run build

tar -czf nc-gui-output.tar.gz -C packages/nc-gui .output
# 拷到服务器后：
sudo tar -xzf nc-gui-output.tar.gz -C /opt/mlnocodb
sudo rm -rf /opt/mlnocodb/ui-output
sudo mv /opt/mlnocodb/.output /opt/mlnocodb/ui-output
```

### 4.3 Compose 配置

复制模板并修改：

```bash
cp /path/to/repo/docker-compose/centos-internal/docker-compose.yml /opt/mlnocodb/docker-compose.yml
# 编辑 image 标签、NC_DB、NC_PUBLIC_URL、NUXT_PUBLIC_NC_BACKEND_URL
```

关键环境变量示例：

```yaml
# mlnocodb-api
image: mlnocodb:0.1.6
environment:
  # 生产 Meta 示例（按实际修改；@ → %40）
  NC_DB: "pg://192.168.100.93:5432?u=postgres&p=REPLACE_ME&d=mlnoco"
  NC_DISABLE_TELE: "true"
  NC_PUBLIC_URL: "http://<服务器IP>:6080"
  # NC_AUTH_JWT_SECRET: "<长随机串>"
  TZ: "Asia/Shanghai"

# mlnocodb-ui
environment:
  NUXT_PUBLIC_NC_BACKEND_URL: "http://<服务器IP>:6080"
```

> **不要把含真实密码的 compose 提交进 Git。**

启动：

```bash
cd /opt/mlnocodb
docker compose up -d
# 或：docker-compose up -d
```

### 4.4 验收

```bash
curl -s http://127.0.0.1:6080/api/v1/health
curl -s http://127.0.0.1:6080/api/v1/version
curl -sI http://127.0.0.1:6100/ | head -5

# SQL Server 驱动（必须）
docker exec mlnocodb-api node -e "require('mssql'); console.log('mssql_ok')"
```

浏览器：

- 日常：`http://<服务器IP>:6100/`
- 备用：`http://<服务器IP>:6080/dashboard`

防火墙：

```bash
sudo firewall-cmd --permanent --add-port=6080/tcp
sudo firewall-cmd --permanent --add-port=6100/tcp
sudo firewall-cmd --reload
```

---

## 5. 备选：仅 API 单容器（最快试跑）

无独立 UI 时，可先只起 API，用内置 `/dashboard`：

```bash
docker run -d --name mlnocodb-api --restart always \
  -p 6080:8080 \
  -e NC_DB='pg://192.168.100.93:5432?u=postgres&p=REPLACE_ME&d=mlnoco' \
  -e NC_DISABLE_TELE=true \
  -e NC_PUBLIC_URL='http://<服务器IP>:6080' \
  -e TZ=Asia/Shanghai \
  -v /opt/mlnocodb/data:/usr/app/data \
  mlnocodb:0.1.6
```

后续再按 §4.2 补 6100 UI。

---

## 6. 内网最快路径（总结）

```text
构建机：checkout 发布点 → pnpm bootstrap → 产出 docker/main.js
       → docker build -f Dockerfile.centos → 验证 require('mssql')
       → 构建 nc-gui .output → docker save + tar UI
    ↓ 拷贝
CentOS7：docker load → 配置 NC_DB（生产 Meta）→ compose up（api+ui）
    ↓
浏览器：http://服务器:6100/   （备用 :6080/dashboard）
```

预计耗时：镜像已就绪时，服务器侧通常 **10～30 分钟**；含首次构建视机器 **1～数小时**。

---

## 7. 可选增强

### 7.1 Nginx 反代（统一 80，UI 对外）

将最新 UI 挂到 80，API 仍可只内网访问或同机反代：

```nginx
server {
  listen 80;
  server_name nocodb.internal.example;
  client_max_body_size 100m;

  # 最新 UI → 6100
  location / {
    proxy_pass http://127.0.0.1:6100;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

同时把 `NUXT_PUBLIC_NC_BACKEND_URL` / `NC_PUBLIC_URL` 改成浏览器实际访问的后端地址。

### 7.2 SQL Server 数据源（部署后）

1. 确认容器内 `mssql_ok`（§4.4）。
2. 确认防火墙：应用主机 → SQL Server 端口（`1433` 或实例端口）。
3. 在 UI：**数据源 → SQL Server**，填写 Host/Port/库名/`searchPath`（业务 schema，如 `UFDATA`，不一定是 `dbo`）。
4. 内网 TLS：常关 encrypt 或开启信任服务器证书。
5. 默认「禁止改结构」；仅运维评估后关闭再做 DDL。

用户侧说明见 [07-用户操作说明书.md](./07-用户操作说明书.md)；运维要点见 [08](./08-系统运维手册.md) §8。

### 7.3 升级

```bash
# 构建机：新镜像 mlnocodb:<新标签> + 新 ui-output → 传到服务器 docker load / 覆盖目录
cd /opt/mlnocodb
docker compose pull   # 若用仓库；本地 load 则可跳过
docker compose up -d  # 或 stop/rm 后按新 image 启动
docker restart mlnocodb-ui   # 仅更新了 ui-output 时
docker exec mlnocodb-api node -e "require('mssql'); console.log('mssql_ok')"
```

升级前建议：`pg_dump` Meta 库 `mlnoco`。数据卷 `/opt/mlnocodb/data` 与 Meta PG 一般可保留。

---

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| 容器起不来 / Meta 连不上 | `telnet <meta-host> 5432`；`pg_hba.conf`；密码 `%40` 编码；确认用的是生产 Meta（如 `100.93`）而非开发机 |
| 页面空白或登录跳转错 | `NC_PUBLIC_URL` / `NUXT_PUBLIC_NC_BACKEND_URL` 是否为浏览器可达地址（勿填 localhost） |
| 海量库加源仍报 FK SQL 错 | 确认是 **自建 mlnocodb 镜像**，不是裸官方 `nocodb/nocodb` |
| 添加 SQL Server 失败 / `Cannot find module 'mssql'` | 必须用 `Dockerfile.centos` 构建；`docker exec … require('mssql')` |
| SQL Server 同步 0 表 | 检查 `searchPath`/Schema 是否为业务 schema |
| 6100 与本地 UI 不一致 | 重新 build `.output` 并覆盖 `ui-output` 后重启 `mlnocodb-ui` |
| CentOS 装不上 Docker | 内网离线 Docker rpm；或换 Rocky/AlmaLinux 8+ 作宿主 |
| SELinux 卷挂载异常 | 测试可 `setenforce 0`，生产用正确 `chcon`/`:z` |

---

## 9. 与本地开发的差异

| 项 | 本地开发 | CentOS 内网生产（本方案） |
|----|----------|---------------------------|
| Backend | `6080`（可用 `start:backend:lite`） | 容器内 `8080` → 宿主 `6080` |
| UI | `6100` 生产包 / `6110` HMR | **6100** 挂载 `.output`；`6080/dashboard` 备用 |
| Meta | `.env` → `NC_DB`（常 `100.89`） | 容器环境变量（常生产 `100.93`，以实际为准） |
| 补丁 / mssql | 源码 + `node_modules` | **必须** `Dockerfile.centos` 打进镜像 |
| SQL Server | 本机网络可达测试库 | 服务器出站放行业务 SQL Server 端口 |

Compose 模板：`docker-compose/centos-internal/docker-compose.yml`。

更完整的备份、巡检、MSSQL 运维见 [08-系统运维手册.md](./08-系统运维手册.md)。
