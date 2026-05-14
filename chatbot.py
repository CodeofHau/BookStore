from flask import Blueprint, request, jsonify, session
import mysql.connector
import chromadb
from chromadb.utils import embedding_functions
import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Tạo Blueprint cho Chatbot
chat_bp = Blueprint('chat_bp', __name__)

# 1. Khởi tạo ChromaDB độc lập
try:
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    collection = chroma_client.get_or_create_collection(name="books_search", embedding_function=ef)
except Exception as e:
    print(f"⚠️ Cảnh báo: Lỗi ChromaDB trong Chatbot - {e}")
    collection = None

# Hàm kết nối CSDL dùng riêng cho Chatbot
def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASS", ""),
        database=os.getenv("DB_NAME", "bookstore"),
        port=int(os.getenv("DB_PORT", 3306))
    )

@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    try:
        user_msg = request.json.get('message', '').strip()
        if not user_msg:
            return jsonify({"response": "Bạn muốn hỏi gì nào?", "books": []})

        # 2. TRUY XUẤT NGỮ CẢNH TỪ RAG (Nâng số lượng lên 3 cuốn để đa dạng hơn)
        found_books = []
        context = ""
        
        if collection:
            results = collection.query(query_texts=[user_msg], n_results=3)
            
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
                    context_list.append(f"- Sách: {b['title']} (Thể loại: {cat_name}). Giá: {b['price']:,.0f}đ. Mô tả: {b['description']}")
                context = "\n".join(context_list)

        # 3. QUẢN LÝ BỘ NHỚ NGỮ CẢNH (CHAT HISTORY)
        if 'chat_history' not in session:
            session['chat_history'] = []
            
        history = session['chat_history']

        # Xây dựng cấu trúc Messages chuẩn cho AI
        messages = [
            {"role": "system", "content": "Bạn là nhân viên tư vấn sách chuyên nghiệp của BookStore. Nhiệm vụ: Trả lời ngắn gọn, lịch sự, đúng trọng tâm bằng tiếng Việt. TUYỆT ĐỐI KHÔNG bịa ra sách. CHỈ dùng thông tin sách được hệ thống cung cấp dưới đây để giới thiệu cho khách."}
        ]
        
        # Nhồi lịch sử cũ vào để AI nhớ (giữ tối đa 4 tin nhắn gần nhất để tránh lag máy)
        messages.extend(history[-4:])

        # Ghép ngữ cảnh RAG vào câu hỏi hiện tại
        if context:
            user_content = f"Dữ liệu từ kho sách:\n{context}\n\nKhách hỏi: {user_msg}"
        else:
            user_content = user_msg
            
        messages.append({"role": "user", "content": user_content})

        # 4. GỌI OLLAMA (Dùng /api/chat thay cho /api/generate)
        response = requests.post("http://localhost:11434/api/chat", json={
            "model": "qwen2:1.5b",
            "messages": messages,
            "stream": False
        })
        
        if response.status_code == 200:
            ai_reply = response.json()['message']['content']
            
            # Cập nhật lại lịch sử (Lưu câu hỏi gốc của khách, không lưu phần ngữ cảnh để tránh rác RAM)
            history.append({"role": "user", "content": user_msg})
            history.append({"role": "assistant", "content": ai_reply})
            session['chat_history'] = history # Lưu lại vào session
            
            return jsonify({"response": ai_reply, "books": found_books})
        else:
            return jsonify({"response": "Lỗi kết nối với lõi AI cục bộ.", "books": []})
            
    except Exception as e:
        print(f"Lỗi AI: {e}")
        return jsonify({"response": "Hệ thống Ollama đang tắt. Vui lòng mở terminal gõ 'ollama run qwen2:1.5b'.", "books": []})

# API để xóa trí nhớ của AI khi cần
@chat_bp.route('/api/clear-chat', methods=['POST'])
def clear_chat():
    session.pop('chat_history', None)
    return jsonify({"success": True})