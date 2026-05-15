import os
import re 
import google.generativeai as genai
from flask import Blueprint, request, jsonify, session
import chromadb
from chromadb.utils import embedding_functions

chat_bp = Blueprint('chat', __name__)

# Cấu hình API Key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# =====================================================================
# BÍ QUYẾT CHỐNG "BỊA SÁCH": CHỈ THỊ HỆ THỐNG CỰC KỲ KHẮT KHE
# =====================================================================
system_instruction = """
Bạn là một chuyên gia tư vấn sách uyên bác đang làm việc tại BookStore.
Sứ mệnh của bạn là truyền cảm hứng đọc sách và giúp khách hàng tìm được sách phù hợp.

QUY TẮC CỐT LÕI (BẮT BUỘC TUÂN THỦ 100%):
1. HỆ THỐNG SẼ CUNG CẤP [DANH SÁCH SÁCH GỢI Ý TỪ DATABASE]. Bạn PHẢI DỰA VÀO ĐÂY để tư vấn.
2. NGHIÊM CẤM TỰ BỊA RA TÊN SÁCH: Tuyệt đối chỉ giới thiệu những cuốn sách có mặt trong [DANH SÁCH SÁCH GỢI Ý]. Không được đề xuất sách bên ngoài, dù nó rất nổi tiếng.
3. NẾU danh sách gợi ý trống, hãy thành thật xin lỗi: "Hiện tại cửa hàng mình tạm thời chưa có cuốn sách nào sát với yêu cầu này của bạn."
4. Xưng "mình" và gọi khách là "bạn". Trình bày rõ ràng, chia đoạn ngắn dễ đọc, dùng các emoji như 📚, ✨.
"""

# Khởi tạo mô hình Gemini 2.5 Flash
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=system_instruction
)

# Bộ nhớ tạm của Server để AI nhớ lịch sử trò chuyện theo từng khách hàng
chat_sessions = {}

# Kết nối CSDL Vector (ChromaDB)
try:
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    collection = chroma_client.get_collection(name="books_search", embedding_function=ef)
except Exception as e:
    collection = None
    print("Lỗi kết nối ChromaDB trong Chatbot:", e)

@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({'response': 'Bạn muốn hỏi gì nào? 😊', 'books': []})

    # Lấy ID của khách (nếu chưa đăng nhập thì dùng session chung)
    user_id = session.get('user_id', 'guest_user')
    if user_id not in chat_sessions:
        chat_sessions[user_id] = model.start_chat(history=[])
    
    current_chat = chat_sessions[user_id]

    try:
        recommended_books = []
        context_for_ai = ""
        
        # ==============================================================
        # 1. BỘ LỌC TOÁN HỌC: BẮT ĐIỀU KIỆN GIÁ TRONG CÂU HỎI
        # ==============================================================
        max_price = float('inf') # Mặc định là vô hạn
        # Tìm các cụm từ như "dưới 100k", "dưới 100.000đ", "dưới 50 nghìn"
        price_match = re.search(r'dưới\s*([\d\.,]+)\s*(k|nghìn|đ)?', user_message.lower())
        if price_match:
            # Làm sạch chuỗi số (xóa dấu chấm, phẩy)
            num_str = price_match.group(1).replace('.', '').replace(',', '')
            if num_str.isdigit():
                val = int(num_str)
                unit = price_match.group(2)
                
                # Tính toán ra giá trị thực (VND)
                if unit in ['k', 'nghìn']:
                    max_price = val * 1000
                elif val < 1000 and not unit: # Nếu khách gõ "dưới 100" (ngầm hiểu 100k)
                    max_price = val * 1000
                else:
                    max_price = val

        # ==============================================================
        # 2. TÌM KIẾM BẰNG CHROMADB VÀ LỌC LẠI
        # ==============================================================
        if collection:
            # Lấy hẳn 15 cuốn để phòng hờ bị loại bớt do giá
            results = collection.query(query_texts=[user_message], n_results=15)
            
            if results['ids'] and results['ids'][0]:
                for i in range(len(results['ids'][0])):
                    book_id = results['ids'][0][i]
                    meta = results['metadatas'][0][i]
                    price = float(meta.get('price', 0))
                    
                    # CHỐT CHẶN THẦN THÁNH: Cuốn nào đắt hơn max_price là loại bỏ thẳng tay!
                    if price <= max_price:
                        # Đưa vào mảng để gửi xuống giao diện tạo nút bấm
                        recommended_books.append({
                            'id': book_id,
                            'title': meta.get('title', 'Sách hay'),
                            'price': price
                        })
                        
                        # Tạo bối cảnh cho AI đọc
                        context_for_ai += f"- Cuốn: '{meta.get('title')}' (Giá: {price}đ)\n"
                        
                    # Chỉ lấy tối đa 4 cuốn xuất sắc nhất để hiện ra web
                    if len(recommended_books) == 4:
                        break

        # 3. ÉP AI PHẢI ĐỌC DỮ LIỆU ĐÃ ĐƯỢC LỌC KỸ
        if context_for_ai:
            prompt = f"Khách hàng hỏi: '{user_message}'.\n\n[DANH SÁCH SÁCH GỢI Ý TỪ DATABASE]:\n{context_for_ai}\n\nHãy tư vấn và mời khách mua các cuốn sách này. Không bịa sách khác."
        else:
            prompt = f"Khách hàng hỏi: '{user_message}'.\n\n[DANH SÁCH SÁCH GỢI Ý TỪ DATABASE]: (Trống)\n\nHãy trả lời khách và khéo léo nói rằng hiện tại cửa hàng không có cuốn nào có mức giá đó."

        # 4. Gửi cho Gemini suy luận
        response = current_chat.send_message(prompt)
        
        return jsonify({
            'response': response.text,
            'books': recommended_books # Trả về danh sách đã lọc chặt chẽ
        })
        
    except Exception as e:
        print("Lỗi Gemini API:", e)
        return jsonify({
            'response': 'Xin lỗi bạn, hệ thống AI đang nghẽn mạng một chút. Bạn hỏi lại mình sau vài giây nhé! 🛠️',
            'books': []
        })