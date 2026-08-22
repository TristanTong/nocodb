# mldata.mlhr — 人才库一期表（IT-AI-2026-003）

## 连接信息（NocoDB 外部数据源）

| 项 | 值 |
|----|-----|
| Host | `192.168.100.89` |
| Port | `5432` |
| Database | **`mldata`** |
| Schema | **`mlhr`** |
| User | `postgres`（或只读/读写业务账号） |

密码勿写入 Git；本地用环境变量 `MLHR_PG_PASSWORD`。

## 已建表

| 表 | 说明 |
|----|------|
| `mlhr.raw_resume` | 泛简历池 |
| `mlhr.candidate` | 候选人正式表 |
| `mlhr.job_req` | 岗位需求 |
| `mlhr.interview_note` | 面评（P1） |
| `mlhr.op_log` | 操作日志 |

DDL 文件：[`scripts/mlhr_talent_phase1.sql`](./mlhr_talent_phase1.sql)

增量：[`scripts/mlhr_add_resume_filename.sql`](./mlhr_add_resume_filename.sql)（原始简历文件名）  
增量：[`scripts/mlhr_add_candidate_created_by.sql`](./mlhr_add_candidate_created_by.sql)（候选人上传人）

应用/重跑：

```bash
set MLHR_PG_PASSWORD=***
python scripts/apply_mlhr_talent_schema.py
python scripts/apply_mlhr_resume_filename.py
python scripts/apply_mlhr_candidate_created_by.py
python scripts/verify_mlhr_tables.py
```

## NocoDB 接入步骤

1. NocoDB → 数据源 → 连接 PostgreSQL（同上主机库名）。  
2. 选择 schema **`mlhr`**，同步/导入 `raw_resume`、`candidate`、`job_req`。  
3. 建视图：`HR_工作台`（candidate 可编辑标记列）、`简历池_待补全`（`pool_status = need_complete`）。  
4. 系统写入 Token 与 HR 编辑账号分离（见专项 04 详设）。

字段口径对齐：`medlinketfastadmin/docs/人才库与人事档案库/04-详细设计文档.md`。
