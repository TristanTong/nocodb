import os, paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.100.93", username="root", password=os.environ["REMOTE_SSH_PASSWORD"], timeout=30)
cmd = (
    "docker run --rm --network mlnocodb_default postgres:15-alpine "
    "psql 'postgresql://postgres:Pass%40w0rd@192.168.100.97:5432/mlnoco' "
    "-c \"DELETE FROM nc_base_users_v2 WHERE fk_user_id='usrprobeexport01'; "
    "DELETE FROM nc_users_v2 WHERE email='csv-export-probe@local.test'; "
    "SELECT count(*) AS left_users FROM nc_users_v2 WHERE email='csv-export-probe@local.test';\""
)
_, o, e = c.exec_command(cmd, timeout=60)
print(o.read().decode("utf-8", "replace"))
print(e.read().decode("utf-8", "replace"))
c.close()
