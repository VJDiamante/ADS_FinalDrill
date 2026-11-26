# CampusPrint Project Spec (Shared Contract)

CampusPrint is a Flask + SQLite prototype of a print request and queue system for Palawan State University, built for an Advanced Database Systems class. It runs locally. The database is the showcase; login, payment, printing, and email are placeholders.

Every later stage must follow the names in this file exactly.

## 1. Stack

Python 3.10+, Flask, sqlite3 (stdlib, raw SQL), Jinja2, vanilla JS, werkzeug (password hashing), pypdf (optional PDF page count).

## 2. File Tree (each file is owned by one stage)

```
app.py, config.py, db.py, requirements.txt, .gitignore, README.md
db/schema.sql, db/seed.py, db/init_db.py, db/demo_queries.sql
services/__init__.py, services/pricing.py, services/files.py, services/orders.py
routes/__init__.py, routes/auth.py, routes/student.py, routes/staff.py, routes/admin.py, routes/db_view.py
templates/base.html, _macros.html, login.html, db_view.html
templates/student/new_order.html, my_orders.html, order_detail.html
templates/staff/queue.html, order.html
templates/admin/pricing.html, audit_log.html
static/css/style.css, static/js/price_preview.js
scripts/concurrency_demo.py
tests/test_database.py, tests/test_app_flow.py
uploads/.gitkeep
docs/PROJECT_SPEC.md, ER_DIAGRAM.md, NORMALIZATION.md, REQUIREMENTS_TRACEABILITY.md, DEMO_SCRIPT.md
status/stage_00.md ... status/stage_16.md
```

## 3. Tables

```
users(user_id PK, name, email UNIQUE NOT NULL CHECK email LIKE '%@psu.palawan.edu.ph', password_hash, role CHECK IN ('student','faculty','staff','admin'))

pricing_rates(rate_id PK, paper_size CHECK IN ('A4','Letter','Legal'), color_mode CHECK IN ('bw','color'), price_per_page REAL CHECK >= 0, UNIQUE(paper_size, color_mode))

print_orders(order_id PK AUTOINCREMENT, user_id FK->users, original_filename, file_path, paper_size, color_mode, page_count CHECK > 0, copies CHECK > 0, total_price REAL CHECK >= 0, order_status CHECK IN ('Pending','Processing','Ready for Pickup','Completed') DEFAULT 'Pending', payment_status CHECK IN ('unpaid','paid') DEFAULT 'unpaid', version INTEGER DEFAULT 1, last_modified_by FK->users, created_at, updated_at; composite FK (paper_size, color_mode) -> pricing_rates)

payments(payment_id PK, order_id FK UNIQUE, amount, method CHECK IN ('cash','gcash','maya'), received_by FK->users, paid_at)

status_logs(log_id PK, order_id FK, old_status, new_status, changed_by FK->users, changed_at)
```

### Indexes

- `print_orders(order_status)`
- `print_orders(user_id)`
- `print_orders(created_at)`

### Triggers

1. Log every status change into `status_logs`.
2. Reject invalid transitions (only Pending -> Processing -> Ready for Pickup -> Completed, no skipping or going back).
3. Reject Completed unless `payment_status = 'paid'`.
4. After INSERT on `payments`, set the order's `payment_status = 'paid'`.

### Views

- `v_queue`: active orders (not Completed), ordered by `created_at` ASC, joined with user name.
- `v_order_details`: order + user + price info.

## 4. Seeded Users

All passwords are `demo1234`, stored hashed.

| Name | Role | Email |
|---|---|---|
| Juan Dela Cruz | student | juan@psu.palawan.edu.ph |
| Maria Santos | faculty | maria@psu.palawan.edu.ph |
| Pedro Reyes | staff | pedro.staff@psu.palawan.edu.ph |
| Ana Admin | admin | admin@psu.palawan.edu.ph |

Seed pricing for all 6 paper/color combinations, plus a few sample orders in different statuses.

## 5. Routes

| Blueprint | Access | Routes |
|---|---|---|
| auth | public | `GET /` (redirect by role), `GET+POST /login` (dropdown of seeded users, placeholder for Google OAuth), `POST /logout` |
| student | roles student, faculty | `GET+POST /orders/new`, `GET /orders`, `GET /orders/<id>`, `POST /api/price` (JSON) |
| staff | roles staff, admin | `GET /staff/queue`, `GET /staff/orders/<id>`, `POST /staff/orders/<id>/advance` (form includes version), `POST /staff/orders/<id>/pay` |
| admin | role admin | `GET+POST /admin/pricing`, `GET /admin/audit-log` |
| db_view | any logged-in user | `GET /db`, `GET /db/<table>` (read-only, whitelist of the 5 tables + 2 views) |

## 6. Service Functions

All take an open sqlite3 connection as the first argument.

- `pricing.calculate_total(conn, paper_size, color_mode, page_count, copies)` -> float rounded to 2 decimals; raises `ValueError` on bad input.
- `files.validate_and_save(file_storage, upload_dir)` -> dict(`original_filename`, `stored_path`, `size_bytes`, `detected_page_count` or None); allows .pdf/.doc/.docx, max 10 MB, uuid-based stored name. (This function does not take a connection.)
- `orders.create_order(conn, user_id, file_info, paper_size, color_mode, page_count, copies)` -> `order_id` (ONE transaction, rollback on failure).
- `orders.get_order(conn, order_id)`
- `orders.list_orders_for_user(conn, user_id)`
- `orders.list_queue(conn)`
- `orders.advance_status(conn, order_id, expected_version, changed_by)` -> new status; raises `ConflictError` if version mismatch (optimistic locking).
- `orders.mark_paid(conn, order_id, received_by, method)` -> `payment_id`
- `orders.ConflictError` exception class.

## 7. Conventions

- Display order IDs as `CP-000123`.
- Session stores `user_id` and `role`.
- `db.get_db()` returns a connection with `row_factory=sqlite3.Row` and foreign keys ON.
- Database file is `campusprint.db` in the project root.
- `SECRET_KEY` lives in `config.py`.
