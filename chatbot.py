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

        # --- LẤY THÔNG TIN CÁ NHÂN CỦA KHÁCH HÀNG ---
        user_name = session.get('user_name', 'Khách hàng')
        user_id = session.get('user_id', None)

        # --- MÀNG LỌC Ý ĐỊNH BẰNG PYTHON (Khắc phục AI lười) ---
        user_msg_lower = user_msg.lower()
        is_chat_only = False
        chat_keywords = ['chào', 'hello', 'hi', 'cảm ơn', 'thanks', 'tạm biệt', 'bye', 'ok', 'oke', 'vâng', 'dạ']
        
        # Nếu câu nói dưới 20 ký tự VÀ chứa các từ giao tiếp cơ bản, khóa chức năng tìm sách
        if len(user_msg_lower) <= 20 and any(kw in user_msg_lower for kw in chat_keywords):
            is_chat_only = True

        # --- SIÊU NĂNG LỰC 1: TRA CỨU ĐƠN HÀNG TỰ ĐỘNG BẰNG TỪ KHÓA ---
        order_context = ""
        check_order_keywords = ['đơn hàng', 'đơn của tôi', 'giao chưa', 'tình trạng đơn', 'kiểm tra đơn']
        if user_id and any(kw in user_msg_lower for kw in check_order_keywords):
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, status, total_money, orderDate 
                FROM orders WHERE user_id = %s ORDER BY orderDate DESC LIMIT 1
            """, (user_id,))
            last_order = cursor.fetchone()
            conn.close()

            if last_order:
                order_context = f"""
                [THÔNG TIN MẬT CHO AI]: Khách đang hỏi về đơn hàng. 
                Đơn hàng gần nhất của {user_name} có mã là #{last_order['id'][:8]}. 
                Tổng tiền: {float(last_order['total_money']):,.0f}đ. 
                Trạng thái hiện tại: {last_order['status']}. 
                Hãy báo cáo trạng thái này cho khách.
                """
            else:
                order_context = f"[THÔNG TIN MẬT CHO AI]: Hệ thống kiểm tra thấy {user_name} chưa có đơn hàng nào."

        # --- SIÊU NĂNG LỰC 2: RAG TÌM SÁCH THÔNG MINH ---
        found_books = []
        rag_context = ""
        
        # Chỉ kích hoạt quét RAG nếu KHÔNG phải là chat phiếm và KHÔNG hỏi đơn hàng
        if collection and not order_context and not is_chat_only:
            results = collection.query(query_texts=[user_msg], n_results=3)
            if results['ids'] and results['ids'][0]:
                found_ids = results['ids'][0]
                conn = get_db()
                cursor = conn.cursor(dictionary=True)
                fmt = ','.join(['%s'] * len(found_ids))
                cursor.execute(f"""
                    SELECT p.id, p.title, p.sale_price as price, p.description, c.name as category_name,
                           (SELECT url FROM image_product WHERE product_id = p.id LIMIT 1) as image_url
                    FROM products p LEFT JOIN categories c ON p.category_id = c.id
                    WHERE p.id IN ({fmt}) AND p.deleted = 0
                """, tuple(found_ids))
                found_books = cursor.fetchall()
                conn.close()

                context_list = []
                for b in found_books:
                    b['price'] = float(b['price']) if b['price'] else 0
                    cat_name = b['category_name'] or 'Chưa phân loại'
                    context_list.append(f"- Sách: {b['title']} (Thể loại: {cat_name}). Giá: {b['price']:,.0f}đ. Mô tả: {b['description']}")
                rag_context = "\n".join(context_list)

        # --- QUẢN LÝ LỊCH SỬ VÀ XÂY DỰNG PROMPT ---
        if 'chat_history' not in session: session['chat_history'] = []
        history = session['chat_history']

        # Dạy AI nhận biết bản thân và khách hàng với KỶ LUẬT THÉP
        system_prompt = f"""Bạn là AI tư vấn sách của BookStore. Tên khách hàng đang chat là: {user_name}.
Quy tắc BẮT BUỘC phải tuân thủ (vi phạm sẽ bị tắt hệ thống):
1. Thái độ: Xưng "mình", gọi khách là "{user_name}". Nói chuyện chân thật, NGẮN GỌN, đi thẳng vào vấn đề. TUYỆT ĐỐI KHÔNG dùng từ sáo rỗng, KHÔNG khen ngợi hay nịnh nọt khách.
2. Xử lý mã bí mật: 
   - Nếu khách CHỈ chào hỏi bình thường HOẶC bạn đang trả lời về đơn hàng: Bạn BẮT BUỘC phải viết mã [NO_BOOK] vào ngay đầu câu trả lời, và không giới thiệu sách.
3. KHI KHÁCH TÌM SÁCH (Rất quan trọng):
   - Bạn phải đối chiếu yêu cầu của khách với "Dữ liệu kho sách" được cung cấp.
   - Nếu cuốn sách khách tìm KHÔNG CÓ mặt trong "Dữ liệu kho sách", BẠN PHẢI NÓI RÕ RÀNG: "Xin lỗi {user_name}, hiện tại cửa hàng mình không có cuốn sách này."
   - Sau khi xin lỗi, bạn mới được phép giới thiệu các cuốn sách thay thế có trong "Dữ liệu kho sách" (nếu thấy phù hợp).
   - TUYỆT ĐỐI không tự bịa ra bất kỳ tên sách nào không có trong dữ liệu."""

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-4:])

        # Cung cấp ngữ cảnh cho câu hỏi hiện tại
        current_context = ""
        if order_context: current_context += f"{order_context}\n"
        if rag_context: current_context += f"Dữ liệu kho sách:\n{rag_context}\n"
        
        user_content = f"{current_context}\nKhách ({user_name}) nói: {user_msg}" if current_context else user_msg
        messages.append({"role": "user", "content": user_content})

        # --- GỌI LLM XỬ LÝ ---
        response = requests.post("http://localhost:11434/api/chat", json={
            "model": "qwen2:1.5b",
            "messages": messages,
            "stream": False
        })
        
        if response.status_code == 200:
            ai_reply = response.json()['message']['content']
            
            # --- BỘ LỌC XÓA MẬT MÃ TRƯỚC KHI TRẢ VỀ CHO KHÁCH ---
            if "[NO_BOOK]" in ai_reply:
                ai_reply = ai_reply.replace("[NO_BOOK]", "").strip()
                found_books = [] 
            
            history.append({"role": "user", "content": user_msg})
            history.append({"role": "assistant", "content": ai_reply})
            session['chat_history'] = history
            
            return jsonify({"response": ai_reply, "books": found_books})
        else:
            return jsonify({"response": "Lỗi kết nối với lõi AI cục bộ.", "books": []})
            
    except Exception as e:
        print(f"Lỗi AI: {e}")
        return jsonify({"response": "Hệ thống Ollama đang tắt. Vui lòng mở terminal gõ 'ollama run qwen2:1.5b'.", "books": []})

@chat_bp.route('/api/clear-chat', methods=['POST'])
def clear_chat():
    session.pop('chat_history', None)
    return jsonify({"success": True})