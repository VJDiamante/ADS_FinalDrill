-- =====================================================================
-- CampusPrint database schema (SQLite)
-- Palawan State University print request and queue system
--
-- Design goal: enforce the business rules INSIDE the database
-- (constraints, triggers, views), so the rules hold no matter which
-- program or person writes to the data.
--
-- This script is re-runnable: it drops everything first.
-- It contains NO seed data (see db/seed.py).
-- All timestamps are stored as UTC text 'YYYY-MM-DD HH:MM:SS'.
-- =====================================================================

-- SQLite ignores foreign keys unless this is ON for each connection.
-- (The application must also run it on every connection it opens.)
PRAGMA foreign_keys = ON;


-- =====================================================================
-- 0. DROP EVERYTHING (views, then triggers, then tables child-first)
-- =====================================================================
DROP VIEW    IF EXISTS v_order_details;
DROP VIEW    IF EXISTS v_queue;

DROP TRIGGER IF EXISTS trg_payments_mark_order_paid;
DROP TRIGGER IF EXISTS trg_orders_log_status_change;
DROP TRIGGER IF EXISTS trg_orders_require_payment_for_completed;
DROP TRIGGER IF EXISTS trg_orders_validate_status_transition;

DROP TABLE   IF EXISTS status_logs;
DROP TABLE   IF EXISTS payments;
DROP TABLE   IF EXISTS print_orders;
DROP TABLE   IF EXISTS pricing_rates;
DROP TABLE   IF EXISTS users;


-- =====================================================================
-- 1. USERS
-- Design: one table for every kind of account; 'role' decides what the
-- person may do. The CHECK on email enforces the "PSU emails only"
-- requirement (FR-1) at the database level, not just in the web form.
-- Note: SQLite's LIKE is case-insensitive for ASCII, which is what we
-- want for email domains.
-- =====================================================================
CREATE TABLE users (
    user_id       INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE
                  CHECK (email LIKE '%@psu.palawan.edu.ph'),
    password_hash TEXT NOT NULL,        -- hashed with werkzeug, never plain text
    role          TEXT NOT NULL
                  CHECK (role IN ('student', 'faculty', 'staff', 'admin'))
);


-- =====================================================================
-- 2. PRICING_RATES
-- Design: prices live in their own table instead of being repeated on
-- every order. This is normalization (3NF): price_per_page depends on
-- (paper_size, color_mode), not on the order. The admin changes a rate
-- in ONE row, which avoids update anomalies.
-- UNIQUE(paper_size, color_mode) means one rate per combination, and it
-- also lets print_orders reference the pair with a composite foreign key.
-- =====================================================================
CREATE TABLE pricing_rates (
    rate_id        INTEGER PRIMARY KEY,
    paper_size     TEXT NOT NULL
                   CHECK (paper_size IN ('A4', 'Letter', 'Legal')),
    color_mode     TEXT NOT NULL
                   CHECK (color_mode IN ('bw', 'color')),
    price_per_page REAL NOT NULL
                   CHECK (price_per_page >= 0),
    UNIQUE (paper_size, color_mode)
);


-- =====================================================================
-- 3. PRINT_ORDERS
-- Design notes:
--  * total_price is a SNAPSHOT: it is stored when the order is created,
--    so later changes to pricing_rates do not change old orders or
--    past revenue. This is an intentional, documented denormalization.
--  * The composite foreign key (paper_size, color_mode) guarantees that
--    every order uses a paper/color combination that has a price.
--  * version supports optimistic locking: the app updates a row only
--    WHERE version = <the version it read>, then increments version.
--    If two staff members act on the same order, the second one fails.
--  * last_modified_by records WHO is changing the row, so the status
--    logging trigger can copy it into status_logs.changed_by (a trigger
--    cannot see the logged-in user on its own). It is NULL for a brand
--    new order that nobody has modified yet.
--  * payment_status is flipped to 'paid' by a trigger on payments.
-- =====================================================================
CREATE TABLE print_orders (
    order_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users (user_id),
    original_filename TEXT NOT NULL,
    file_path         TEXT NOT NULL,
    paper_size        TEXT NOT NULL,
    color_mode        TEXT NOT NULL,
    page_count        INTEGER NOT NULL CHECK (page_count > 0),
    copies            INTEGER NOT NULL CHECK (copies > 0),
    total_price       REAL NOT NULL CHECK (total_price >= 0),
    order_status      TEXT NOT NULL DEFAULT 'Pending'
                      CHECK (order_status IN
                             ('Pending', 'Processing', 'Ready for Pickup', 'Completed')),
    payment_status    TEXT NOT NULL DEFAULT 'unpaid'
                      CHECK (payment_status IN ('unpaid', 'paid')),
    version           INTEGER NOT NULL DEFAULT 1,
    last_modified_by  INTEGER REFERENCES users (user_id),
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    FOREIGN KEY (paper_size, color_mode)
        REFERENCES pricing_rates (paper_size, color_mode)
);


-- =====================================================================
-- 4. PAYMENTS
-- Design: payment is its own entity (not just a column) so we keep the
-- method, amount, who received it, and when. UNIQUE(order_id) makes the
-- relationship 1:1, so an order cannot be paid twice.
-- =====================================================================
CREATE TABLE payments (
    payment_id  INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL UNIQUE REFERENCES print_orders (order_id),
    amount      REAL NOT NULL CHECK (amount >= 0),
    method      TEXT NOT NULL CHECK (method IN ('cash', 'gcash', 'maya')),
    received_by INTEGER NOT NULL REFERENCES users (user_id),
    paid_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
);


-- =====================================================================
-- 5. STATUS_LOGS (audit history)
-- Design: append-only history of every status change, filled
-- automatically by a trigger so no code path can forget to log.
-- old_status is the previous status, new_status is the new one.
-- changed_by is copied from print_orders.last_modified_by.
-- =====================================================================
CREATE TABLE status_logs (
    log_id     INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES print_orders (order_id),
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by INTEGER REFERENCES users (user_id),
    changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
);


-- =====================================================================
-- 6. INDEXES
-- Each index speeds up a query the app runs often.
--  * order_status: the staff queue filters by status.
--  * user_id:      "My Orders" looks up all orders of one user.
--  * created_at:   the queue is sorted by submission time.
-- =====================================================================
CREATE INDEX idx_print_orders_order_status ON print_orders (order_status);
CREATE INDEX idx_print_orders_user_id      ON print_orders (user_id);
CREATE INDEX idx_print_orders_created_at   ON print_orders (created_at);


-- =====================================================================
-- 7. TRIGGERS
-- The two validation triggers are BEFORE triggers (they stop a bad
-- change before it is written). The logging trigger is an AFTER trigger
-- (it only logs changes that were actually accepted).
-- All of them run only when order_status is really changing.
-- =====================================================================

-- Trigger 2: only allow Pending -> Processing -> Ready for Pickup -> Completed.
-- No skipping steps and no going backwards.
CREATE TRIGGER trg_orders_validate_status_transition
BEFORE UPDATE OF order_status ON print_orders
WHEN NEW.order_status IS NOT OLD.order_status
 AND NOT (
        (OLD.order_status = 'Pending'          AND NEW.order_status = 'Processing')
     OR (OLD.order_status = 'Processing'       AND NEW.order_status = 'Ready for Pickup')
     OR (OLD.order_status = 'Ready for Pickup' AND NEW.order_status = 'Completed')
 )
BEGIN
    SELECT RAISE(ABORT, 'Invalid status transition: allowed order is Pending -> Processing -> Ready for Pickup -> Completed');
END;

-- Trigger 3: an order cannot be Completed until it has been paid.
CREATE TRIGGER trg_orders_require_payment_for_completed
BEFORE UPDATE OF order_status ON print_orders
WHEN NEW.order_status = 'Completed'
 AND OLD.order_status IS NOT 'Completed'
 AND NEW.payment_status <> 'paid'
BEGIN
    SELECT RAISE(ABORT, 'Cannot complete an order that has not been paid');
END;

-- Trigger 1: write every accepted status change into status_logs.
CREATE TRIGGER trg_orders_log_status_change
AFTER UPDATE OF order_status ON print_orders
WHEN NEW.order_status IS NOT OLD.order_status
BEGIN
    INSERT INTO status_logs (order_id, old_status, new_status, changed_by)
    VALUES (NEW.order_id, OLD.order_status, NEW.order_status, NEW.last_modified_by);
END;

-- Trigger 4: recording a payment automatically marks the order as paid.
-- Note: this deliberately does NOT change print_orders.version, so a
-- staff member who is holding a page open can still advance the status
-- after recording a payment without getting a false conflict.
CREATE TRIGGER trg_payments_mark_order_paid
AFTER INSERT ON payments
BEGIN
    UPDATE print_orders
       SET payment_status = 'paid',
           updated_at     = strftime('%Y-%m-%d %H:%M:%S', 'now')
     WHERE order_id = NEW.order_id;
END;


-- =====================================================================
-- 8. VIEWS
-- Views hide repeated joins so the app and the demo queries stay short.
-- =====================================================================

-- v_queue: the live staff queue. Orders that are not Completed, oldest
-- first (first come, first served), with the customer's name attached.
CREATE VIEW v_queue AS
SELECT o.order_id,
       o.user_id,
       u.name  AS user_name,
       u.email AS user_email,
       o.original_filename,
       o.paper_size,
       o.color_mode,
       o.page_count,
       o.copies,
       o.total_price,
       o.order_status,
       o.payment_status,
       o.version,
       o.created_at,
       o.updated_at
  FROM print_orders o
  JOIN users u ON u.user_id = o.user_id
 WHERE o.order_status <> 'Completed'
 ORDER BY o.created_at ASC, o.order_id ASC;

-- v_order_details: one order with its owner and the CURRENT price per
-- page. Compare current_price_per_page with total_price to see the
-- snapshot idea: old orders keep the price they were created with.
CREATE VIEW v_order_details AS
SELECT o.order_id,
       o.user_id,
       u.name  AS user_name,
       u.email AS user_email,
       u.role  AS user_role,
       o.original_filename,
       o.file_path,
       o.paper_size,
       o.color_mode,
       o.page_count,
       o.copies,
       r.price_per_page AS current_price_per_page,
       o.total_price,
       o.order_status,
       o.payment_status,
       o.version,
       o.last_modified_by,
       o.created_at,
       o.updated_at
  FROM print_orders o
  JOIN users u         ON u.user_id = o.user_id
  JOIN pricing_rates r ON r.paper_size = o.paper_size
                      AND r.color_mode = o.color_mode;
