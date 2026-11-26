-- CampusPrint demo queries
-- Run after: python db/init_db.py
-- Open with:  sqlite3 campusprint.db   then   .read db/demo_queries.sql
-- Tip: .headers on  and  .mode column  make the output easier to read.


-- 1. Staff queue straight from the table: everything not yet completed,
--    oldest submission first.
SELECT order_id, original_filename, order_status, payment_status, created_at
FROM print_orders
WHERE order_status <> 'Completed'
ORDER BY created_at ASC;


-- 2. Join: each order with the name and role of the person who sent it.
SELECT o.order_id, u.name, u.role, o.original_filename, o.order_status
FROM print_orders o
JOIN users u ON u.user_id = o.user_id
ORDER BY o.order_id;


-- 3. How many orders sit in each status right now.
SELECT order_status, COUNT(*) AS orders
FROM print_orders
GROUP BY order_status
ORDER BY orders DESC;


-- 4. Revenue per paper size and color mode, counting only paid orders.
--    The sums come from the payments table, not from the quoted totals.
SELECT o.paper_size, o.color_mode,
       COUNT(*)      AS paid_orders,
       SUM(p.amount) AS revenue
FROM print_orders o
JOIN payments p ON p.order_id = o.order_id
GROUP BY o.paper_size, o.color_mode
ORDER BY revenue DESC;


-- 5. Orders per user, keeping only users with at least 2 orders.
SELECT u.name, COUNT(*) AS orders, SUM(o.total_price) AS total_quoted
FROM users u
JOIN print_orders o ON o.user_id = u.user_id
GROUP BY u.user_id
HAVING COUNT(*) >= 2
ORDER BY orders DESC;


-- 6. Unpaid orders that are ready for pickup. The database will refuse
--    to mark these Completed until a payment row exists.
SELECT order_id, user_name, total_price, order_status, payment_status
FROM v_queue
WHERE order_status = 'Ready for Pickup' AND payment_status = 'unpaid';


-- 7. The queue view. It hides Completed orders and sorts by submission
--    time, so the app does not repeat that logic.
SELECT order_id, user_name, original_filename, order_status, payment_status, version
FROM v_queue;


-- 8. Price snapshot. total_price is what the customer was quoted. The
--    recomputed column uses today's rate. They differ after an admin
--    changes a price, and old orders keep their original total.
SELECT order_id, paper_size, color_mode, page_count, copies,
       total_price AS quoted_total,
       ROUND(current_price_per_page * page_count * copies, 2) AS total_at_current_rate
FROM v_order_details
ORDER BY order_id;


-- 9. Query plan for the staff queue filter. It should say
--    SEARCH ... USING INDEX idx_print_orders_order_status.
EXPLAIN QUERY PLAN
SELECT order_id, original_filename
FROM print_orders
WHERE order_status = 'Processing';


-- 10. Query plan for "My Orders". It should use idx_print_orders_user_id.
EXPLAIN QUERY PLAN
SELECT order_id, order_status
FROM print_orders
WHERE user_id = 1;


-- 11. Audit history written by the status trigger: who moved which order
--     from which status to which, and when.
SELECT l.log_id, l.order_id, l.old_status, l.new_status,
       u.name AS changed_by, l.changed_at
FROM status_logs l
LEFT JOIN users u ON u.user_id = l.changed_by
ORDER BY l.log_id;


-- 12. Cash handling by staff member: how many payments each person
--     recorded and how much.
SELECT u.name, p.method, COUNT(*) AS payments, SUM(p.amount) AS amount
FROM payments p
JOIN users u ON u.user_id = p.received_by
GROUP BY u.user_id, p.method
ORDER BY amount DESC;


-- Live trigger demos. These are commented out because each one is meant
-- to fail. Remove the leading dashes and run them one at a time.

-- Skip a step (order 5 is Pending). Expect: Invalid status transition
-- UPDATE print_orders SET order_status = 'Ready for Pickup' WHERE order_id = 5;

-- Complete an unpaid order (order 3). Expect: Cannot complete an order that has not been paid
-- UPDATE print_orders SET order_status = 'Completed' WHERE order_id = 3;

-- Non-PSU email. Expect: CHECK constraint failed
-- INSERT INTO users (name, email, password_hash, role)
-- VALUES ('Test', 'test@gmail.com', 'x', 'student');

-- Pay order 3, then complete it. Both succeed, and a log row appears.
-- INSERT INTO payments (order_id, amount, method, received_by) VALUES (3, 48.00, 'cash', 3);
-- UPDATE print_orders SET order_status = 'Completed', last_modified_by = 3 WHERE order_id = 3;
-- SELECT * FROM status_logs WHERE order_id = 3;
