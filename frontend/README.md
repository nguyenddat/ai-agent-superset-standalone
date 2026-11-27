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

## Cấu trúc và lệnh

```
app/          route (App Router) và app/api/own-knowledge (lớp proxy)
features/     text2sql (tab "Hỏi dữ liệu", dùng /chat/stream), own-knowledge, database-connections, glossary-management,
              expert-rule-management, data-dictionary, metric-management, business-model, data-lineage
components/, lib/
```

| Lệnh | Việc làm |
|---|---|
| `npm run dev` | Dev server cổng 3000 |
| `npm run test:charts` | Test phần biểu đồ |
| `npx next build` | Build production (chạy tay, không nằm trong `scripts/verify.sh`) |

Biến môi trường: `NEXT_PUBLIC_API_URL` (build arg trong `compose.yaml`, mặc định `http://localhost:8000`) cho trình duyệt và `API_URL` (trong compose: `http://backend:8000`) cho phía server. Cả stack: [README gốc](../README.md).
