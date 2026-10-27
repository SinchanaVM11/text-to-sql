import argparse
import csv
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

TABLE_FILES = {
    "customers": "olist_customers_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "product_category_translation": "product_category_name_translation.csv",
}

INDEXES = {
    "orders": [
        ("idx_orders_customer_id", ["customer_id"]),
        ("idx_orders_status", ["order_status"]),
        ("idx_orders_purchase_timestamp", ["order_purchase_timestamp"]),
    ],
    "order_items": [
        ("idx_order_items_order_id", ["order_id"]),
        ("idx_order_items_product_id", ["product_id"]),
        ("idx_order_items_seller_id", ["seller_id"]),
    ],
    "order_payments": [
        ("idx_order_payments_order_id", ["order_id"]),
    ],
    "order_reviews": [
        ("idx_order_reviews_order_id", ["order_id"]),
    ],
    "products": [
        ("idx_products_category", ["product_category_name"]),
    ],
}


def quote_identifier(value: str) -> str:
    """Safely quote a SQLite identifier."""
    return '"' + value.replace('"', '""') + '"'


def is_identifier(column: str) -> bool:
    name = column.lower()
    return (
        name.endswith("_id")
        or name.endswith("_zip_code_prefix")
        or name in {"order_id", "customer_id", "product_id", "seller_id"}
    )


def infer_column_type(column: str, values: list[str]) -> str:
    """Infer INTEGER, REAL, or TEXT while preserving identifier strings."""
    if is_identifier(column):
        return "TEXT"

    nonempty = [value.strip() for value in values if value.strip() != ""]
    if not nonempty:
        return "TEXT"

    try:
        for value in nonempty:
            int(value)
        return "INTEGER"
    except ValueError:
        pass

    try:
        for value in nonempty:
            float(value)
        return "REAL"
    except ValueError:
        return "TEXT"


def inspect_csv(path: Path) -> tuple[list[str], list[str], int]:
    """Read a CSV to validate its header and infer its column types."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames

        if not columns or any(not name for name in columns):
            raise ValueError(f"Missing or invalid CSV header: {path.name}")
        if len(columns) != len(set(columns)):
            raise ValueError(f"Duplicate column names in {path.name}")

        values_by_column = {column: [] for column in columns}
        row_count = 0

        for row in reader:
            if None in row:
                raise ValueError(f"Too many fields on row {row_count + 2} of {path.name}")
            for column in columns:
                value = row[column]
                if value is not None:
                    values_by_column[column].append(value)
            row_count += 1

    types = [
        infer_column_type(column, values_by_column[column])
        for column in columns
    ]
    return columns, types, row_count


def load_csv(
    connection: sqlite3.Connection,
    table: str,
    path: Path,
    columns: list[str],
    types: list[str],
) -> int:
    quoted_table = quote_identifier(table)
    column_definitions = ", ".join(
        f"{quote_identifier(column)} {kind}"
        for column, kind in zip(columns, types)
    )
    connection.execute(f"CREATE TABLE {quoted_table} ({column_definitions})")

    placeholders = ", ".join("?" for _ in columns)
    quoted_columns = ", ".join(quote_identifier(column) for column in columns)
    insert_sql = (
        f"INSERT INTO {quoted_table} ({quoted_columns}) "
        f"VALUES ({placeholders})"
    )

    inserted = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        batch = []

        for row in reader:
            batch.append([
                None if row[column] is None or row[column].strip() == ""
                else row[column]
                for column in columns
            ])
            if len(batch) >= 2000:
                connection.executemany(insert_sql, batch)
                inserted += len(batch)
                batch.clear()

        if batch:
            connection.executemany(insert_sql, batch)
            inserted += len(batch)

    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import the Olist CSV dataset into a new SQLite database."
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw",
        help="Directory containing the source CSV files.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "data" / "olist.db",
        help="Output SQLite database path.",
    )
    args = parser.parse_args()

    csv_dir = args.csv_dir.expanduser().resolve()
    database_path = args.database.expanduser().resolve()

    if not csv_dir.is_dir():
        raise SystemExit(f"CSV directory does not exist: {csv_dir}")

    missing = [
        filename for filename in TABLE_FILES.values()
        if not (csv_dir / filename).is_file()
    ]
    if missing:
        raise SystemExit("Missing required CSV files:\n" + "\n".join(missing))

    if database_path.exists():
        raise SystemExit(
            f"Database already exists: {database_path}\n"
            "It was not changed. Choose another --database path to preserve it."
        )

    database_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Source: {csv_dir}")
    print(f"Destination: {database_path}")

    try:
        with sqlite3.connect(database_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")

            for table, filename in TABLE_FILES.items():
                path = csv_dir / filename
                columns, types, expected_rows = inspect_csv(path)
                inserted = load_csv(
                    connection, table, path, columns, types
                )
                if inserted != expected_rows:
                    raise RuntimeError(
                        f"{table}: expected {expected_rows} rows, "
                        f"inserted {inserted}"
                    )

                print(
                    f"{table}: {inserted:,} rows, "
                    f"{len(columns)} columns"
                )

            for table, indexes in INDEXES.items():
                for index_name, columns in indexes:
                    column_sql = ", ".join(
                        quote_identifier(column) for column in columns
                    )
                    connection.execute(
                        f"CREATE INDEX {quote_identifier(index_name)} "
                        f"ON {quote_identifier(table)} ({column_sql})"
                    )

            connection.execute("ANALYZE")

        print("\nDataset import completed successfully.")
        print("Note: no foreign-key constraints were inferred or added.")
    except Exception:
        if database_path.exists():
            database_path.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(database_path) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        raise


if __name__ == "__main__":
    main()
