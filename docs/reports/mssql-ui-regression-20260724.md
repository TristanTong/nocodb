# MSSQL UI 回归报告（最新）

| 项 | 内容 |
|----|------|
| 时间 | 2026-07-24 |
| Meta | `192.168.100.89:5432` / `mlnoco`（`packages/nocodb/.env` → `NC_DB`） |
| Backend | http://localhost:6080 health OK / `0.301.2` |
| Frontend | http://localhost:6100（已重建含 MSSQL） |
| SQL Server 测试库 | `192.168.1.11:5678` / `Metabase_ODS` |

## 结论

**通过。** Meta 连通正常；UI 可见 **SQL Server** 选择与完整配置表单；对 `Metabase_ODS` **Test successful**。

## 发现与修复

打开 SQL Server 集成时配置弹窗曾为空白：`getStaticInitializor` 未注册 `ClientType.MSSQL`。已补齐 `useIntegrationsStore.ts` / `EditOrAdd.vue` 并重建前端。

## 回归轮次

### API / Bundle（3 轮，`scripts/compat/run_mssql_ui_regression.py`）

| 轮次 | health | Meta 登录 | roles | sources | FE | bundle 含 SQL Server |
|------|--------|-----------|-------|---------|----|----------------------|
| 1–3 | PASS | PASS | creator+super | PASS | PASS | PASS |

### UI（浏览器）

| 检查 | 结果 |
|------|------|
| Integrations 列表可见 SQL Server | PASS |
| 搜索 “SQL Server” 仅余该卡片 | PASS |
| 配置表单：Host/Port/User/Password/Database/Schema | PASS（默认 Port `1433`、User `sa`、Schema `dbo`） |
| 填入 `192.168.1.11:5678` / `Metabase_ODS` / Schema `UFDATA` 测试连接 | **Test successful** |
| 连续 3 轮重新打开配置表单 | 见下方脚本结果 |

详细 JSON：`docs/reports/mssql-ui-regression-latest.json`

### UI 连续打开配置表单（3 轮）

| 轮次 | Host/Port 表单可见 |
|------|-------------------|
| 1 | PASS |
| 2 | PASS |
| 3 | PASS |
