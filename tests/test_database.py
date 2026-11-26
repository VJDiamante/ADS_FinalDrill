import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "db"))

from seed import seed

PENDING_ORDER = 5
PROCESSING_ORDER = 4
READY_UNPAID_ORDER = 3
READY_PAID_ORDER = 2
COMPLETED_ORDER = 1
STAFF_ID = 3
STUDENT_ID = 1


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
    seed(connection)
    connection.commit()
    yield connection
    connection.close()


def add_user(conn, email="new.user@psu.palawan.edu.ph"):
    conn.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("New User", email, "hash", "student"),
    )


def add_order(conn, user_id=STUDENT_ID, paper="A4", color="bw", copies=1, status="Pending"):
    return conn.execute(
        """INSERT INTO print_orders
               (user_id, original_filename, file_path, paper_size, color_mode,
                page_count, copies, total_price, order_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, "test.pdf", "uploads/test.pdf", paper, color, 5, copies, 10.0, status),
    )


def move_order(conn, order_id, new_status):
    conn.execute(
        """UPDATE print_orders
              SET order_status = ?, version = version + 1, last_modified_by = ?
            WHERE order_id = ?""",
        (new_status, STAFF_ID, order_id),
    )


def status_of(conn, order_id):
    row = conn.execute(
        "SELECT order_status FROM print_orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    return row["order_status"]


def test_seed_loads_expected_rows(conn):
    counts = {
        table: conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        for table in ("users", "pricing_rates", "print_orders", "payments", "status_logs")
    }
    assert counts == {
        "users": 4,
        "pricing_rates": 6,
        "print_orders": 6,
        "payments": 2,
        "status_logs": 8,
    }


def test_non_psu_email_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_user(conn, "someone@gmail.com")


def test_psu_email_accepted(conn):
    add_user(conn)
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert count == 5


def test_duplicate_email_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: users.email"):
        add_user(conn, "juan@psu.palawan.edu.ph")


def test_zero_copies_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_order(conn, copies=0)


def test_invalid_status_on_insert_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        add_order(conn, status="Done")


def test_invalid_status_on_update_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        move_order(conn, PENDING_ORDER, "Done")
    assert status_of(conn, PENDING_ORDER) == "Pending"


def test_skipping_a_status_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="Invalid status transition"):
        move_order(conn, PENDING_ORDER, "Ready for Pickup")
    assert status_of(conn, PENDING_ORDER) == "Pending"


def test_going_backwards_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="Invalid status transition"):
        move_order(conn, PROCESSING_ORDER, "Pending")
    assert status_of(conn, PROCESSING_ORDER) == "Processing"


def test_completed_order_cannot_change_again(conn):
    with pytest.raises(sqlite3.IntegrityError, match="Invalid status transition"):
        move_order(conn, COMPLETED_ORDER, "Ready for Pickup")


def test_completed_without_payment_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="has not been paid"):
        move_order(conn, READY_UNPAID_ORDER, "Completed")
    assert status_of(conn, READY_UNPAID_ORDER) == "Ready for Pickup"


def test_completed_allowed_after_payment(conn):
    conn.execute(
        "INSERT INTO payments (order_id, amount, method, received_by) VALUES (?, ?, ?, ?)",
        (READY_UNPAID_ORDER, 48.0, "cash", STAFF_ID),
    )
    move_order(conn, READY_UNPAID_ORDER, "Completed")
    assert status_of(conn, READY_UNPAID_ORDER) == "Completed"


def test_order_with_unknown_user_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        add_order(conn, user_id=999)


def test_order_with_unpriced_paper_and_color_rejected(conn):
    conn.execute("DELETE FROM pricing_rates WHERE paper_size = 'Legal' AND color_mode = 'color'")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        add_order(conn, paper="Legal", color="color")


def test_rate_used_by_an_order_cannot_be_deleted(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        conn.execute("DELETE FROM pricing_rates WHERE paper_size = 'A4' AND color_mode = 'color'")


def test_payment_for_unknown_order_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        conn.execute(
            "INSERT INTO payments (order_id, amount, method, received_by) VALUES (?, ?, ?, ?)",
            (999, 10.0, "cash", STAFF_ID),
        )


def test_user_with_orders_cannot_be_deleted(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        conn.execute("DELETE FROM users WHERE user_id = ?", (STUDENT_ID,))


def test_payment_flips_payment_status_to_paid(conn):
    before = conn.execute(
        "SELECT payment_status, version FROM print_orders WHERE order_id = ?",
        (PROCESSING_ORDER,),
    ).fetchone()
    assert before["payment_status"] == "unpaid"

    conn.execute(
        "INSERT INTO payments (order_id, amount, method, received_by) VALUES (?, ?, ?, ?)",
        (PROCESSING_ORDER, 960.0, "gcash", STAFF_ID),
    )

    after = conn.execute(
        "SELECT payment_status, version FROM print_orders WHERE order_id = ?",
        (PROCESSING_ORDER,),
    ).fetchone()
    assert after["payment_status"] == "paid"
    assert after["version"] == before["version"]


def test_order_cannot_be_paid_twice(conn):
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: payments.order_id"):
        conn.execute(
            "INSERT INTO payments (order_id, amount, method, received_by) VALUES (?, ?, ?, ?)",
            (READY_PAID_ORDER, 300.0, "cash", STAFF_ID),
        )


def test_invalid_payment_method_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        conn.execute(
            "INSERT INTO payments (order_id, amount, method, received_by) VALUES (?, ?, ?, ?)",
            (PROCESSING_ORDER, 960.0, "bitcoin", STAFF_ID),
        )


def test_status_change_creates_one_log_row(conn):
    before = conn.execute(
        "SELECT COUNT(*) FROM status_logs WHERE order_id = ?", (PENDING_ORDER,)
    ).fetchone()[0]

    move_order(conn, PENDING_ORDER, "Processing")

    rows = conn.execute(
        "SELECT old_status, new_status, changed_by FROM status_logs WHERE order_id = ?",
        (PENDING_ORDER,),
    ).fetchall()
    assert len(rows) == before + 1
    assert tuple(rows[-1]) == ("Pending", "Processing", STAFF_ID)


def test_every_step_is_logged_in_order(conn):
    move_order(conn, PENDING_ORDER, "Processing")
    move_order(conn, PENDING_ORDER, "Ready for Pickup")
    conn.execute(
        "INSERT INTO payments (order_id, amount, method, received_by) VALUES (?, ?, ?, ?)",
        (PENDING_ORDER, 12.0, "maya", STAFF_ID),
    )
    move_order(conn, PENDING_ORDER, "Completed")

    steps = [
        (r["old_status"], r["new_status"])
        for r in conn.execute(
            "SELECT old_status, new_status FROM status_logs WHERE order_id = ? ORDER BY log_id",
            (PENDING_ORDER,),
        )
    ]
    assert steps == [
        ("Pending", "Processing"),
        ("Processing", "Ready for Pickup"),
        ("Ready for Pickup", "Completed"),
    ]


def test_rejected_change_writes_no_log_row(conn):
    before = conn.execute("SELECT COUNT(*) FROM status_logs").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        move_order(conn, PENDING_ORDER, "Completed")
    after = conn.execute("SELECT COUNT(*) FROM status_logs").fetchone()[0]
    assert after == before


def test_update_without_status_change_writes_no_log_row(conn):
    before = conn.execute("SELECT COUNT(*) FROM status_logs").fetchone()[0]
    conn.execute("UPDATE print_orders SET copies = 2 WHERE order_id = ?", (PENDING_ORDER,))
    after = conn.execute("SELECT COUNT(*) FROM status_logs").fetchone()[0]
    assert after == before


def test_queue_view_hides_completed_and_sorts_by_submission_time(conn):
    rows = conn.execute("SELECT order_id, order_status, created_at FROM v_queue").fetchall()
    ids = [r["order_id"] for r in rows]
    assert COMPLETED_ORDER not in ids
    assert len(ids) == 5
    stamps = [r["created_at"] for r in rows]
    assert stamps == sorted(stamps)


def test_order_status_query_uses_index(conn):
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM print_orders WHERE order_status = 'Pending'"
    ).fetchall()
    assert any("idx_print_orders_order_status" in row["detail"] for row in plan)
