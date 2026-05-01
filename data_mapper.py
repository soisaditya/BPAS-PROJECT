import os
import sqlite3
import pandas as pd
from database import get_db_connection, init_db

DATA_DIR = "data"


def load_and_map_data(paths=None):
    """
    Ingest CSV files into SQLite.
    paths: dict with keys 'orders','payments','order_items','products','customers','reviews'
           If None, fall back to the default data/ directory.
    """
    print("Initializing database...")
    init_db()
    conn = get_db_connection()

    def get_path(key, default_name):
        if paths and key in paths and paths[key]:
            return paths[key]
        return os.path.join(DATA_DIR, default_name)

    print("Loading datasets...")
    try:
        orders_df    = pd.read_csv(get_path('orders',      'olist_orders_dataset.csv'))
        payments_df  = pd.read_csv(get_path('payments',    'olist_order_payments_dataset.csv'))
        items_df     = pd.read_csv(get_path('order_items', 'olist_order_items_dataset.csv'))
        products_df  = pd.read_csv(get_path('products',    'olist_products_dataset.csv'))
        customers_df = pd.read_csv(get_path('customers',   'olist_customers_dataset.csv'))
        reviews_path = get_path('reviews', 'olist_order_reviews_dataset.csv')
        reviews_df   = pd.read_csv(reviews_path) if os.path.exists(reviews_path) else None
    except FileNotFoundError as e:
        raise RuntimeError(f"Could not find data file: {e}")

    # 1. Orders
    print("Processing Orders...")
    mapped_orders = orders_df[[
        'order_id', 'customer_id', 'order_status',
        'order_purchase_timestamp', 'order_delivered_customer_date',
        'order_estimated_delivery_date'
    ]].copy()
    mapped_orders.rename(columns={
        'order_status': 'status',
        'order_purchase_timestamp': 'purchase_timestamp',
        'order_delivered_customer_date': 'delivered_date',
        'order_estimated_delivery_date': 'estimated_date'
    }, inplace=True)
    mapped_orders.to_sql('orders', conn, if_exists='append', index=False)

    # 2. Transactions
    print("Processing Transactions...")
    payments_df[['order_id', 'payment_type', 'payment_value']].to_sql(
        'transactions', conn, if_exists='append', index=False
    )

    # 3. Products (Items + Products)
    print("Processing Products...")
    merged = pd.merge(items_df, products_df, on='product_id', how='left')
    mapped_products = merged[['order_id', 'product_id', 'product_category_name', 'price']].copy()
    mapped_products.rename(columns={'product_category_name': 'category'}, inplace=True)
    mapped_products['category'] = mapped_products['category'].fillna('unknown')
    mapped_products.to_sql('products', conn, if_exists='append', index=False)

    # 4. Geographics
    print("Processing Geographics...")
    mapped_geo = customers_df[['customer_id', 'customer_state', 'customer_city']].copy()
    mapped_geo.rename(columns={'customer_state': 'state', 'customer_city': 'city'}, inplace=True)
    mapped_geo.to_sql('geographics', conn, if_exists='append', index=False)

    # 5. Reviews (optional)
    if reviews_df is not None:
        print("Processing Reviews...")
        reviews_df[['order_id', 'review_score']].to_sql(
            'reviews', conn, if_exists='append', index=False
        )

    conn.close()
    print("Data ingestion complete!")


def load_from_excel(filepath):
    """
    Ingest a single Excel (.xlsx) file into SQLite.
    Expected sheets: orders, payments, order_items, products, customers, reviews (optional).
    Sheet names are matched case-insensitively and with common variations.
    """
    print("Initializing database...")
    init_db()
    conn = get_db_connection()

    # Read all sheets
    xl = pd.ExcelFile(filepath, engine='openpyxl')
    sheet_names = xl.sheet_names
    print(f"Found sheets: {sheet_names}")

    # Flexible sheet name matching
    SHEET_ALIASES = {
        'orders':     ['orders', 'order'],
        'payments':   ['payments', 'payment'],
        'order_items':['order_items', 'order items', 'orderitems', 'items', 'order_item'],
        'products':   ['products', 'product'],
        'customers':  ['customers', 'customer'],
        'reviews':    ['reviews', 'review'],
    }

    def find_sheet(key):
        aliases = SHEET_ALIASES.get(key, [key])
        for sheet in sheet_names:
            if sheet.strip().lower() in aliases:
                return sheet
        return None

    # Load required sheets
    required = ['orders', 'payments', 'order_items', 'products', 'customers']
    dfs = {}
    for key in required:
        sheet = find_sheet(key)
        if not sheet:
            raise RuntimeError(
                f"Missing required sheet '{key}'. "
                f"Found sheets: {sheet_names}. "
                f"Expected one of: {SHEET_ALIASES[key]}"
            )
        dfs[key] = pd.read_excel(xl, sheet_name=sheet)
        print(f"  Loaded sheet '{sheet}' → {len(dfs[key])} rows")

    # Optional reviews
    reviews_sheet = find_sheet('reviews')
    reviews_df = pd.read_excel(xl, sheet_name=reviews_sheet) if reviews_sheet else None
    if reviews_df is not None:
        print(f"  Loaded sheet '{reviews_sheet}' → {len(reviews_df)} rows")

    orders_df    = dfs['orders']
    payments_df  = dfs['payments']
    items_df     = dfs['order_items']
    products_df  = dfs['products']
    customers_df = dfs['customers']

    # 1. Orders
    print("Processing Orders...")
    mapped_orders = orders_df[[
        'order_id', 'customer_id', 'order_status',
        'order_purchase_timestamp', 'order_delivered_customer_date',
        'order_estimated_delivery_date'
    ]].copy()
    mapped_orders.rename(columns={
        'order_status': 'status',
        'order_purchase_timestamp': 'purchase_timestamp',
        'order_delivered_customer_date': 'delivered_date',
        'order_estimated_delivery_date': 'estimated_date'
    }, inplace=True)
    mapped_orders.to_sql('orders', conn, if_exists='append', index=False)

    # 2. Transactions
    print("Processing Transactions...")
    payments_df[['order_id', 'payment_type', 'payment_value']].to_sql(
        'transactions', conn, if_exists='append', index=False
    )

    # 3. Products (Items + Products)
    print("Processing Products...")
    merged = pd.merge(items_df, products_df, on='product_id', how='left')
    mapped_products = merged[['order_id', 'product_id', 'product_category_name', 'price']].copy()
    mapped_products.rename(columns={'product_category_name': 'category'}, inplace=True)
    mapped_products['category'] = mapped_products['category'].fillna('unknown')
    mapped_products.to_sql('products', conn, if_exists='append', index=False)

    # 4. Geographics
    print("Processing Geographics...")
    mapped_geo = customers_df[['customer_id', 'customer_state', 'customer_city']].copy()
    mapped_geo.rename(columns={'customer_state': 'state', 'customer_city': 'city'}, inplace=True)
    mapped_geo.to_sql('geographics', conn, if_exists='append', index=False)

    # 5. Reviews (optional)
    if reviews_df is not None:
        print("Processing Reviews...")
        reviews_df[['order_id', 'review_score']].to_sql(
            'reviews', conn, if_exists='append', index=False
        )

    conn.close()
    print("Excel data ingestion complete!")


if __name__ == "__main__":
    load_and_map_data()
