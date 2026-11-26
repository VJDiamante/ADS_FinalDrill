import os
import sqlite3
import sys

DB_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(DB_DIR)
DB_PATH = os.path.join(ROOT_DIR, "campusprint.db")
SCHEMA_PATH = os.path.join(DB_DIR, "schema.sql")

sys.path.insert(0, DB_DIR)
from seed import seed

TABLES = ["users", "pricing_rates", "print_orders", "payments", "status_logs"]


def init_db(db_path=DB_PATH):
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    seed(conn)
    conn.commit()
    return conn


def print_summary(conn):
    print("Row counts")
    for table in TABLES:
        count = conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        print("  {:<14}{}".format(table, count))
    print()
    print("v_queue")
    rows = conn.execute(
        "SELECT order_id, user_name, original_filename, order_status, payment_status, total_price "
        "FROM v_queue"
    ).fetchall()
    for r in rows:
        print("  CP-{:06d}  {:<16}{:<22}{:<18}{:<8}{:>8.2f}".format(
            r["order_id"], r["user_name"], r["original_filename"],
            r["order_status"], r["payment_status"], r["total_price"]))


if __name__ == "__main__":
    connection = init_db()
    print("Created " + DB_PATH)
    print()
    print_summary(connection)
    connection.close()
