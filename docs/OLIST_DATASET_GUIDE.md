# Olist Brazilian E-Commerce Dataset — Project Guide

## 1. Why this file exists

This document explains the real-world dataset used by this Text-to-SQL project.
Read it before modifying the database, writing SQL, changing the schema, or
debugging incorrect answers from the language model.

It is intended to be a long-term reference for the project.

## 2. Dataset overview

Dataset: Brazilian E-Commerce Public Dataset by Olist
Source: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

The dataset contains Brazilian e-commerce orders from 2016–2018. It includes
orders, customers, products, sellers, payments, reviews, and product categories.

The current project imports eight CSV files into SQLite.

| Table | Source CSV | Imported rows | Purpose |
|---|---|---:|---|
| customers | olist_customers_dataset.csv | 99,441 | Customer IDs and location |
| order_items | olist_order_items_dataset.csv | 112,650 | Products, sellers, prices, freight |
| order_payments | olist_order_payments_dataset.csv | 103,886 | Payment methods, installments, values |
| order_reviews | olist_order_reviews_dataset.csv | 99,224 | Review scores and comments |
| orders | olist_orders_dataset.csv | 99,441 | Order status and lifecycle timestamps |
| products | olist_products_dataset.csv | 32,951 | Product categories and attributes |
| sellers | olist_sellers_dataset.csv | 3,095 | Seller IDs and location |
| product_category_translation | product_category_name_translation.csv | 71 | Portuguese category names and English translations |

The large geolocation CSV is intentionally not imported in the first version.

## 3. Where files live

Repository: ~/text-to-sql

Raw CSVs:
- data/raw/

Imported SQLite database:
- data/olist.db

Loader:
- scripts/load_olist_dataset.py

Configuration:
- app/core/config.py

Database connection and query execution:
- app/db/database.py

Dynamic schema discovery:
- app/db/schema.py

SQL validation:
- app/services/sql_guardrails.py

SQL generation:
- app/services/sql_generator.py

API:
- app/main.py

The raw CSVs and database are excluded from Git. The loader and this guide
should be committed so another developer can reproduce the import using the
source files.

## 4. Table-by-table understanding

### customers

One row per customer_id in this dataset.

Important columns:
- customer_id: order-specific customer identifier used by orders.
- customer_unique_id: identifier that can associate multiple customer records
  with the same underlying customer.
- customer_zip_code_prefix: partial postal code.
- customer_city: customer city.
- customer_state: Brazilian state abbreviation.

Important:
customer_id and customer_unique_id are not interchangeable. An individual
may have multiple customer_id values across different orders.

### orders

One row per order.

Important columns:
- order_id: order identifier.
- customer_id: customer record associated with the order.
- order_status: status such as delivered, shipped, canceled, or unavailable.
- order_purchase_timestamp: when the order was placed.
- order_approved_at: approval timestamp.
- order_delivered_carrier_date: when the carrier received the order.
- order_delivered_customer_date: when the customer received the order.
- order_estimated_delivery_date: estimated delivery date.

Some timestamps are missing. Missing delivery timestamps do not automatically
mean an order was delivered late; check its status and available dates.

### order_items

One row per item within an order. An order can contain multiple items.

Important columns:
- order_id: associated order.
- order_item_id: item sequence within the order.
- product_id: purchased product.
- seller_id: seller supplying the item.
- shipping_limit_date: shipping deadline.
- price: item price.
- freight_value: freight charged for the item.

An order's item total is generally calculated using SUM(price).
Item total plus freight can be calculated using SUM(price + freight_value).

These measures are not necessarily the same as payment_value.

### order_payments

One row per payment record, not necessarily one row per order.

Important columns:
- order_id
- payment_sequential
- payment_type
- payment_installments
- payment_value

Some orders have multiple payment records. Aggregate payments by order before
joining them to item-level rows, otherwise joins can multiply amounts.

### order_reviews

Review records associated with orders.

Important columns:
- review_id
- order_id
- review_score
- review_comment_title
- review_comment_message
- review_creation_date
- review_answer_timestamp

Review text can be missing even when a review score exists. Use review_score
for numeric rating analysis and account for multiple review rows where relevant.

### products

One row per product identifier.

Important columns:
- product_id
- product_category_name
- product_name_lenght
- product_description_lenght
- product_photos_qty
- product_weight_g
- product_length_cm
- product_height_cm
- product_width_cm

Some source column names contain the spelling "lenght". Preserve the original
names in SQL unless the database schema is deliberately migrated.

Product attributes can be missing.

### sellers

One row per seller identifier.

Important columns:
- seller_id
- seller_zip_code_prefix
- seller_city
- seller_state

A seller can supply many order items.

### product_category_translation

Maps product_category_name to product_category_name_english.

Use this table to display English category labels when a translation is available.
It does not contain every possible product attribute.

## 5. Relationships

Logical joins:

- customers.customer_id = orders.customer_id
- orders.order_id = order_items.order_id
- orders.order_id = order_payments.order_id
- orders.order_id = order_reviews.order_id
- order_items.product_id = products.product_id
- order_items.seller_id = sellers.seller_id
- products.product_category_name =
  product_category_translation.product_category_name

These are logical relationships; the loader does not add foreign-key constraints.
Validate assumptions against the data before relying on them.

### Important join cardinalities

- One order can have multiple order_items rows.
- One order can have multiple order_payments rows.
- One order can have multiple order_reviews rows.
- One product can appear in many order_items rows.
- One seller can supply many order_items rows.
- One customer record can be associated with many orders.

Joining multiple one-to-many tables directly can multiply rows and inflate
revenue, payment totals, or review counts.

## 6. Common analytical pitfalls

### Pitfall A: Inflated revenue

Do not directly join order_items and order_payments and then sum both price
and payment_value. Multiple items and multiple payments can multiply rows.

For item sales, aggregate order_items first:

SELECT order_id, SUM(price) AS item_sales
FROM order_items
GROUP BY order_id;

For payments, aggregate order_payments independently:

SELECT order_id, SUM(payment_value) AS total_payments
FROM order_payments
GROUP BY order_id;

Then join the aggregated results by order_id if both measures are needed.

### Pitfall B: Confusing item sales, freight, and payments

- SUM(order_items.price): item-price total.
- SUM(order_items.freight_value): freight total.
- SUM(order_items.price + order_items.freight_value): item price plus freight.
- SUM(order_payments.payment_value): recorded payment total.

State which metric a question asks for. Do not label these measures
interchangeably.

### Pitfall C: Counting customers

COUNT(DISTINCT customer_id) counts customer records.
COUNT(DISTINCT customer_unique_id) counts unique customer identities represented
by the customer table.

Use the metric that matches the business question.

### Pitfall D: Delivery performance

Compare order_delivered_customer_date with order_estimated_delivery_date only
when both timestamps are available. A delivered order received after its
estimated date is late by this definition.

Do not treat every missing delivery timestamp as a late delivery.

### Pitfall E: Missing values

Empty CSV fields are loaded as SQL NULL. Use IS NULL or IS NOT NULL to check
them. Comparisons such as column = NULL are incorrect SQL.

### Pitfall F: Product category names

The products table contains the original category name. Join the translation
table when English labels are required. A missing category or translation
should not automatically cause the product to be discarded.

## 7. Example business questions

1. How many orders were placed each month?
2. Which product categories have the highest item sales?
3. What are the most frequently purchased products?
4. What is the average review score by product category?
5. Which delivered orders arrived after the estimated delivery date?
6. Which payment types are used most often?
7. Which sellers have the highest item sales?
8. How many distinct customer identities placed orders?
9. What is the average freight value per order?
10. How many orders have each order_status?

These questions test aggregation, filtering, joins, dates, sorting, and
distinct counts. Verify generated SQL before trusting a business conclusion.

## 8. Useful SQL examples

### Count orders by status

SELECT order_status, COUNT(*) AS order_count
FROM orders
GROUP BY order_status
ORDER BY order_count DESC;

### Monthly order volume

SELECT
    substr(order_purchase_timestamp, 1, 7) AS purchase_month,
    COUNT(*) AS order_count
FROM orders
WHERE order_purchase_timestamp IS NOT NULL
GROUP BY substr(order_purchase_timestamp, 1, 7)
ORDER BY purchase_month;

### Top product categories by item sales

SELECT
    COALESCE(t.product_category_name_english,
             p.product_category_name,
             'unknown') AS category,
    SUM(oi.price) AS item_sales
FROM order_items AS oi
JOIN products AS p ON p.product_id = oi.product_id
LEFT JOIN product_category_translation AS t
    ON t.product_category_name = p.product_category_name
GROUP BY category
ORDER BY item_sales DESC
LIMIT 10;

### Average review score by category

SELECT
    COALESCE(t.product_category_name_english,
             p.product_category_name,
             'unknown') AS category,
    AVG(r.review_score) AS average_review_score,
    COUNT(r.review_score) AS review_count
FROM order_reviews AS r
JOIN order_items AS oi ON oi.order_id = r.order_id
JOIN products AS p ON p.product_id = oi.product_id
LEFT JOIN product_category_translation AS t
    ON t.product_category_name = p.product_category_name
GROUP BY category
ORDER BY average_review_score DESC;

Note: an order can contain multiple items and reviews. This query associates
an order's review with every category in that order, so it is not a product-level
review attribution. Interpret the result accordingly.

### Delivered orders that arrived late

SELECT
    order_id,
    order_delivered_customer_date,
    order_estimated_delivery_date
FROM orders
WHERE order_status = 'delivered'
  AND order_delivered_customer_date IS NOT NULL
  AND order_estimated_delivery_date IS NOT NULL
  AND order_delivered_customer_date > order_estimated_delivery_date
ORDER BY order_delivered_customer_date DESC
LIMIT 100;

## 9. Rebuild the database

Activate the project's virtual environment if it is not already active:

cd ~/text-to-sql
source .venv/bin/activate

Check that the eight source CSVs exist:

find data/raw -maxdepth 1 -type f -name '*.csv' | sort

Build a new database:

python scripts/load_olist_dataset.py

The loader refuses to overwrite an existing database. To rebuild, choose a new
output path explicitly, or back up and intentionally remove the old database
after confirming it is safe to do so:

python scripts/load_olist_dataset.py --database data/olist-rebuilt.db

The default output is data/olist.db. The app's current default configuration
still points to data/demo.db; switching the app to the Olist database is a
separate step.

## 10. Git and data safety

Raw CSVs and SQLite database files must not be committed to Git. The repository
should contain the loader, tests, and this documentation, not the full dataset.

Check ignore rules with:

git check-ignore data/raw/olist_orders_dataset.csv
git check-ignore data/olist.db

Before committing:

git status --short

The dataset is published on Kaggle under the Olist Brazilian E-Commerce Public
Dataset listing. Review the source's current license and terms before using the
data outside learning, research, or other permitted non-commercial purposes.
The commonly listed license is CC BY-NC-SA 4.0.

## 11. Project status and next steps

Current status:
- Eight CSV files copied to data/raw/.
- data/raw/ is ignored by Git.
- scripts/load_olist_dataset.py imports eight tables.
- data/olist.db was created successfully.
- Imported row counts match the source CSV counts.
- The application still defaults to data/demo.db.
- Foreign-key constraints have not been added to the imported tables.

Next:
1. Test the loader's validation and failure behavior.
2. Add automated tests for the loader.
3. Verify schema discovery against data/olist.db.
4. Switch the application to the Olist database safely.
5. Run the existing test suite and add real-data SQL tests.
6. Commit and push each verified step.
