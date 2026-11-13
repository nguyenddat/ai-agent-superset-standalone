# Frontend

Ứng dụng Next.js độc lập cho AI Agent Superset Standalone. Giao diện dựng bằng shadcn/ui: một trang quản lý kết nối database, hỗ trợ sáng/tối và bố cục responsive. Nội dung và mã nguồn tại đây được viết cho nghiệp vụ database connection của dự án.

```powershell
cd frontend
npm install
npm run dev
```

Mở `http://localhost:3000`. Frontend gọi backend tại `NEXT_PUBLIC_API_URL` (mặc định `http://localhost:8000`, xem `.env.example`). Hiện chưa có trang đăng nhập hoặc middleware xác thực.

Form thêm/sửa kết nối cho phép nhập từng thành phần hoặc dán URI đầy đủ. Mật khẩu và URI không được đọc lại từ backend sau khi lưu.
