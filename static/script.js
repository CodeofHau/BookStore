// --- 1. CẤU HÌNH & KHỞI TẠO ---
document.addEventListener("DOMContentLoaded", () => {
    updateCartBadge();
    
    // Nếu đang ở trang Giỏ hàng thì tải dữ liệu
    if (window.location.pathname === '/cart') {
        loadCartPage();
    }
});

// --- 2. XỬ LÝ THÊM VÀO GIỎ (Add to Cart) ---
// Hàm này được gọi từ nút "Thêm vào giỏ" ở HTML
function addToCartAnimation(btn) {
    let bookId = btn.getAttribute('data-book-id');
    
    if (!bookId) {
        console.error("Lỗi: Không tìm thấy ID sách");
        return;
    }

    // Hiệu ứng nút bấm
    let originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-check"></i> Đã thêm';
    btn.classList.replace("btn-outline-primary", "btn-success");
    
    // LƯU VÀO LOCAL STORAGE
    let cart = JSON.parse(localStorage.getItem("shoppingCart")) || {};
    if (cart[bookId]) {
        cart[bookId]++; // Nếu có rồi thì tăng số lượng
    } else {
        cart[bookId] = 1; // Chưa có thì thêm mới
    }
    localStorage.setItem("shoppingCart", JSON.stringify(cart));

    updateCartBadge();

    setTimeout(() => {
        btn.innerHTML = originalText;
        btn.classList.replace("btn-success", "btn-outline-primary");
    }, 1000);
}

// Cập nhật số màu đỏ trên menu
function updateCartBadge() {
    let cart = JSON.parse(localStorage.getItem("shoppingCart")) || {};
    let totalItems = Object.values(cart).reduce((a, b) => a + b, 0);
    
    let badge = document.querySelector('.badge');
    if (badge) badge.innerText = totalItems;
}

// --- 3. XỬ LÝ TRANG GIỎ HÀNG (Cart Page Logic) ---
async function loadCartPage() {
    let cart = JSON.parse(localStorage.getItem("shoppingCart")) || {};
    let bookIds = Object.keys(cart);
    let tableBody = document.getElementById('cart-items');
    let cartContent = document.getElementById('cart-content');
    let emptyCart = document.getElementById('empty-cart');

    if (bookIds.length === 0) {
        cartContent.style.display = 'none';
        emptyCart.style.display = 'block';
        return;
    }

    // Gọi API lấy thông tin sách từ Server (để lấy giá chuẩn)
    let res = await fetch('/api/cart-details', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: bookIds})
    });
    let books = await res.json();

    // Render bảng
    tableBody.innerHTML = '';
    let grandTotal = 0;

    books.forEach(book => {
        let qty = cart[book.id];
        let total = book.price * qty;
        grandTotal += total;

        let row = `
            <tr>
                <td style="width: 100px;">
                    <img src="${book.image_url}" class="img-fluid rounded" style="width: 80px; height: 100px; object-fit: cover;">
                </td>
                <td class="align-middle">
                    <h6 class="mb-0 fw-bold">${book.title}</h6>
                    <small class="text-muted">${book.author}</small>
                </td>
                <td class="align-middle text-danger fw-bold">${book.price.toLocaleString()}đ</td>
                <td class="align-middle">
                    <div class="input-group input-group-sm" style="width: 100px;">
                        <button class="btn btn-outline-secondary" onclick="updateQty(${book.id}, -1)">-</button>
                        <input type="text" class="form-control text-center bg-white" value="${qty}" readonly>
                        <button class="btn btn-outline-secondary" onclick="updateQty(${book.id}, 1)">+</button>
                    </div>
                </td>
                <td class="align-middle fw-bold">${total.toLocaleString()}đ</td>
                <td class="align-middle">
                    <button class="btn btn-link text-danger p-0" onclick="removeItem(${book.id})"><i class="fas fa-trash"></i></button>
                </td>
            </tr>
        `;
        tableBody.innerHTML += row;
    });

    // Cập nhật tổng tiền
    document.getElementById('grand-total').innerText = grandTotal.toLocaleString() + 'đ';
}

function updateQty(id, change) {
    let cart = JSON.parse(localStorage.getItem("shoppingCart"));
    if (cart[id] + change > 0) {
        cart[id] += change;
    }
    localStorage.setItem("shoppingCart", JSON.stringify(cart));
    loadCartPage(); // Render lại bảng
    updateCartBadge();
}

function removeItem(id) {
    if(confirm("Bạn muốn xóa sách này?")) {
        let cart = JSON.parse(localStorage.getItem("shoppingCart"));
        delete cart[id];
        localStorage.setItem("shoppingCart", JSON.stringify(cart));
        loadCartPage();
        updateCartBadge();
    }
}

// --- 4. CHATBOT (Giữ nguyên) ---
function toggleChat() {
    let w = document.getElementById("chat-window");
    w.style.display = (w.style.display === "flex") ? "none" : "flex";
}

async function sendMessage() {
    let input = document.getElementById("user-input");
    let msg = input.value.trim();
    if (!msg) return;

    let body = document.getElementById("chat-body");
    body.innerHTML += `<div class="user-msg">${msg}</div>`;
    input.value = "";
    
    let loadingId = "loading-" + Date.now();
    body.innerHTML += `<div id="${loadingId}" class="bot-msg">...</div>`;
    body.scrollTop = body.scrollHeight;

    try {
        let res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: msg})
        });
        let data = await res.json();
        
        document.getElementById(loadingId).remove();
        body.innerHTML += `<div class="bot-msg">${data.response}</div>`;
        
        if (data.books && data.books.length > 0) {
            let suggestHtml = data.books.map(b => 
                `<div style="font-size:0.85em; margin-top:5px; border-left: 3px solid #0d6efd; padding-left:5px;">
                    <a href="/book/${b.id}"><b>${b.title}</b></a> - ${b.price}đ
                 </div>`
            ).join('');
            body.innerHTML += `<div class="bot-msg bg-white border">${suggestHtml}</div>`;
        }
    } catch (e) {
        document.getElementById(loadingId).innerText = "Lỗi kết nối server!";
    }
    body.scrollTop = body.scrollHeight;
}
document.getElementById("user-input").addEventListener("keypress", function(event) {
    if (event.key === "Enter") sendMessage();
});

// --- 5. LOGIC THANH TOÁN & VIETQR ---

// Cấu hình Tài khoản ngân hàng
const MY_BANK = {
    BANK_ID: "VCB",       
    ACCOUNT_NO: "1027766108", 
    TEMPLATE: "compact" 
};

// Chạy khi vào trang Checkout
if (window.location.pathname === '/checkout') {
    loadCheckout();
}

async function loadCheckout() {
    let cart = JSON.parse(localStorage.getItem("shoppingCart")) || {};
    let bookIds = Object.keys(cart);
    
    if (bookIds.length === 0) {
        window.location.href = "/cart"; // Giỏ trống thì đá về giỏ hàng
        return;
    }

    // Lấy thông tin sách để tính tổng tiền
    let res = await fetch('/api/cart-details', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: bookIds})
    });
    let books = await res.json();

    let totalAmount = 0;
    let listHtml = '';
    
    books.forEach(book => {
        let qty = cart[book.id];
        let price = book.price * qty;
        totalAmount += price;
        listHtml += `
            <li class="list-group-item d-flex justify-content-between lh-sm">
                <div>
                    <h6 class="my-0 small">${book.title}</h6>
                    <small class="text-muted">x ${qty}</small>
                </div>
                <span class="text-muted">${price.toLocaleString()}đ</span>
            </li>
        `;
    });

    // Hiển thị danh sách & Tổng tiền
    document.getElementById('order-summary').innerHTML = listHtml;
    document.getElementById('checkout-total').innerText = totalAmount.toLocaleString() + 'đ';
    document.getElementById('cart-count-checkout').innerText = bookIds.length;

    // --- TẠO MÃ QR TỰ ĐỘNG ---
    // 1. Tạo mã đơn hàng ngẫu nhiên
    let orderId = "DH" + Math.floor(Math.random() * 1000000);
    document.getElementById('order-id').innerText = orderId;

    // 2. Tạo Link VietQR
    // Cấu trúc: https://img.vietqr.io/image/<BANK>-<STK>-<TEMPLATE>.png?amount=<TIEN>&addInfo=<NOIDUNG>
    let qrUrl = `https://img.vietqr.io/image/${MY_BANK.BANK_ID}-${MY_BANK.ACCOUNT_NO}-${MY_BANK.TEMPLATE}.png?amount=${totalAmount}&addInfo=${orderId}`;

    // 3. Hiển thị ảnh
    let img = document.getElementById('vietqr-img');
    img.onload = () => {
        document.getElementById('loading-qr').style.display = 'none';
        img.style.display = 'block';
    };
    img.src = qrUrl;
}

async function finishOrder() {
    let cart = JSON.parse(localStorage.getItem("shoppingCart")) || {};
    let bookIds = Object.keys(cart);
    
    if (bookIds.length === 0) return;

    // Lấy thông tin từ form
    let name = document.getElementById('fullname').value;
    let phone = document.getElementById('phone').value;
    let address = document.getElementById('address').value;
    
    if (!name || !phone || !address) {
        alert("Vui lòng điền đầy đủ thông tin giao hàng!");
        return;
    }
    
    // Lấy thông tin sách để tính tổng tiền và chuẩn bị dữ liệu lưu
    let res = await fetch('/api/cart-details', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: bookIds})
    });
    let books = await res.json();
    
    let itemsToSave = [];
    let total = 0;
    
    books.forEach(b => {
        let q = cart[b.id];
        itemsToSave.push({ title: b.title, quantity: q, price: b.price });
        total += b.price * q;
    });

    // Gửi API lưu đơn hàng
    let orderRes = await fetch('/api/save-order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            name: name,
            phone: phone,
            address: address,
            total: total,
            items: itemsToSave
        })
    });
    
    let result = await orderRes.json();
    
    if (result.success) {
        alert("Thành công! Đơn hàng của bạn đã được ghi nhận.");
        localStorage.removeItem("shoppingCart");
        window.location.href = "/";
    } else {
        alert("Có lỗi xảy ra, vui lòng thử lại.");
    }
}