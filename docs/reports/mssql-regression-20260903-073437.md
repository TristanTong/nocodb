# MSSQL 回归报告 20260903-073437

- Backend: `http://192.168.100.89`
- Base/Source/Table: `pw4yksn9i7x1fx4` / `b6mmr5wqft4lj6l` / `mfovsj7l4h4g32p`
- 结果: **14/15 PASS**

| 用例 | 结果 | 详情 |
|------|------|------|
| TC-ENV-01 health | PASS | {'message': 'OK', 'timestamp': 1788420877901, 'uptime': 862.035805147} |
| TC-ENV-02 version | PASS | {'currentVersion': '0.301.3', 'releaseVersion': '2026.08.1'} |
| TC-AUTH-01 signin/signup | PASS | signin |
| TC-AUTH-03 me | PASS | mssql-ui-test@local.test |
| TC-BASE-01 bases list HTTP | PASS | status=200 |
| TC-DS-06 MSSQL source present | PASS | {"list":[{"upgraderQueries":[],"id":"b1xz5ra6pnrpbjq","base_id":"pw4yksn9i7x1fx4","alias":null,"meta":null,"is_meta":fal |
| TC-MSSQL-META-DIFF load metadata diff | PASS | 200 listen=completed n=49 {"id":"joby3kfuppozwwczt"} |
| TC-MSSQL-META-SYNC trigger | PASS | 200 listen=completed {"id":"jobqs0titkbjaqd6c"} |
| TC-MSSQL-COUNT sync count | PASS | 200 {"count":1} |
| TC-MSSQL-COUNT-VIEW view sync count | PASS | 200 {"count":1} |
| TC-MSSQL-10 grid list | PASS | 200 list_len=1 |
| TC-MSSQL-20 insert+list+delete smoke | FAIL | ins=200 found=True del=500 {"到货单id":1999999001,"到货单列表id":null,"存货编码":"nc-reg-smoke","存货名称":null,"批号":null,"供应商":null,"数量 |
| TC-MSSQL-TABLE meta | PASS | 200 |
| TC-MSSQL-05 wiring | PASS | tos
[PASS] docs/07 SQL Server — 07-用户操作说明书.md
[PASS] docs/08 MSSQL port/TLS — 08-系统运维手册.md
[PASS] live_mssql — {"ok":[{" |
| TC-MSSQL-28 extractor wiring | PASS | MSSQL_EXTRACTOR_OK
 |
