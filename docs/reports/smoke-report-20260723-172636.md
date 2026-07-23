# mlnocodb 自动化冒烟测试报告

- 时间: 2026-07-23T17:26:36
- Backend: `http://127.0.0.1:6080`
- Frontend: `http://127.0.0.1:6100`
- 汇总: **23 passed** / 0 failed / 0 blocked / 7 skip （共 30）

| 用例 | 标题 | 结果 | 耗时ms | 详情 |
|------|------|------|--------|------|
| TC-DS-01 | 添加标准 PG 源 UI | skip | 0 | 需浏览器 UI / Playwright |
| TC-DS-03 | 海量源同步 UI（SQL 层已由 COMPAT/VB 覆盖） | skip | 0 | 需浏览器 UI / Playwright |
| TC-DS-05 | 错误密码 UI 提示 | skip | 0 | 需浏览器 UI / Playwright |
| TC-VIEW-01 | 切换表单视图 UI | skip | 0 | 需浏览器 UI / Playwright |
| TC-VIEW-02 | 切换看板 UI | skip | 0 | 需浏览器 UI / Playwright |
| TC-ENV-01 | Backend 健康检查 | pass | 65 | status=200 body={'message': 'OK', 'timestamp': 1784798785701, 'uptime': 2066.2513912} |
| TC-ENV-02 | 版本接口 | pass | 2 | status=200 version=0.301.2 |
| TC-ENV-03 | Frontend 可访问 | pass | 2 | status=200 len=19082 |
| TC-AUTH-01 | 正确账号登录 | pass | 87 | status=200 email=tristantong@qq.com token=yes |
| TC-AUTH-02 | 错误密码拒绝 | pass | 3 | status=400 body={'msg': 'Invalid credentials'} |
| TC-AUTH-03 | user/me guest+authed | pass | 5 | guest_ok=True authed_status=200 email=tristantong@qq.com |
| TC-BASE-01 | 登录后 Base 列表 | pass | 10 | status=200 count=26 sample=['公共数据集', '运营生产部数据集', '法规部数据集', '流信部数据集', '始兴发货项目'] |
| TC-BASE-02 | 打开 Base 表列表 | pass | 5 | status=200 base=prccnooekrjgzqv tables=2 sample=[{'id': 'muhmp4hezsd1wsu', 'title': '法规部邮箱通讯录', 'table_name': '法规部邮箱通讯录'}, {'id': 'm3cba4pcy52dkvt', 'title': '证件与印章收集表', 'table_nam |
| TC-GRID-01 | 网格/记录列表 | pass | 20 | status=200 table=muhmp4hezsd1wsu rows=5 |
| TC-GRID-02 | 网格新增 | skip | 0 | shared Meta/production bases: skip write; Vastbase isolation CRUD covered by TC-VB-03 |
| TC-GRID-03 | 网格编辑 | skip | 0 | shared Meta/production bases: skip write; Vastbase isolation CRUD covered by TC-VB-03 |
| TC-DS-04 | 登录后数据源列表 | pass | 59 | bases=26 enabled_pg_sources=13 sample=[{'base': '公共数据集', 'alias': '公开数据', 'id': 'bir6yxdyc1pzufm'}, {'base': '运营生产部数据集', 'alias': '运营生产部数据', 'id': 'bqtr997ew99a6tc'}, {'base': '法规部 |
| TC-PORT-01 | 6080/6100 可访问 | pass | 32 | backend=True frontend=True dashboard_code=200 |
| TC-PERF-01 | Frontend 打开≤3s | pass | 9410 | budget=3000ms runs=[{'run': 1, 'openMs': 1705, 'passed': True, 'rc': 0}, {'run': 2, 'openMs': 1659, 'passed': True, 'rc': 0}, {'run': 3, 'openMs': 1658, 'passed': True, 'rc': 0}] m |
| TC-BUILD-01 | PgClient 无 WITH ORDINALITY | pass | 3 | has_ORDINALITY_in_code=False has_generate_series=True |
| TC-META-01 | Meta info + sqlite mtime | pass | 509 | info_version=0.301.2 noco_db_mtime_before=1784784914.7417717 after=1784784914.7417717 |
| TC-META-02 | Meta PG 有用户/Base | pass | 78 | pg_users=52 pg_bases=28 info=200 |
| TC-DS-02 | 海量库连接 metabase_rpt | pass | 44 | db=('metabase_rpt', 'sa') |
| TC-COMPAT-01 | Vastbase relationListAll SQL | pass | 49 | rows=0 |
| TC-COMPAT-02 | 标准 PG FK 列映射 | pass | 30 | rows=[('public', '_nc_fk_test_child_parent_id_fkey', '_nc_fk_test_child', 'parent_id', 'public', '_nc_fk_test_parent', 'id')] |
| TC-VB-01 | 列举 schema/表 | pass | 48 | tables_by_schema=[('dbo', 36), ('py_etl', 15)] |
| TC-VB-02 | 只读抽样 dbo 表 | pass | 40 | table=APS出货清单列表 sample_rows=5 |
| TC-VB-03 | 隔离表 CRUD(含04/05) | pass | 60 | crud ok on dbo."_nc_auto_test_1784798796" |
| TC-VB-06 | 错误密码连接失败 | pass | 65 | connection to server at "192.168.100.99", port 5432 failed: FATAL:  Invalid username/password,login denied. |
| TC-VB-07 | introspect+表列表联调 | pass | 46 | fk_rows=0 dbo_tables=36 |

## 说明

- 海量表操作使用隔离表 `_nc_auto_test_*`，已自动 DROP。
- `TC-AUTH-01` 等需登录的用例在未设置 `NC_TEST_EMAIL`/`NC_TEST_PASSWORD` 时记为 blocked。
- UI 级 GRID/VIEW 用例未在本轮 API/SQL 冒烟中执行（见 Playwright）。
