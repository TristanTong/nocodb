# MSSQL 回归报告 20260903-072203

- Backend: `http://192.168.100.89`
- Base/Source/Table: `pw4yksn9i7x1fx4` / `b6mmr5wqft4lj6l` / `mfovsj7l4h4g32p`
- 结果: **12/12 PASS**

| 用例 | 结果 | 详情 |
|------|------|------|
| TC-ENV-01 health | PASS | {'message': 'OK', 'timestamp': 1788420123127, 'uptime': 107.261464406} |
| TC-ENV-02 version | PASS | {'currentVersion': '0.301.3', 'releaseVersion': '2026.08.1'} |
| TC-AUTH-01 signin/signup | PASS | signin |
| TC-AUTH-03 me | PASS | mssql-ui-test@local.test |
| TC-BASE-01 bases list HTTP | PASS | status=200 |
| TC-DS-06 MSSQL source present | PASS | {"list":[{"upgraderQueries":[],"id":"b1xz5ra6pnrpbjq","base_id":"pw4yksn9i7x1fx4","alias":null,"meta":null,"is_meta":fal |
| TC-MSSQL-META-DIFF load metadata diff | PASS | 200 {"id":"job2apz9xi0ym2zea"} |
| TC-MSSQL-META-SYNC trigger | PASS | 200 {"id":"joby96z470onf6y1f"} |
| TC-MSSQL-COUNT sync count | PASS | 200 {"count":0} |
| TC-MSSQL-10 grid list | PASS | 200 list_len=0 |
| TC-MSSQL-TABLE meta | PASS | 200 |
| TC-MSSQL-05 wiring | PASS | PASS] formula TRIM��LTRIM/RTRIM �� functionMappings/mssql.ts
[PASS] formula COALESCE map �� functionMappings/mssql.ts
[P |
