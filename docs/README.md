# mlnocodb 项目文档

本目录为 **mlnocodb**（基于 NocoDB 开源版二次开发）的工程文档集，版本基线对应源码 `0.301.2`；文档集版本 **v0.1.3**（含 SQL Server 外部源 Phase 0～5）。

| 文档 | 说明 |
|------|------|
| [01-项目需求分析文档.md](./01-项目需求分析文档.md) | 背景、目标、干系人、功能/非功能需求 |
| [02-架构设计文档.md](./02-架构设计文档.md) | 总体架构、部署视图、技术选型 |
| [03-系统设计文档.md](./03-系统设计文档.md) | 模块划分、数据流、接口与安全 |
| [04-详细设计文档.md](./04-详细设计文档.md) | 关键模块、Meta/数据源、MSSQL/海量改造点 |
| [05-自动化测试方案.md](./05-自动化测试方案.md) | 测试策略、工具链、MSSQL/海量脚本 |
| [06-测试用例文档.md](./06-测试用例文档.md) | 功能/兼容/运维相关用例清单 |
| [07-用户操作说明书.md](./07-用户操作说明书.md) | 登录、Base、数据源（含 SQL Server）、视图 |
| [08-系统运维手册.md](./08-系统运维手册.md) | 安装、配置、启停、备份、MSSQL 运维、排障 |
| [09-NocoDB项目分析文档.md](./09-NocoDB项目分析文档.md) | NocoDB 开源能力与架构分析 |
| [10-上游功能对比与开发计划.md](./10-上游功能对比与开发计划.md) | 对照上游、免费/收费澄清、迭代路线 |
| [11-CentOS7快速部署.md](./11-CentOS7快速部署.md) | CentOS 7.6：`Dockerfile.centos`（含 mssql）+ API/6100 UI 双容器 |
| [12-SQLServer数据源支持开发方案.md](./12-SQLServer数据源支持开发方案.md) | SQL Server 外部数据源方案与实施进度 |
| [reports/](./reports/) | 自动化冒烟测试报告（latest） |

## 本地开发入口（本仓库约定）

| 服务 | 地址 | 说明 |
|------|------|------|
| Backend | http://localhost:6080 | Nest API；`/dashboard` 为内置静态 GUI |
| Frontend | http://localhost:6100 | 生产构建 UI（日常打开；首屏目标 ≤3s） |
| Frontend HMR | http://localhost:6110 | Nuxt 热更新（改 UI 源码时用） |

```bash
pnpm bootstrap
pnpm start:backend:lite     # 低内存推荐；或 pnpm start:backend
pnpm start:frontend:build   # 首次或前端变更后
pnpm start:frontend         # http://localhost:6100/
# 改 nc-gui：pnpm start:frontend:dev  → :6110
# 打开速度门禁：pnpm test:frontend-open
# MSSQL：pnpm test:mssql-wiring / test:mssql-phase2～4
```
