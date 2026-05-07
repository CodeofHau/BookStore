import mysql.connector
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
import os
import uuid

load_dotenv()

# --- BỘ DỮ LIỆU 16 CUỐN SÁCH (MỖI CUỐN 3 ẢNH ĐỘ PHÂN GIẢI CAO KHÔNG BAO GIỜ LỖI) ---
LOCAL_BOOKS_DATA = [
    # ==== TÂM LÝ - KỸ NĂNG ====
    {
        "title": "Đắc Nhân Tâm", "author": "Dale Carnegie", "category": "Tâm Lý - Kỹ Năng", 
        "price": 68000, "origin_price": 86000,
        "desc": "Cuốn sách kinh điển đưa ra các lời khuyên về cách thức cư xử, ứng xử và giao tiếp với mọi người để đạt được thành công trong cuộc sống.",
        "images": [
            "https://images.unsplash.com/photo-1544947950-fa07a98d237f?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1512820790803-83ca734da794?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1456953180671-730de08edaa7?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Tâm Lý Học Tội Phạm", "author": "Stanton E. Samenow", "category": "Tâm Lý - Kỹ Năng", 
        "price": 125000, "origin_price": 165000,
        "desc": "Giải mã những góc khuất tăm tối nhất trong tâm trí con người. Giúp bạn hiểu được động cơ đằng sau những hành vi phi lý.",
        "images": [
            "https://images.unsplash.com/photo-1587876931567-564ce588bfbd?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1589829085413-56de8ae18c73?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1505664159854-2326115c04c0?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Tư Duy Nhanh Và Chậm", "author": "Daniel Kahneman", "category": "Tâm Lý - Kỹ Năng", 
        "price": 168000, "origin_price": 235000,
        "desc": "Phân tích về hai hệ thống tư duy điều khiển các quyết định của chúng ta: Hệ thống 1 nhanh, cảm tính; Hệ thống 2 chậm, logic.",
        "images": [
            "https://images.unsplash.com/photo-1532012197267-da84d127e765?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1491841550275-ad7854e35ca6?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Tuổi Trẻ Đáng Giá Bao Nhiêu", "author": "Rosie Nguyễn", "category": "Tâm Lý - Kỹ Năng", 
        "price": 55000, "origin_price": 80000,
        "desc": "Những câu chuyện thực tế và lời khuyên hữu ích cho người trẻ về việc học, làm việc và khám phá bản thân để không hoài phí thanh xuân.",
        "images": [
            "https://images.unsplash.com/photo-1511108690759-001cb7a508fa?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1495640388908-05fa85288e61?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1474366521946-c3d4b507abf2?auto=format&fit=crop&q=80&w=800"
        ]
    },

    # ==== VĂN HỌC ====
    {
        "title": "Cây Cam Ngọt Của Tôi", "author": "José Mauro", "category": "Văn Học", 
        "price": 75000, "origin_price": 108000,
        "desc": "Một tác phẩm kinh điển của Brazil về tuổi thơ, tình yêu thương và nỗi đau. Câu chuyện về cậu bé Zezé sẽ chạm đến trái tim bạn.",
        "images": [
            "https://images.unsplash.com/photo-1481628485456-02e0b57e7939?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1497436073866-508b982d6880?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1507738978512-35f115a31792?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Mắt Biếc", "author": "Nguyễn Nhật Ánh", "category": "Văn Học", 
        "price": 82000, "origin_price": 110000,
        "desc": "Câu chuyện tình yêu buồn và đầy luyến tiếc giữa Ngạn và Hà Lan từ thuở ấu thơ đến khi trưởng thành.",
        "images": [
            "https://images.unsplash.com/photo-1476275466078-4007374efac4?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1463320726281-696a485928c7?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Số Đỏ", "author": "Vũ Trọng Phụng", "category": "Văn Học", 
        "price": 60000, "origin_price": 75000,
        "desc": "Tiểu thuyết trào phúng xuất sắc phê phán xã hội thượng lưu rởm đời những năm 1930 thông qua nhân vật Xuân Tóc Đỏ.",
        "images": [
            "https://images.unsplash.com/photo-1524578271613-d550eacf6090?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1535905557558-afc4877a26fc?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1457369804613-52c61a468e7d?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Cho Tôi Xin Một Vé Đi Tuổi Thơ", "author": "Nguyễn Nhật Ánh", "category": "Văn Học", 
        "price": 65000, "origin_price": 80000,
        "desc": "Cuốn sách đưa người đọc trở về những năm tháng tuổi thơ hồn nhiên, tinh nghịch nhưng cũng đầy triết lý nhân sinh sâu sắc.",
        "images": [
            "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1471107340929-a87cd0f5b5f3?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1516979187457-637abb4f9353?auto=format&fit=crop&q=80&w=800"
        ]
    },

    # ==== KINH DOANH - TÀI CHÍNH ====
    {
        "title": "Cha Giàu Cha Nghèo", "author": "Robert T. Kiyosaki", "category": "Kinh Doanh - Tài Chính", 
        "price": 85000, "origin_price": 109000,
        "desc": "Bài học quản lý tài chính cá nhân kinh điển, sự khác biệt trong tư duy về tiền bạc giữa người giàu và người nghèo.",
        "images": [
            "https://images.unsplash.com/photo-1554774853-719586f82d77?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1579621970563-ebec7560ff3e?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Nghĩ Giàu Làm Giàu", "author": "Napoleon Hill", "category": "Kinh Doanh - Tài Chính", 
        "price": 95000, "origin_price": 110000,
        "desc": "13 nguyên tắc thành công được đúc kết từ việc nghiên cứu hàng trăm người giàu nhất nước Mỹ.",
        "images": [
            "https://images.unsplash.com/photo-1507679799987-c73779587ccf?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1518186285589-2f7649de83e0?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Từ Tốt Đến Vĩ Đại", "author": "Jim Collins", "category": "Kinh Doanh - Tài Chính", 
        "price": 115000, "origin_price": 140000,
        "desc": "Phân tích cách các công ty bình thường vươn lên trở thành những tập đoàn vĩ đại và trường tồn.",
        "images": [
            "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&q=80&w=800"
        ]
    },

    # ==== LỊCH SỬ - TRIẾT HỌC ====
    {
        "title": "Sapiens - Lược Sử Loài Người", "author": "Yuval Noah Harari", "category": "Lịch Sử - Triết Học", 
        "price": 180000, "origin_price": 250000,
        "desc": "Cái nhìn toàn cảnh về lịch sử phát triển của loài người từ thời tiền sử đến hiện đại, giải thích vì sao chúng ta thống trị Trái Đất.",
        "images": [
            "https://images.unsplash.com/photo-1461360228754-6e81c478b882?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1447069387366-5aab5ee3fcd5?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1535905557558-afc4877a26fc?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Lược Sử Thời Gian", "author": "Stephen Hawking", "category": "Lịch Sử - Triết Học", 
        "price": 125000, "origin_price": 145000,
        "desc": "Khám phá những bí ẩn lớn nhất của vũ trụ, từ vụ nổ Big Bang đến các lỗ đen, được viết bởi nhà vật lý vĩ đại Stephen Hawking.",
        "images": [
            "https://images.unsplash.com/photo-1468164016595-6108e4c60c8b?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1419242902214-272b3f66ee7a?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Thế Giới Của Sophie", "author": "Jostein Gaarder", "category": "Lịch Sử - Triết Học", 
        "price": 110000, "origin_price": 135000,
        "desc": "Một cuốn tiểu thuyết kể về lịch sử triết học phương Tây một cách dễ hiểu và hấp dẫn thông qua cuộc phiêu lưu của cô bé Sophie.",
        "images": [
            "https://images.unsplash.com/photo-1491841550275-ad7854e35ca6?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1505664159854-2326115c04c0?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1544947950-fa07a98d237f?auto=format&fit=crop&q=80&w=800"
        ]
    },

    # ==== TIỂU THUYẾT NƯỚC NGOÀI ====
    {
        "title": "Bố Già (The Godfather)", "author": "Mario Puzo", "category": "Tiểu Thuyết Nước Ngoài", 
        "price": 115000, "origin_price": 140000,
        "desc": "Bức tranh chân thực, khốc liệt về thế giới ngầm của giới mafia Ý tại Mỹ thông qua câu chuyện của gia đình Corleone.",
        "images": [
            "https://images.unsplash.com/photo-1585779034823-7e9ac8fa3707?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1481628485456-02e0b57e7939?auto=format&fit=crop&q=80&w=800"
        ]
    },
    {
        "title": "Hai Vạn Dặm Dưới Đáy Biển", "author": "Jules Verne", "category": "Tiểu Thuyết Nước Ngoài", 
        "price": 95000, "origin_price": 125000,
        "desc": "Cuộc hành trình kỳ thú khám phá đại dương trên chiếc tàu ngầm Nautilus cùng thuyền trưởng Nemo huyền thoại.",
        "images": [
            "https://images.unsplash.com/photo-1682687220742-aba13b6e50ba?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1518837695005-2083093ee35b?auto=format&fit=crop&q=80&w=800",
            "https://images.unsplash.com/photo-1497436073866-508b982d6880?auto=format&fit=crop&q=80&w=800"
        ]
    }
]

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASS", ""),
        database=os.getenv("DB_NAME", "bookstore"),
        port=int(os.getenv("DB_PORT", 3306))
    )

def seed_database():
    print("🚀 Bắt đầu làm sạch và cấy dữ liệu sách mới (16 Cuốn - 3 Ảnh/Cuốn)...")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        chroma_client = chromadb.PersistentClient(path="./chroma_db")
        try: chroma_client.delete_collection("books_search")
        except: pass
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        collection = chroma_client.create_collection(name="books_search", embedding_function=ef)
    except Exception as e:
        print(f"⚠️ Lỗi ChromaDB: {e}")
        return

    cursor.execute("DELETE FROM order_detail")
    cursor.execute("DELETE FROM carts")
    cursor.execute("DELETE FROM feedbacks")
    cursor.execute("DELETE FROM galeries")
    cursor.execute("DELETE FROM image_product")
    cursor.execute("DELETE FROM products")
    conn.commit()
    print("🧹 Đã dọn dẹp sách cũ thành công.")

    print("📁 Đang kiểm tra và tạo danh mục...")
    category_ids = {}
    for book in LOCAL_BOOKS_DATA:
        cat_name = book['category']
        if cat_name not in category_ids:
            cursor.execute("SELECT id FROM categories WHERE name = %s", (cat_name,))
            cat = cursor.fetchone()
            if cat:
                category_ids[cat_name] = cat['id']
            else:
                new_cat_id = str(uuid.uuid4())
                cursor.execute("INSERT INTO categories (id, name) VALUES (%s, %s)", (new_cat_id, cat_name))
                conn.commit()
                category_ids[cat_name] = new_cat_id

    print("📚 Đang nạp 16 cuốn sách vào hệ thống...")
    total_added = 0
    
    for book in LOCAL_BOOKS_DATA:
        title = book['title']
        author = book['author']
        cat_id = category_ids[book['category']]
        desc = f"Tác giả: {author}\n\n{book['desc']}"
        sale_price = book['price']
        origin_price = book['origin_price']
        
        product_id = str(uuid.uuid4())

        try:
            cursor.execute("""
                INSERT INTO products (id, title, description, sale_price, origin_price, category_id, deleted) 
                VALUES (%s, %s, %s, %s, %s, %s, 0)
            """, (product_id, title, desc, sale_price, origin_price, cat_id))
            
            for img_url in book['images']:
                image_id = str(uuid.uuid4())
                cursor.execute("INSERT INTO image_product (id, product_id, url) VALUES (%s, %s, %s)", (image_id, product_id, img_url))

            text_for_ai = f"Sách: {title}. Danh mục: {book['category']}. Tác giả: {author}. Nội dung: {book['desc']}"
            collection.add(ids=[product_id], documents=[text_for_ai], metadatas=[{"title": title, "price": sale_price}])
            
            conn.commit()
            total_added += 1
            print(f"   ✅ Đã thêm: {title} ({len(book['images'])} ảnh)")
        except Exception as e:
            conn.rollback()
            print(f"   ❌ Lỗi lưu sách {title}: {e}")

    conn.close()
    print(f"\n🎉 HOÀN TẤT TUYỆT ĐỐI! Hệ thống đã nạp thành công {total_added} cuốn sách xịn sò cho đồ án của bạn.")

if __name__ == "__main__":
    seed_database()