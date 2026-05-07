from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import mysql.connector
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
import os
import requests 
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timedelta
import random
import uuid

# --- CẤU HÌNH ---
load_dotenv()
app = Flask(__name__)
app.secret_key = 'hmart_bookstore_ai_secret_key_2026'

# --- KẾT NỐI DATABASE ---
def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASS", ""),
        database=os.getenv("DB_NAME", "bookstore"),
        port=int(os.getenv("DB_PORT", 3306))
    )

# --- CẤU HÌNH CHROMADB (AI VECTOR) ---
try:
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    collection = chroma_client.get_or_create_collection(name="books_search", embedding_function=ef)
except Exception as e:
    print(f"⚠️ Cảnh báo: Lỗi ChromaDB - {e}")

# --- MIDDLEWARE KIỂM TRA QUYỀN ADMIN ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Bạn không có quyền truy cập trang này!", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# --- CONTEXT PROCESSOR ---
@app.context_processor
def inject_global_data():
    data = {'category_tree': [], 'notifications': [], 'unread_count': 0, 'cart_count': 0}
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM categories")
        data['category_tree'] = cursor.fetchall()
        
        if 'user_id' in session:
            cursor.execute("SELECT id, content, `read` FROM notifications WHERE user_id = %s ORDER BY id DESC LIMIT 10", (session['user_id'],))
            data['notifications'] = cursor.fetchall()
            
            cursor.execute("SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND `read` = 0", (session['user_id'],))
            data['unread_count'] = cursor.fetchone()['count']
            
            # ĐÃ BỔ SUNG: Tính tổng số lượng trong Giỏ Hàng từ DB
            cursor.execute("SELECT SUM(quantity) as total_qty FROM carts WHERE user_id = %s", (session['user_id'],))
            qty_res = cursor.fetchone()
            data['cart_count'] = int(qty_res['total_qty']) if qty_res and qty_res['total_qty'] else 0
            
        conn.close()
    except Exception as e:
        print("Lỗi load context:", e)
    return data

# HÀM HỖ TRỢ XỬ LÝ LỌC THEO GIÁ
def get_price_condition(price_filter):
    if price_filter == 'under_50': return " AND p.sale_price < 50000"
    elif price_filter == '50_100': return " AND p.sale_price BETWEEN 50000 AND 100000"
    elif price_filter == '100_200': return " AND p.sale_price BETWEEN 100000 AND 200000"
    elif price_filter == 'over_200': return " AND p.sale_price > 200000"
    return ""

# =========================================================
# 1. HỆ THỐNG TÀI KHOẢN
# =========================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        user_name = request.form.get('username', '').strip()
        
        if confirm_password and password != confirm_password:
            flash('Mật khẩu xác nhận không khớp!', 'danger')
            return render_template('register.html')
            
        if not user_name or not email or not password:
            flash('Vui lòng nhập đầy đủ thông tin!', 'danger')
            return render_template('register.html')
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE email = %s OR user_name = %s", (email, user_name))
        if cursor.fetchone():
            flash('Email hoặc Tên đăng nhập này đã được sử dụng!', 'danger')
            conn.close()
            return render_template('register.html')
        
        hashed_pw = generate_password_hash(password)
        new_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO users (id, role_id, user_name, email, password, full_name, deleted) 
            VALUES (%s, 'R02', %s, %s, %s, %s, 0)
        """, (new_id, user_name, email, hashed_pw, full_name if full_name else user_name))
        conn.commit()
        conn.close()
        flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_id = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.*, r.role_name FROM users u 
            LEFT JOIN roles r ON u.role_id = r.id 
            WHERE (u.email = %s OR u.user_name = %s) AND u.deleted = 0
        """, (login_id, login_id))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['role'] = 'admin' if user['role_id'] == 'R01' else 'customer'
            flash('Đăng nhập thành công!', 'success')
            if session['role'] == 'admin': 
                return redirect('/admin/dashboard')
            return redirect(url_for('index'))
            
        flash('Sai Email/Tên tài khoản hoặc mật khẩu!', 'danger')
    return render_template('login.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user_name = request.form.get('user_name', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if new_password != confirm_password:
            flash('Mật khẩu xác nhận không khớp!', 'danger')
            return redirect(url_for('forgot_password'))

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id FROM users 
            WHERE email = %s AND user_name = %s AND deleted = 0
        """, (email, user_name))
        user = cursor.fetchone()

        if user:
            hashed_pw = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_pw, user['id']))
            conn.commit()
            flash('Khôi phục mật khẩu thành công! Vui lòng đăng nhập với mật khẩu mới.', 'success')
            conn.close()
            return redirect(url_for('login'))
        else:
            flash('Tên tài khoản hoặc Email không chính xác!', 'danger')
            conn.close()
            return redirect(url_for('forgot_password'))

    return render_template('forgot_password.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Đã đăng xuất.', 'info')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        phone = request.form.get('phone_number')
        dob = request.form.get('dob') or None
        address = request.form.get('address')
        
        image_path = None
        if 'avatar_file' in request.files:
            file = request.files['avatar_file']
            if file and file.filename != '':
                upload_folder = os.path.join('static', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                filename = secure_filename(f"{session['user_id']}_{file.filename}")
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                image_path = f"/{filepath}".replace("\\", "/")

        try:
            if image_path:
                cursor.execute("""
                    UPDATE users 
                    SET full_name=%s, email=%s, phone_number=%s, date_of_birth=%s, address=%s, image=%s 
                    WHERE id=%s
                """, (full_name, email, phone, dob, address, image_path, session['user_id']))
            else:
                cursor.execute("""
                    UPDATE users 
                    SET full_name=%s, email=%s, phone_number=%s, date_of_birth=%s, address=%s 
                    WHERE id=%s
                """, (full_name, email, phone, dob, address, session['user_id']))
                
            conn.commit()
            session['user_name'] = full_name
            flash('Cập nhật thông tin cá nhân thành công!', 'success')
        except Exception as e:
            print(f"Lỗi cập nhật profile: {e}")
            flash('Có lỗi xảy ra khi cập nhật!', 'danger')
            
    cursor.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    return render_template('profile.html', user=user)

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('Mật khẩu mới và xác nhận không khớp!', 'danger')
            return redirect('/change-password')
            
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password FROM users WHERE id = %s", (session['user_id'],))
        user = cursor.fetchone()
        
        if user and check_password_hash(user['password'], old_password):
            hashed_pw = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_pw, session['user_id']))
            conn.commit()
            flash('Đổi mật khẩu thành công!', 'success')
        else:
            flash('Mật khẩu hiện tại không đúng!', 'danger')
        conn.close()
        return redirect('/change-password')
        
    return render_template('change_password.html')

# =========================================================
# 2. GIAO DIỆN KHÁCH HÀNG & LỌC GIÁ SÁCH
# =========================================================

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 8
    offset = (page - 1) * per_page
    price_filter = request.args.get('price', '')
    price_cond = get_price_condition(price_filter)
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute(f"SELECT COUNT(*) as total FROM products p WHERE p.deleted = 0 {price_cond}")
    total_books = cursor.fetchone()['total']
    total_pages = (total_books + per_page - 1) // per_page

    cursor.execute(f"""
        SELECT p.id, p.title, p.sale_price as price, p.origin_price,
               (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url
        FROM products p WHERE p.deleted = 0 {price_cond} ORDER BY p.id DESC LIMIT %s OFFSET %s
    """, (per_page, offset))
    books = cursor.fetchall()
    
    cursor.execute("""
        SELECT g.image, g.product_id, p.title 
        FROM galeries g LEFT JOIN products p ON g.product_id = p.id
    """)
    galeries = cursor.fetchall()
    conn.close()
    
    for b in books: b['price'] = float(b['price']) if b['price'] else 0
    return render_template('index.html', books=books, page=page, total_pages=total_pages, galeries=galeries)

@app.route('/book/<string:book_id>')
def book_detail(book_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Lấy thông tin sách
    cursor.execute("""
        SELECT p.*, p.sale_price as price, c.name as category_name
        FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.id = %s AND p.deleted = 0
    """, (book_id,))
    book = cursor.fetchone()

    if not book:
        conn.close()
        return "Không tìm thấy sản phẩm", 404
    book['price'] = float(book['price']) if book['price'] else 0

    # 2. LẤY DANH SÁCH TOÀN BỘ ẢNH (BẮT BUỘC PHẢI CÓ ĐOẠN NÀY ĐỂ HIỆN ẢNH NHỎ)
    cursor.execute("SELECT url FROM image_product WHERE product_id = %s", (book_id,))
    images = cursor.fetchall()
    
    # Gán ảnh đầu tiên làm ảnh đại diện chính
    book['image_url'] = images[0]['url'] if images else "https://via.placeholder.com/300x400"

    # 3. Sách liên quan
    cursor.execute("""
        SELECT p.id, p.title, p.sale_price as price,
               (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url
        FROM products p WHERE p.category_id = %s AND p.id != %s AND p.deleted = 0 LIMIT 4
    """, (book['category_id'], book_id))
    related_books = cursor.fetchall()

    # 4. Lấy đánh giá
    feedbacks = []
    try:
        cursor.execute("""
            SELECT f.*, u.full_name, u.image as avatar_url 
            FROM feedbacks f 
            JOIN users u ON f.user_id = u.id 
            WHERE f.product_id = %s 
            ORDER BY f.id DESC
        """, (book_id,))
        feedbacks = cursor.fetchall()
    except Exception as e:
        print(f"Lỗi truy xuất đánh giá: {e}")

    conn.close()
    
    for b in related_books: b['price'] = float(b['price']) if b['price'] else 0
    
    # TRUYỀN THÊM BIẾN `images=images` XUỐNG DƯỚI NÀY
    return render_template('product.html', book=book, images=images, related_books=related_books, feedbacks=feedbacks)

@app.route('/search')
def search_book():
    query = request.args.get('keyword', '').strip()
    if not query: return redirect('/')
    
    price_filter = request.args.get('price', '')
    price_cond = get_price_condition(price_filter)
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    search_term = f"%{query}%"
    cursor.execute(f"""
        SELECT p.id, p.title, p.sale_price as price, p.origin_price,
               (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url
        FROM products p WHERE (p.title LIKE %s OR p.description LIKE %s) AND p.deleted = 0 {price_cond}
    """, (search_term, search_term))
    books = cursor.fetchall()
    conn.close()
    
    for b in books: b['price'] = float(b['price']) if b['price'] else 0
    return render_template('index.html', books=books, page_title=f"🔍 Kết quả tìm kiếm: '{query}'")

@app.route('/category/<string:cat_id>')
def category_books(cat_id):
    price_filter = request.args.get('price', '')
    price_cond = get_price_condition(price_filter)
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name FROM categories WHERE id = %s", (cat_id,))
    cat_info = cursor.fetchone()
    cat_name = cat_info['name'] if cat_info else "Danh mục"
    
    cursor.execute(f"""
        SELECT p.id, p.title, p.sale_price as price, p.origin_price,
               (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url
        FROM products p WHERE p.category_id = %s AND p.deleted = 0 {price_cond}
    """, (cat_id,))
    books = cursor.fetchall()
    conn.close()
    
    for b in books: b['price'] = float(b['price']) if b['price'] else 0
    return render_template('index.html', books=books, page_title=f"Danh mục: {cat_name}")

# =========================================================
# 3. CHATBOT AI OFFLINE
# =========================================================
@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        user_msg = request.json.get('message')
        results = collection.query(query_texts=[user_msg], n_results=2)
        found_books = []
        context = ""
        
        if results['ids'] and results['ids'][0]:
            found_ids = results['ids'][0]
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            fmt = ','.join(['%s'] * len(found_ids))
            
            cursor.execute(f"""
                SELECT p.id, p.title, p.sale_price as price, p.description, c.name as category_name,
                       (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url
                FROM products p 
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE p.id IN ({fmt}) AND p.deleted = 0
            """, tuple(found_ids))
            found_books = cursor.fetchall()
            conn.close()

            context_list = []
            for b in found_books:
                b['price'] = float(b['price']) if b['price'] else 0
                cat_name = b['category_name'] or 'Chưa phân loại'
                context_list.append(f"- Tên sách: {b['title']} (Thể loại: {cat_name}). Giá: {b['price']:,.0f}đ. Nội dung: {b['description']}")
            context = "\n".join(context_list)

        prompt = f"""Bạn là nhân viên tư vấn bán hàng của nhà sách. Khách hỏi: "{user_msg}"
        Dữ liệu kho sách hiện tại: 
        {context}
        
        Quy tắc BẮT BUỘC: 
        1. NẾU CÓ dữ liệu kho ở trên, BẮT BUỘC phải dựa vào đó để giới thiệu cho khách.
        2. Trả lời tự nhiên, ngắn gọn, thân thiện bằng tiếng Việt."""
        
        response = requests.post("http://localhost:11434/api/generate", 
                               json={"model": "qwen2:1.5b", "prompt": prompt, "stream": False})
        
        if response.status_code == 200:
            ai_reply = response.json().get("response", "Tôi chưa hiểu ý bạn.")
            return jsonify({"response": ai_reply, "books": found_books})
        else:
            return jsonify({"response": "Lỗi kết nối với AI cục bộ.", "books": []})
    except Exception as e:
        return jsonify({"response": "Hệ thống AI Offline đang tắt, vui lòng bật Ollama.", "books": []})

# =========================================================
# 4. GIỎ HÀNG, THANH TOÁN & ĐƠN HÀNG
# =========================================================

@app.route('/cart')
def cart_page():
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập để xem giỏ hàng!', 'warning')
        return redirect(url_for('login'))
    return render_template('cart.html')

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({'success': False, 'redirect': '/login', 'message': 'Vui lòng đăng nhập!'})

    try:
        data = request.json
        product_id = str(data.get('book_id'))
        quantity = int(data.get('quantity', 1))
        user_id = session['user_id']

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM carts WHERE user_id = %s AND product_id = %s", (user_id, product_id))
        item = cursor.fetchone()

        if item:
            cursor.execute("UPDATE carts SET quantity = quantity + %s WHERE id = %s", (quantity, item['id']))
        else:
            cursor.execute("INSERT INTO carts (id, user_id, product_id, quantity) VALUES (%s, %s, %s, %s)",
                           (str(uuid.uuid4()), user_id, product_id, quantity))
        conn.commit()

        cursor.execute("SELECT SUM(quantity) as total FROM carts WHERE user_id = %s", (user_id,))
        total_qty = cursor.fetchone()['total'] or 0
        conn.close()

        return jsonify({'success': True, 'cart_count': int(total_qty)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/cart-details', methods=['POST'])
def get_cart_details():
    if 'user_id' not in session: return jsonify([])
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.product_id as id, c.quantity, p.title, p.sale_price as price,
                   (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url
            FROM carts c JOIN products p ON c.product_id = p.id WHERE c.user_id = %s
        """, (session['user_id'],))
        items = cursor.fetchall()
        conn.close()

        results = []
        for item in items:
            item['price'] = float(item['price']) if item['price'] else 0
            item['total'] = item['price'] * item['quantity']
            item['author'] = "Sản phẩm BookStore"
            results.append(item)
        return jsonify(results)
    except:
        return jsonify([])

@app.route('/api/update-cart', methods=['POST'])
def update_cart():
    if 'user_id' not in session: return jsonify({'success': False})
    data = request.json
    product_id, action = str(data.get('book_id')), data.get('action')
    user_id = session['user_id']

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, quantity FROM carts WHERE user_id = %s AND product_id = %s", (user_id, product_id))
    item = cursor.fetchone()

    if item:
        if action == 'increase':
            cursor.execute("UPDATE carts SET quantity = quantity + 1 WHERE id = %s", (item['id'],))
        elif action == 'decrease':
            if item['quantity'] > 1:
                cursor.execute("UPDATE carts SET quantity = quantity - 1 WHERE id = %s", (item['id'],))
            else:
                cursor.execute("DELETE FROM carts WHERE id = %s", (item['id'],))
        elif action == 'remove':
            cursor.execute("DELETE FROM carts WHERE id = %s", (item['id'],))
        conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/checkout')
def checkout_page():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    return render_template('checkout.html', user=user)

@app.route('/api/apply-coupon', methods=['POST'])
def apply_coupon():
    data = request.json
    code = data.get('code', '').strip().upper()
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM coupons 
        WHERE code = %s AND expired = 0 AND quantity > 0 
        AND expiration_date >= NOW()
    """, (code,))
    coupon = cursor.fetchone()
    conn.close()
    
    if coupon:
        return jsonify({
            'success': True, 
            'discount_percent': float(coupon['discount'])
        })
    else:
        return jsonify({'success': False, 'message': 'Mã không hợp lệ hoặc đã hết hạn.'})

@app.route('/api/save-order', methods=['POST'])
def save_order():
    if 'user_id' not in session: return jsonify({"success": False})
    data = request.json
    conn = get_db(); cursor = conn.cursor()
    order_id = str(uuid.uuid4())
    
    # LẤY HÌNH THỨC THANH TOÁN TỪ GIAO DIỆN (Nếu không có thì mặc định là cod)
    payment_method = data.get('payment_method', 'cod')
    
    # ĐƯA payment_method VÀO CÂU LỆNH INSERT
    cursor.execute("""
        INSERT INTO orders (id, user_id, full_name, phone_number, address, total_money, status, coupon_code, payment_method) 
        VALUES (%s, %s, %s, %s, %s, %s, 'Chờ xác nhận', %s, %s)
    """, (order_id, session['user_id'], data['name'], data['phone'], data['address'], data['total'], data.get('coupon_code'), payment_method))
    
    for item in data['items']:
        cursor.execute("""
            INSERT INTO order_detail (id, order_id, product_id, price, quantity, total_money) 
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (str(uuid.uuid4()), order_id, item['id'], item['price'], item['quantity'], float(item['price']) * int(item['quantity'])))
        
    cursor.execute("DELETE FROM carts WHERE user_id = %s", (session['user_id'],))
    conn.commit(); conn.close()
    
    return jsonify({"success": True, "order_id": order_id})

@app.route('/order-history')
def order_history():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY orderDate DESC", (session['user_id'],))
    orders = cursor.fetchall()
    
    for order in orders:
        order['total_amount'] = float(order['total_money']) if order['total_money'] else 0
        order['customer_name'] = order.get('full_name', 'Khách hàng')
        order['phone'] = order.get('phone_number', '')
        
        if order.get('orderDate'):
            order['created_at'] = order['orderDate'].strftime('%d/%m/%Y %H:%M') if hasattr(order['orderDate'], 'strftime') else order['orderDate']
        else:
            order['created_at'] = ''

        cursor.execute("""
            SELECT od.quantity, od.price, p.title as book_title 
            FROM order_detail od
            JOIN products p ON od.product_id = p.id
            WHERE od.order_id = %s
        """, (order['id'],))
        items = cursor.fetchall()
        
        for item in items: 
            item['price'] = float(item['price']) if item['price'] else 0
            item['quantity'] = int(item['quantity']) if item['quantity'] else 1
            
        order['details'] = items
        
    conn.close()
    return render_template('history.html', orders=orders)

@app.route('/order/<string:order_id>')
def order_detail(order_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, session['user_id']))
    order = cursor.fetchone()
    if not order: 
        conn.close()
        flash('Không tìm thấy đơn hàng!', 'danger')
        return redirect('/order-history')
        
    order['total_amount'] = float(order['total_money']) if order['total_money'] else 0
    order['created_at'] = order['orderDate'].strftime('%d/%m/%Y %H:%M') if hasattr(order.get('orderDate'), 'strftime') else order.get('orderDate', '')

    items = []
    try:
        cursor.execute("""
            SELECT od.*, p.title as book_title, p.id as product_id,
                   (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url,
                   (SELECT id FROM feedbacks WHERE user_id = %s AND product_id = p.id LIMIT 1) as is_reviewed
            FROM order_detail od
            JOIN products p ON od.product_id = p.id
            WHERE od.order_id = %s
        """, (session['user_id'], order_id))
        items = cursor.fetchall()
    except Exception:
        try:
            cursor.execute("""
                SELECT od.*, p.title as book_title, p.id as product_id,
                       (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url,
                       (SELECT id FROM FEEDBACK WHERE user_id = %s AND product_id = p.id LIMIT 1) as is_reviewed
                FROM order_detail od
                JOIN products p ON od.product_id = p.id
                WHERE od.order_id = %s
            """, (session['user_id'], order_id))
            items = cursor.fetchall()
        except Exception as e: print(f"Lỗi truy xuất chi tiết đơn: {e}")
        
    conn.close()
    return render_template('order_detail.html', order=order, items=items)

@app.route('/payment/<string:order_id>')
def payment_page(order_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, total_money as total_amount FROM orders WHERE id = %s AND user_id = %s", (order_id, session['user_id']))
    order = cursor.fetchone()
    conn.close()
    if not order:
        flash('Không tìm thấy đơn hàng!', 'danger')
        return redirect('/order-history')
    order['total_amount'] = float(order['total_amount']) if order['total_amount'] else 0
    return render_template('payment.html', order=order)

@app.route('/api/submit-feedback', methods=['POST'])
def submit_feedback():
    if 'user_id' not in session: return jsonify({'success': False, 'message': 'Vui lòng đăng nhập'})
    data = request.json
    product_id = data.get('product_id')
    rating = int(data.get('rating', 5))
    comment = data.get('comment', '')
    new_feedback_id = str(uuid.uuid4())
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedbacks (id, product_id, user_id, note, star, image)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (new_feedback_id, product_id, session['user_id'], comment, rating, ''))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Đánh giá thành công!'})
    except Exception:
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO FEEDBACK (id, product_id, user_id, note, star, image)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (new_feedback_id, product_id, session['user_id'], comment, rating, ''))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'Đánh giá thành công!'})
        except Exception as e2:
            print(f"Lỗi khi gửi Feedback: {e2}")
            return jsonify({'success': False, 'message': 'Đã có lỗi xảy ra. Vui lòng thử lại sau.'})

@app.route('/api/read-notifications', methods=['POST'])
def read_notifications():
    if 'user_id' in session:
        try:
            conn = get_db(); cursor = conn.cursor()
            cursor.execute("UPDATE notifications SET `read` = 1 WHERE user_id = %s", (session['user_id'],))
            conn.commit(); conn.close()
            return jsonify({'success': True})
        except Exception as e: print(f"Lỗi đọc thông báo: {e}")
    return jsonify({'success': False})

# =========================================================
# 5. QUẢN TRỊ VIÊN (ADMIN)
# =========================================================

@app.route('/admin')
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    query_revenue = """
        SELECT DATE_FORMAT(orderDate, '%d/%m') as date_label, SUM(total_money) as daily_revenue 
        FROM orders 
        WHERE DATE(orderDate) BETWEEN %s AND %s AND status != 'Đã hủy'
        GROUP BY DATE(orderDate) 
        ORDER BY DATE(orderDate) ASC
    """
    cursor.execute(query_revenue, (start_date, end_date))
    revenue_data = cursor.fetchall()
    
    if revenue_data:
        labels = [row['date_label'] for row in revenue_data]
        values = [float(row['daily_revenue']) for row in revenue_data]
    else:
        labels = ["Chưa có dữ liệu"]
        values = [0]

    query_best_sellers = """
        SELECT p.title as book_title, SUM(od.quantity) as total_sold, MAX(od.price) as price,
               (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url
        FROM order_detail od
        JOIN products p ON od.product_id = p.id
        JOIN orders o ON od.order_id = o.id
        WHERE o.status != 'Đã hủy'
        GROUP BY p.id, p.title
        ORDER BY total_sold DESC
        LIMIT 5
    """
    cursor.execute(query_best_sellers)
    best_sellers = cursor.fetchall()
    conn.close()

    return render_template('admin_dashboard.html', labels=labels, values=values, best_sellers=best_sellers, start_date=start_date, end_date=end_date)

@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    role_id = request.args.get('role_id', '')
    name = request.args.get('name', '')
    contact = request.args.get('contact', '')
    
    try:
        cursor.execute("SELECT * FROM roles")
        roles = cursor.fetchall()
    except Exception:
        roles = []
    
    query = "SELECT u.*, r.role_name FROM users u LEFT JOIN roles r ON u.role_id = r.id WHERE u.deleted = 0"
    params = []
    
    if role_id:
        query += " AND u.role_id = %s"
        params.append(role_id)
    if name:
        query += " AND u.full_name LIKE %s"
        params.append(f"%{name}%")
    if contact:
        query += " AND (u.email LIKE %s OR u.phone_number LIKE %s)"
        params.extend([f"%{contact}%", f"%{contact}%"])
        
    query += " ORDER BY u.full_name ASC"
    
    cursor.execute(query, tuple(params))
    users = cursor.fetchall()
    conn.close()
    
    return render_template('admin_users.html', users=users, roles=roles)

@app.route('/admin/add-user', methods=['POST'])
@admin_required
def admin_add_user():
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone_number = request.form.get('phone_number', '').strip() 
    password = request.form.get('password')
    role_id = request.form.get('role_id')
    user_name = request.form.get('user_name', '').strip()
    if not user_name: user_name = email.split('@')[0]

    hashed_pw = generate_password_hash(password)
    new_id = str(uuid.uuid4())
    
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (id, full_name, user_name, email, phone_number, password, role_id, deleted) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
    """, (new_id, full_name, user_name, email, phone_number, hashed_pw, role_id))
    conn.commit(); conn.close()
    flash('Thêm người dùng thành công!', 'success')
    return redirect('/admin/users')

@app.route('/admin/edit-user/<string:id>', methods=['POST'])
@admin_required
def edit_user(id):
    full_name = request.form.get('full_name')
    user_name = request.form.get('user_name')
    phone = request.form.get('phone_number')
    address = request.form.get('address')
    role_id = request.form.get('role_id')
    dob = request.form.get('date_of_birth')
    
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE users SET full_name=%s, user_name=%s, phone_number=%s, address=%s, role_id=%s, date_of_birth=%s WHERE id=%s", 
                   (full_name, user_name, phone, address, role_id, dob, id))
    conn.commit(); conn.close()
    flash('Cập nhật người dùng thành công!', 'success')
    return redirect('/admin/users')

@app.route('/admin/delete-user/<string:id>')
@admin_required
def delete_user(id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE users SET deleted = 1 WHERE id=%s", (id,))
    conn.commit(); conn.close()
    flash('Đã xóa người dùng!', 'warning')
    return redirect('/admin/users')

@app.route('/admin/products')
@admin_required
def admin_products():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    category_id = request.args.get('category_id', '')
    product_code = request.args.get('product_code', '')
    product_name = request.args.get('product_name', '')

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    query_conditions = ["p.deleted = 0"]
    params = []

    if category_id:
        query_conditions.append("p.category_id = %s"); params.append(category_id)
    if product_code:
        clean_code = product_code.replace('BOOK-', '').strip()
        query_conditions.append("p.id LIKE %s"); params.append(f"%{clean_code}%")
    if product_name:
        query_conditions.append("p.title LIKE %s"); params.append(f"%{product_name}%")

    where_clause = " AND ".join(query_conditions)

    cursor.execute(f"SELECT COUNT(*) as total FROM products p WHERE {where_clause}", tuple(params))
    total_books = cursor.fetchone()['total']
    total_pages = (total_books + per_page - 1) // per_page
    if total_pages == 0: total_pages = 1

    select_query = f"""
        SELECT p.*, c.name as category_name,
               (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE {where_clause} ORDER BY p.id DESC LIMIT %s OFFSET %s
    """
    params.extend([per_page, offset])
    cursor.execute(select_query, tuple(params))
    books = cursor.fetchall()
    
    for b in books: 
        b['price'] = float(b['sale_price']) if b.get('sale_price') else 0
        b['origin_price'] = float(b['origin_price']) if b.get('origin_price') else 0
        b['stock'] = b.get('stock', 50) 

    cursor.execute("SELECT * FROM categories")
    categories = cursor.fetchall()
    conn.close()

    return render_template('admin_products.html', books=books, categories=categories, page=page, total_pages=total_pages)

@app.route('/admin/add-book', methods=['POST'])
@admin_required
def add_book():
    try:
        title = request.form['title']
        desc = request.form['description']
        origin_price = float(request.form['origin_price'])
        sale_price = float(request.form['price'])
        category_id = request.form.get('category_id') or None

        image_path = ""
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                upload_folder = os.path.join('static', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                filename = secure_filename(f"book_{uuid.uuid4().hex[:8]}_{file.filename}")
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                image_path = f"/{filepath}".replace("\\", "/")

        product_id = str(uuid.uuid4())
        conn = get_db(); cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO products (id, title, description, sale_price, origin_price, category_id, deleted)
            VALUES (%s, %s, %s, %s, %s, %s, 0)
        """, (product_id, title, desc, sale_price, origin_price, category_id))

        cursor.execute("INSERT INTO image_product (id, product_id, url) VALUES (%s, %s, %s)",
                       (str(uuid.uuid4()), product_id, image_path))
        conn.commit(); conn.close()
        
        try:
            text_for_ai = f"Sản phẩm: {title}. Nội dung: {desc}"
            collection.add(ids=[product_id], documents=[text_for_ai], metadatas=[{"title": title, "price": sale_price}])
        except Exception: pass
        flash('Đã thêm sản phẩm mới thành công!', 'success')
    except Exception as e:
        flash(f'Lỗi khi thêm: {str(e)}', 'danger')
    return redirect('/admin/products')

@app.route('/admin/edit-book/<string:id>', methods=['POST'])
@admin_required
def edit_book(id):
    try:
        title = request.form['title']
        desc = request.form['description']
        origin_price = float(request.form['origin_price'])
        sale_price = float(request.form['price'])
        category_id = request.form.get('category_id') or None

        image_path = None
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                upload_folder = os.path.join('static', 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                filename = secure_filename(f"book_{uuid.uuid4().hex[:8]}_{file.filename}")
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                image_path = f"/{filepath}".replace("\\", "/")

        conn = get_db(); cursor = conn.cursor()
        cursor.execute("UPDATE products SET title=%s, description=%s, origin_price=%s, sale_price=%s, category_id=%s WHERE id=%s", 
                       (title, desc, origin_price, sale_price, category_id, id))

        if image_path:
            cursor.execute("UPDATE image_product SET url=%s WHERE product_id=%s LIMIT 1", (image_path, id))
        conn.commit(); conn.close()
        
        try:
            text_for_ai = f"Sản phẩm: {title}. Nội dung: {desc}"
            collection.update(ids=[id], documents=[text_for_ai], metadatas=[{"title": title, "price": sale_price}])
        except Exception: pass
        flash('Đã cập nhật sản phẩm thành công!', 'success')
    except Exception as e:
        flash(f'Lỗi cập nhật: {str(e)}', 'danger')
    return redirect('/admin/products')

@app.route('/admin/delete-book/<string:id>')
@admin_required
def delete_book(id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE products SET deleted = 1 WHERE id = %s", (id,))
    conn.commit(); conn.close()
    try: collection.delete(ids=[id])
    except: pass
    flash('Đã đưa sản phẩm vào thùng rác.', 'warning')
    return redirect('/admin/products')

@app.route('/admin/categories')
@admin_required
def admin_categories():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM categories")
    categories = cursor.fetchall()
    conn.close()
    return render_template('admin_categories.html', categories=categories)

@app.route('/admin/add-category', methods=['POST'])
@admin_required
def add_category():
    name = request.form.get('name', '').strip()
    new_id = str(uuid.uuid4())
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("INSERT INTO categories (id, name) VALUES (%s, %s)", (new_id, name))
    conn.commit(); conn.close()
    flash('Đã thêm danh mục mới!', 'success')
    return redirect('/admin/categories')

@app.route('/admin/edit-category/<string:id>', methods=['POST'])
@admin_required
def edit_category(id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE categories SET name=%s WHERE id=%s", (request.form.get('name'), id))
    conn.commit(); conn.close()
    flash('Đã cập nhật danh mục!', 'success')
    return redirect('/admin/categories')

@app.route('/admin/delete-category/<string:id>')
@admin_required
def delete_category(id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE products SET category_id = NULL WHERE category_id = %s", (id,)) 
    cursor.execute("DELETE FROM categories WHERE id=%s", (id,))
    conn.commit(); conn.close()
    flash('Đã xóa danh mục!', 'warning')
    return redirect('/admin/categories')

@app.route('/admin/discount-category', methods=['POST'])
@admin_required
def discount_category():
    category_id = request.form.get('category_id')
    percent = float(request.form.get('discount_percent', 0))
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("""
        UPDATE products SET sale_price = origin_price * (1 - %s / 100)
        WHERE category_id = %s AND deleted = 0
    """, (percent, category_id))
    conn.commit(); conn.close()
    flash(f'Đã giảm giá {percent}% cho toàn bộ sản phẩm trong danh mục!', 'success')
    return redirect('/admin/categories')

@app.route('/admin/orders')
@admin_required
def admin_orders():
    page = request.args.get('page', 1, type=int)
    per_page = 12 
    offset = (page - 1) * per_page
    
    status = request.args.get('status', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    query_conditions = ["1=1"]
    params = []

    if status:
        query_conditions.append("status = %s"); params.append(status)
    if start_date:
        query_conditions.append("DATE(orderDate) >= %s"); params.append(start_date)
    if end_date:
        query_conditions.append("DATE(orderDate) <= %s"); params.append(end_date)

    where_clause = " AND ".join(query_conditions)

    cursor.execute(f"SELECT COUNT(*) as total FROM orders WHERE {where_clause}", tuple(params))
    total_orders = cursor.fetchone()['total']
    total_pages = (total_orders + per_page - 1) // per_page
    if total_pages == 0: total_pages = 1

    query = f"SELECT * FROM orders WHERE {where_clause} ORDER BY orderDate DESC LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    cursor.execute(query, tuple(params))
    orders = cursor.fetchall()
    
    for o in orders:
        o['total_amount'] = float(o['total_money']) if o['total_money'] else 0
        o['customer_name'] = o.get('full_name', 'Khách hàng')
        o['phone'] = o.get('phone_number', '')
        o['created_at'] = o.get('orderDate', '')
        
    conn.close()
    return render_template('admin_orders.html', orders=orders, page=page, total_pages=total_pages)

@app.route('/admin/update-order/<string:order_id>', methods=['POST'])
@admin_required
def update_order_status(order_id):
    new_status = request.form.get('status')
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT user_id, status FROM orders WHERE id = %s", (order_id,))
    order = cursor.fetchone()
    
    if order:
        if order['status'] in ['Đã giao', 'Đã hủy']:
            flash('Đơn hàng đã hoàn tất hoặc bị hủy, không thể thay đổi trạng thái!', 'danger')
        else:
            cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, order_id))
            
            if order['user_id']:
                notif_id = str(uuid.uuid4())
                content = f"Đơn hàng #{order_id[:8]} đã chuyển sang trạng thái: {new_status}"
                try:
                    cursor.execute("""
                        INSERT INTO notifications (id, user_id, order_detail_id, content, `read`) 
                        VALUES (%s, %s, NULL, %s, 0)
                    """, (notif_id, order['user_id'], content))
                except Exception as e:
                    print(f"Lỗi thêm thông báo: {e}")
            conn.commit()
            flash(f'Đã cập nhật trạng thái đơn hàng thành: {new_status}', 'success')

    conn.close()
    return redirect(request.referrer or '/admin/orders')

@app.route('/admin/banners')
@admin_required
def admin_banners():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT g.id, g.image, p.title as product_name, g.product_id
        FROM galeries g LEFT JOIN products p ON g.product_id = p.id
    """)
    banners = cursor.fetchall()
    cursor.execute("SELECT id, title FROM products WHERE deleted = 0")
    products = cursor.fetchall()
    conn.close()
    return render_template('admin_banners.html', banners=banners, products=products)

@app.route('/admin/add-banner', methods=['POST'])
@admin_required
def add_banner():
    product_id = request.form.get('product_id') or None
    
    image_path = ""
    if 'image_file' in request.files:
        file = request.files['image_file']
        if file and file.filename != '':
            upload_folder = os.path.join('static', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filename = secure_filename(f"banner_{uuid.uuid4().hex[:8]}_{file.filename}")
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            image_path = f"/{filepath}".replace("\\", "/")
            
    new_id = str(uuid.uuid4())
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("INSERT INTO galeries (id, product_id, image) VALUES (%s, %s, %s)", (new_id, product_id, image_path))
    conn.commit(); conn.close()
    flash('Đã thêm sản phẩm ra trưng bày!', 'success')
    return redirect('/admin/banners')

@app.route('/admin/edit-banner/<string:id>', methods=['POST'])
@admin_required
def edit_banner(id):
    product_id = request.form.get('product_id') or None
    
    image_path = None
    if 'image_file' in request.files:
        file = request.files['image_file']
        if file and file.filename != '':
            upload_folder = os.path.join('static', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filename = secure_filename(f"banner_{uuid.uuid4().hex[:8]}_{file.filename}")
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            image_path = f"/{filepath}".replace("\\", "/")
            
    conn = get_db(); cursor = conn.cursor()
    if image_path:
        cursor.execute("UPDATE galeries SET product_id=%s, image=%s WHERE id=%s", (product_id, image_path, id))
    else:
        cursor.execute("UPDATE galeries SET product_id=%s WHERE id=%s", (product_id, id))
        
    conn.commit(); conn.close()
    flash('Đã cập nhật trưng bày!', 'success')
    return redirect('/admin/banners')

@app.route('/admin/delete-banner/<string:id>')
@admin_required
def delete_banner(id):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM galeries WHERE id=%s", (id,))
    conn.commit(); conn.close()
    flash('Đã xóa trưng bày!', 'warning')
    return redirect('/admin/banners')

@app.route('/admin/coupons')
@admin_required
def admin_coupons():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) as total FROM coupons")
    total_coupons = cursor.fetchone()['total']
    total_pages = (total_coupons + per_page - 1) // per_page
    if total_pages == 0: total_pages = 1
    cursor.execute("""
        SELECT * FROM coupons 
        ORDER BY expiration_date ASC LIMIT %s OFFSET %s
    """, (per_page, offset))
    coupons = cursor.fetchall()
    conn.close()
    return render_template('admin_coupons.html', coupons=coupons, page=page, total_pages=total_pages)

@app.route('/admin/add-coupon', methods=['POST'])
@admin_required
def add_coupon():
    code = request.form.get('code').strip().upper()
    discount = float(request.form.get('discount', 0))
    quantity = int(request.form.get('quantity', 0))
    expiration_date = request.form.get('expiration_date')
    
    conn = get_db(); cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO coupons (code, discount, expiration_date, expired, quantity)
            VALUES (%s, %s, %s, 0, %s)
        """, (code, discount, expiration_date, quantity))
        conn.commit()
        flash('Đã thêm mã giảm giá!', 'success')
    except Exception as e:
        flash(f'Lỗi (Có thể trùng mã): {str(e)}', 'danger')
    finally:
        conn.close()
    return redirect('/admin/coupons')

@app.route('/admin/edit-coupon/<string:code>', methods=['POST'])
@admin_required
def edit_coupon(code):
    expired = 1 if request.form.get('expired') else 0
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE coupons SET discount=%s, quantity=%s, expiration_date=%s, expired=%s WHERE code=%s",
                   (request.form.get('discount'), request.form.get('quantity'), request.form.get('expiration_date'), expired, code))
    conn.commit(); conn.close()
    flash('Đã cập nhật mã giảm giá!', 'success')
    return redirect('/admin/coupons')

@app.route('/admin/delete-coupon/<string:code>')
@admin_required
def delete_coupon(code):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM coupons WHERE code=%s", (code,))
    conn.commit(); conn.close()
    flash('Đã xóa mã giảm giá!', 'warning')
    return redirect('/admin/coupons')

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5000)