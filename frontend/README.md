# Frontend

Ứng dụng Next.js độc lập cho AI Agent Superset Standalone. Giao diện dựng bằng shadcn/ui, hỗ trợ sáng/tối và bố cục responsive. Trang chính quản lý kết nối database; trang chi tiết có các mục Tổng quan, Metadata, Từ điển và Cài đặt. Mục Từ điển cho phép mô tả bảng và cột, lưu thay đổi, tự động điền bằng AI.

```powershell
cd frontend
npm install
npm run dev
```

Mở `http://localhost:3000`. Frontend gọi backend tại `NEXT_PUBLIC_API_URL` (mặc định `http://localhost:8000`, xem `.env.example`). Hiện chưa có trang đăng nhập hoặc middleware xác thực.

Form thêm/sửa kết nối cho phép nhập từng thành phần hoặc dán URI đầy đủ. Mật khẩu và URI không được đọc lại từ backend sau khi lưu.

Xem [handbook frontend](../docs/handbook/frontend/README.md) để biết các luồng giao diện và API tương ứng.
