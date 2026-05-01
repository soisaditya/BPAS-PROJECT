from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from database import get_db_connection, init_db
from data_mapper import load_and_map_data, load_from_excel
import os

app = Flask(__name__)
app.secret_key = 'bpas-secret-key-change-in-production'

# ---- Auth decorator ----
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access the dashboard.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ---- Auth Routes ----

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password. Please try again.', 'error')

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not name or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('signup.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('signup.html')

        conn = get_db_connection()
        existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            conn.close()
            flash('An account with this email already exists.', 'error')
            return render_template('signup.html')

        hashed = generate_password_hash(password)
        conn.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, hashed))
        conn.commit()
        conn.close()

        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# ---- Dashboard & Upload Views ----

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        upload_mode = request.form.get('upload_mode', 'csv')

        try:
            if upload_mode == 'excel':
                # Single Excel file upload
                excel_file = request.files.get('excel_file')
                if not excel_file or excel_file.filename == '':
                    flash('Please select an Excel file to upload.', 'error')
                    return render_template('upload.html')

                filename = secure_filename(excel_file.filename)
                if not filename.lower().endswith(('.xlsx', '.xls')):
                    flash('Please upload a valid Excel file (.xlsx or .xls).', 'error')
                    return render_template('upload.html')

                save_path = os.path.join(UPLOAD_FOLDER, filename)
                excel_file.save(save_path)
                load_from_excel(save_path)
                flash('Excel dataset uploaded and processed successfully!', 'success')
                return redirect(url_for('dashboard'))

            else:
                # Multiple CSV files upload
                file_keys = ['orders', 'payments', 'order_items', 'products', 'customers']
                paths = {}

                for key in file_keys:
                    f = request.files.get(key)
                    if not f or f.filename == '':
                        flash(f'Missing required file: {key}', 'error')
                        return render_template('upload.html')
                    filename = secure_filename(f.filename)
                    save_path = os.path.join(UPLOAD_FOLDER, filename)
                    f.save(save_path)
                    paths[key] = save_path

                # Optional reviews file
                reviews_file = request.files.get('reviews')
                if reviews_file and reviews_file.filename != '':
                    filename = secure_filename(reviews_file.filename)
                    save_path = os.path.join(UPLOAD_FOLDER, filename)
                    reviews_file.save(save_path)
                    paths['reviews'] = save_path

                load_and_map_data(paths)
                flash('Dataset uploaded and processed successfully!', 'success')
                return redirect(url_for('dashboard'))

        except Exception as e:
            flash(f'Error processing dataset: {str(e)}', 'error')
            return render_template('upload.html')

    return render_template('upload.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# ---- API Endpoints ----

@app.route('/api/kpi/revenue_growth')
@login_required
def revenue_growth():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT strftime('%Y-%m', o.purchase_timestamp) as month, SUM(t.payment_value) as revenue
        FROM orders o
        JOIN transactions t ON o.order_id = t.order_id
        WHERE o.purchase_timestamp IS NOT NULL
        GROUP BY month
        ORDER BY month
    ''')
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/api/kpi/category_profitability')
@login_required
def category_profitability():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT category, SUM(price) as total_revenue
        FROM products
        WHERE category != 'unknown'
        GROUP BY category
        ORDER BY total_revenue DESC
        LIMIT 10
    ''')
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/api/kpi/aov')
@login_required
def aov():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT SUM(payment_value) / COUNT(DISTINCT order_id) as aov
        FROM transactions
    ''')
    result = cursor.fetchone()
    conn.close()
    return jsonify({"aov": result['aov'] if result['aov'] else 0})

@app.route('/api/kpi/logistics_delta')
@login_required
def logistics_delta():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT AVG(julianday(delivered_date) - julianday(estimated_date)) as avg_delta_days
        FROM orders
        WHERE delivered_date IS NOT NULL AND estimated_date IS NOT NULL AND status = 'delivered'
    ''')
    result = cursor.fetchone()
    conn.close()
    return jsonify({"avg_delta_days": result['avg_delta_days'] if result['avg_delta_days'] else 0})

@app.route('/api/kpi/geographic_spend')
@login_required
def geographic_spend():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT g.state, SUM(t.payment_value) as total_spend
        FROM geographics g
        JOIN orders o ON g.customer_id = o.customer_id
        JOIN transactions t ON o.order_id = t.order_id
        GROUP BY g.state
        ORDER BY total_spend DESC
    ''')
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/api/kpi/order_health')
@login_required
def order_health():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT status, COUNT(*) as count
        FROM orders
        GROUP BY status
    ''')
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/api/kpi/review_vs_price')
@login_required
def review_vs_price():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.review_score, AVG(p.price) as avg_price
        FROM reviews r
        JOIN products p ON r.order_id = p.order_id
        GROUP BY r.review_score
        ORDER BY r.review_score
    ''')
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/api/kpi/payment_distribution')
@login_required
def payment_distribution():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT payment_type, COUNT(*) as count, SUM(payment_value) as total_value
        FROM transactions
        GROUP BY payment_type
    ''')
    data = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(data)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
