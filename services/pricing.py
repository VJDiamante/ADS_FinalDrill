from decimal import Decimal, ROUND_HALF_UP


def _check_positive_int(name, value):
    # bool is a subclass of int, so reject it explicitly
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")


def calculate_total(conn, paper_size, color_mode, page_count, copies):
    """Return the order total as a float rounded to 2 decimals.

    Raises ValueError if the paper/color combination has no rate or if
    page_count or copies is not a positive integer.
    """
    _check_positive_int("page_count", page_count)
    _check_positive_int("copies", copies)

    row = conn.execute(
        """
        SELECT price_per_page
        FROM pricing_rates
        WHERE paper_size = ? AND color_mode = ?
        """,
        (paper_size, color_mode),
    ).fetchone()

    if row is None:
        raise ValueError(f"No price for {paper_size} / {color_mode}")

    # Decimal avoids binary floating-point rounding errors in money math
    price = Decimal(str(row["price_per_page"]))
    total = price * page_count * copies
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
