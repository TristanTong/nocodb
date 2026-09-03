# MSSQL 回归报告 20260903-074029

- Backend: `http://192.168.100.89`
- Base/Source/Table: `pw4yksn9i7x1fx4` / `b6mmr5wqft4lj6l` / `mfovsj7l4h4g32p`
- 结果: **15/16 PASS**

| 用例 | 结果 | 详情 |
|------|------|------|
| TC-ENV-01 health | PASS | {'message': 'OK', 'timestamp': 1788421229565, 'uptime': 35.575157816} |
| TC-ENV-02 version | PASS | {'currentVersion': '0.301.3', 'releaseVersion': None} |
| TC-AUTH-01 signin/signup | PASS | signin |
| TC-AUTH-03 me | PASS | mssql-ui-test@local.test |
| TC-BASE-01 bases list HTTP | PASS | status=200 |
| TC-DS-06 MSSQL source present | PASS | {"list":[{"upgraderQueries":[],"id":"b1xz5ra6pnrpbjq","base_id":"pw4yksn9i7x1fx4","alias":null,"meta":null,"is_meta":fal |
| TC-MSSQL-META-DIFF load metadata diff | PASS | 200 listen=completed n=49 {"id":"jobqg4pv5hes3d2kl"} |
| TC-MSSQL-META-SYNC trigger | FAIL | 400 listen=skip {"msg":"Meta sync already in progress for this base"} |
| TC-MSSQL-COUNT sync count | PASS | 200 {"count":0} |
| TC-MSSQL-COUNT-VIEW view sync count | PASS | 200 {"count":0} |
| TC-MSSQL-10 grid list | PASS | 200 list_len=0 |
| TC-MSSQL-20 insert+update+delete smoke | PASS | table=_nc_p2_1784943212 ins=200 id=1 upd=200 del=200 |
| TC-MSSQL-NOPK delete without PK is 4xx | PASS | 400 {"msg":"Primary key is required to delete records from this table"} |
| TC-MSSQL-TABLE meta | PASS | 200 |
| TC-MSSQL-05 wiring | PASS | tos
[PASS] docs/07 SQL Server — 07-用户操作说明书.md
[PASS] docs/08 MSSQL port/TLS — 08-系统运维手册.md
[PASS] live_mssql — {"ok":[{" |
| TC-MSSQL-28 extractor wiring | PASS | MSSQL_EXTRACTOR_OK
 |
