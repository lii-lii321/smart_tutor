"""临时：查 dev.db 的 applications 表。用完即删。"""
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
conn = sqlite3.connect("dev.db")
rows = conn.execute("SELECT id, order_id, teacher_id, tenant_id, status FROM applications ORDER BY id DESC LIMIT 8").fetchall()
print("applications (latest):")
for r in rows:
    print(" ", r)
tenants = conn.execute("SELECT id, tenant_name, invite_code, is_active FROM tenants ORDER BY id DESC LIMIT 5").fetchall()
print("tenants (latest):")
for t in tenants:
    print(" ", t)
