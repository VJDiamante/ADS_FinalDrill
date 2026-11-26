# CampusPrint

CampusPrint is a print request and queue system for Palawan State University. Students upload a document, choose the paper size, color mode and number of copies, and the order joins a queue that staff work through until it is ready for pickup. The project is a Flask web application backed by a SQLite database. The database holds the business rules, so they apply no matter which part of the application writes the data.

This repository was created for ADS (Advanced Database Systems), BSIT3-B2.

## Requirements

- Python 3.13 (the version the project was built and tested with)
- The packages in `requirements.txt` (Flask, pypdf, werkzeug, pytest)

## Setup

1. Clone the repository and open a terminal in the project folder.

2. Install the dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Create the database. This deletes any existing `campusprint.db`, runs `db/schema.sql`, and loads the sample data from `db/seed.py`:

   ```
   python db/init_db.py
   ```

   The script prints row counts for each table and the contents of the queue view, so you can confirm the load worked.

## Running the application

```
python app.py
```

Open `http://127.0.0.1:5000` in your browser. The login page has a dropdown of the seeded users. Choose one to sign in. Students can submit and track their own orders. Staff can open the queue, advance orders, and record payments. Admins can edit prices and read the audit log.

Main pages:

- `/login`: sign in
- `/orders/new`: submit a print request
- `/orders`: a student's own orders
- `/staff/queue`: the staff queue
- `/staff/orders/<id>`: advance an order and record a payment
- `/admin/pricing`: edit the price per page for each paper size and color mode
- `/admin/audit-log`: the history of status changes
- `/db`: a read-only viewer for the tables and views

Uploaded files are saved in the `uploads/` folder. Only PDF, DOC and DOCX files up to 10 MB are accepted.

## Running the tests

```
python -m pytest tests/test_database.py -q
```

The tests run against an in-memory database, so they never change `campusprint.db`. They check the constraints, triggers, and transaction behavior directly in the database.

## Running the required queries

The queries are in `db/demo_queries.sql`. Run them against the database file with the SQLite command-line tool:

```
sqlite3 campusprint.db
```

Then, at the `sqlite>` prompt, run `.headers on` and `.mode column` for readable output, and paste a query from the file. Each query is labeled with a number in the comments.

The file also defines two views:

- `v_queue`: orders that are not yet completed, sorted by submission time
- `v_order_details`: each order with the current price per page for its paper size and color mode

## Database

- `db/schema.sql`: the tables, keys, CHECK constraints, triggers, and views
- `db/seed.py`: the sample users, prices, orders, and payments
- `db/init_db.py`: rebuilds the database from the schema and seed data
- `db/demo_queries.sql`: the queries used in the demonstration

The database has five tables: `users`, `pricing_rates`, `print_orders`, `payments`, and `status_logs`. Triggers enforce the status workflow: an order can only move one step forward, it cannot be completed before it is paid, every status change is logged, and recording a payment marks the order as paid.

## Project structure

```
app.py              application entry point
config.py           paths and settings
db.py               database connection and transaction helper
db/                 schema, seed data, init script, demo queries
routes/             Flask routes for auth, student, staff, admin and the database viewer
services/           file validation, pricing, and order logic
templates/          HTML pages
static/             CSS and the price preview script
tests/              automated database tests
docs/               project specification
```

## Notes

- The login page uses a dropdown of seeded users instead of real passwords. This is a limitation of the prototype and is not suitable for real deployment.
- Set the `CAMPUSPRINT_SECRET_KEY` environment variable before running the application outside a classroom setting. The default key is for development only.
- `campusprint.db` and the uploaded files are not stored in the repository. Run `python db/init_db.py` after cloning to create the database.
