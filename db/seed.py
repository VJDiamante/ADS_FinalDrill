from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

DEMO_PASSWORD = "demo1234"

USERS = [
    ("Juan Dela Cruz", "juan@psu.palawan.edu.ph", "student"),
    ("Maria Santos", "maria@psu.palawan.edu.ph", "faculty"),
    ("Pedro Reyes", "pedro.staff@psu.palawan.edu.ph", "staff"),
    ("Ana Admin", "admin@psu.palawan.edu.ph", "admin"),
]

RATES = [
    ("A4", "bw", 2.00),
    ("A4", "color", 8.00),
    ("Letter", "bw", 2.00),
    ("Letter", "color", 8.00),
    ("Legal", "bw", 3.00),
    ("Legal", "color", 10.00),
]

STATUS_STEPS = ["Pending", "Processing", "Ready for Pickup", "Completed"]

# user email, file, paper, color, pages, copies, final status, paid, minutes ago, payment method
ORDERS = [
    ("juan@psu.palawan.edu.ph", "thesis_chapter1.pdf", "A4", "bw", 42, 1, "Completed", True, 180, "cash"),
    ("maria@psu.palawan.edu.ph", "lecture_notes.pdf", "Letter", "bw", 30, 5, "Ready for Pickup", True, 120, "gcash"),
    ("juan@psu.palawan.edu.ph", "poster_draft.pdf", "A4", "color", 3, 2, "Ready for Pickup", False, 90, None),
    ("maria@psu.palawan.edu.ph", "exam_set_a.docx", "Legal", "bw", 8, 40, "Processing", False, 45, None),
    ("juan@psu.palawan.edu.ph", "resume.pdf", "A4", "bw", 2, 3, "Pending", False, 15, None),
    ("maria@psu.palawan.edu.ph", "syllabus.docx", "Letter", "color", 6, 1, "Pending", False, 5, None),
]


def _stamp(minutes_ago=0):
    moment = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _insert_users(conn):
    password_hash = generate_password_hash(DEMO_PASSWORD)
    for name, email, role in USERS:
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (name, email, password_hash, role),
        )


def _insert_rates(conn):
    conn.executemany(
        "INSERT INTO pricing_rates (paper_size, color_mode, price_per_page) VALUES (?, ?, ?)",
        RATES,
    )


def _user_id(conn, email):
    return conn.execute("SELECT user_id FROM users WHERE email = ?", (email,)).fetchone()[0]


def _insert_order(conn, user_id, filename, paper, color, pages, copies, minutes_ago):
    rate = conn.execute(
        "SELECT price_per_page FROM pricing_rates WHERE paper_size = ? AND color_mode = ?",
        (paper, color),
    ).fetchone()[0]
    total = round(rate * pages * copies, 2)
    created = _stamp(minutes_ago)
    cursor = conn.execute(
        """INSERT INTO print_orders
               (user_id, original_filename, file_path, paper_size, color_mode,
                page_count, copies, total_price, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, filename, "uploads/sample_" + filename, paper, color,
         pages, copies, total, created, created),
    )
    return cursor.lastrowid, total


def _advance(conn, order_id, new_status, staff_id, minutes_ago):
    conn.execute(
        """UPDATE print_orders
              SET order_status = ?, version = version + 1,
                  last_modified_by = ?, updated_at = ?
            WHERE order_id = ?""",
        (new_status, staff_id, _stamp(minutes_ago), order_id),
    )


def _record_payment(conn, order_id, amount, method, staff_id, minutes_ago):
    conn.execute(
        """INSERT INTO payments (order_id, amount, method, received_by, paid_at)
           VALUES (?, ?, ?, ?, ?)""",
        (order_id, amount, method, staff_id, _stamp(minutes_ago)),
    )


def _insert_orders(conn):
    staff_id = _user_id(conn, "pedro.staff@psu.palawan.edu.ph")
    for (email, filename, paper, color, pages, copies,
         final_status, paid, minutes_ago, method) in ORDERS:
        order_id, total = _insert_order(
            conn, _user_id(conn, email), filename, paper, color, pages, copies, minutes_ago
        )
        target = STATUS_STEPS.index(final_status)
        for step in range(1, target + 1):
            new_status = STATUS_STEPS[step]
            when = max(minutes_ago - step * 5, 0)
            _advance(conn, order_id, new_status, staff_id, when)
            if paid and new_status == "Ready for Pickup":
                _record_payment(conn, order_id, total, method, staff_id, when)


def seed(conn):
    _insert_users(conn)
    _insert_rates(conn)
    _insert_orders(conn)
