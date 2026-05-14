import pandas as pd
import mysql.connector
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
import os
import uuid
from tqdm import tqdm

load_dotenv()

def import_tiki_data():
    print("🚀 Bắt đầu nạp dữ liệu Tiki Books...")
    
    # 1. Kết nối Database
    try:
        db = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASS", ""),
            database=os.getenv("DB_NAME", "bookstore"),
            port=int(os.getenv("DB_PORT", 3306))
        )
        cursor = db.cursor(dictionary=True)
    except Exception as e:
        print(f"❌ Lỗi kết nối MySQL: {e}\nHãy kiểm tra lại DB_PASS trong file .env")
        return

    # 2. Khởi tạo ChromaDB
    print("🧠 Đang khởi tạo bộ não AI (ChromaDB)...")
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    try:
        chroma_client.delete_collection("books_search") # Xóa bộ nhớ cũ
    except:
        pass
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    collection = chroma_client.create_collection(name="books_search", embedding_function=ef)

    # 3. Dọn dẹp Database cũ
    print("🧹 Đang dọn dẹp dữ liệu sách cũ trong MySQL...")
    cursor.execute("DELETE FROM order_detail")
    cursor.execute("DELETE FROM carts")
    cursor.execute("DELETE FROM feedbacks")
    cursor.execute("DELETE FROM galeries")
    cursor.execute("DELETE FROM image_product")
    cursor.execute("DELETE FROM products")
    db.commit()

    # 4. Đọc file CSV
    file_path = "book_data.csv" # Tên file tải về từ Kaggle
    if not os.path.exists(file_path):
        print(f"❌ Không tìm thấy file '{file_path}'. Hãy tải từ Kaggle và để cùng thư mục với code.")
        return

    df = pd.read_csv(file_path)
    df = df.dropna(subset=['title']) # Bỏ qua các dòng bị lỗi không có tên sách
    print(f"📚 Bắt đầu nạp {len(df)} cuốn sách vào hệ thống...")

    # Cache danh mục để tăng tốc độ
    category_cache = {}
    cursor.execute("SELECT id, name FROM categories")
    for row in cursor.fetchall():
        category_cache[row['name']] = row['id']

    # 5. Lặp và nạp dữ liệu
    total_added = 0
    for index, row in tqdm(df.iterrows(), total=df.shape[0]):
        try:
            title = str(row.get('title', '')).strip()
            author = str(row.get('authors', 'Đang cập nhật')).strip()
            if author == 'nan': author = 'Nhiều tác giả'
            
            cat_name = str(row.get('category', 'Sách Khác')).strip()
            if cat_name == 'nan': cat_name = 'Sách Khác'
            
            # Xử lý giá tiền (chống lỗi ép kiểu)
            try: origin_price = int(row.get('original_price', 100000))
            except: origin_price = 100000
                
            try: sale_price = int(row.get('current_price', 80000))
            except: sale_price = origin_price

            image_url = str(row.get('cover_link', 'https://via.placeholder.com/300x400')).strip()

            # Thủ thuật xử lý Description: Sinh ra một đoạn mô tả chuẩn form vì Tiki không có sẵn mô tả dài
            description = f"Tác giả: {author}. Đây là một tác phẩm nổi bật thuộc thể loại {cat_name}. Cuốn sách mang đến cho độc giả những kiến thức và trải nghiệm vô giá, hiện đang được phân phối tại BookStore."

            # Xử lý Category
            if cat_name not in category_cache:
                cat_id = str(uuid.uuid4())
                cursor.execute("INSERT INTO categories (id, name) VALUES (%s, %s)", (cat_id, cat_name))
                db.commit()
                category_cache[cat_name] = cat_id
            else:
                cat_id = category_cache[cat_name]

            # Thêm Product (Lưu ý: Không có cột stock theo đúng cấu trúc của bạn)
            product_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO products (id, title, description, sale_price, origin_price, category_id, deleted) 
                VALUES (%s, %s, %s, %s, %s, %s, 0)
            """, (product_id, title, description, sale_price, origin_price, cat_id))
            
            # Thêm Image
            cursor.execute("INSERT INTO image_product (id, product_id, url) VALUES (%s, %s, %s)", 
                           (str(uuid.uuid4()), product_id, image_url))
            
            # Nhúng vector vào ChromaDB cho AI
            text_for_ai = f"Tên sách: {title}. Tác giả: {author}. Thể loại: {cat_name}. Giá: {sale_price} VNĐ. Nội dung: {description}"
            collection.add(
                documents=[text_for_ai],
                metadatas=[{"title": title, "price": sale_price}],
                ids=[product_id]
            )
            total_added += 1
            
        except Exception as e:
            continue # Lỗi 1 cuốn thì âm thầm bỏ qua, chạy tiếp cuốn khác
            
    db.commit()
    db.close()
    print(f"\n🎉 HOÀN TẤT TUYỆT ĐỐI! Đã nạp thành công {total_added} cuốn sách vào website và hệ thống Chatbot AI.")

if __name__ == "__main__":
    import_tiki_data()