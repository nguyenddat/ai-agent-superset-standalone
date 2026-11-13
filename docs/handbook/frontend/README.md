# Frontend

**Trạng thái:** đã triển khai. Frontend gọi API kết nối và metadata của module [`database_connection`](../modules/database_connection/README.md). Trang `/` liệt kê kết nối; bấm vào một kết nối sẽ mở trang chi tiết của kết nối đó.

`frontend/` được khởi tạo bằng `npx create-next-app@latest` (Next.js 16.4.6, App Router, TypeScript, Tailwind CSS, ESLint, npm). Giao diện dùng [shadcn/ui](https://ui.shadcn.com) (style `radix-nova`, icon `lucide-react`): header cố định có nút chuyển sáng/tối, không có sidebar.

## Cấu trúc

- `app/`: layout và các route.
  - `/`: số kết nối (tổng, đang hoạt động, tạm dừng) ở trên, danh sách kết nối ở dưới.
  - `/connections/[id]`: trang chi tiết, có thanh điều hướng ngang gồm ba mục. `Tổng quan` hiển thị thông tin kết nối và biểu đồ cột dọc nhóm theo schema, mỗi nhóm gồm cột số bảng và số view. `/metadata` xem lần lượt schema, bảng/view và cột. `/settings` sửa hoặc xóa kết nối. `layout.tsx` bọc phần đầu trang trong `Suspense` vì `useParams` trên route động cần điều này khi bật `cacheComponents`.
- `components/ui/`: component shadcn, thêm bằng `npx shadcn@latest add <tên>`; cấu hình tại `components.json`.
- `components/layout/`: shell và header.
- `lib/api.ts`: `apiFetch` gọi backend tại `NEXT_PUBLIC_API_URL` (mặc định `http://localhost:8000`), ném `ApiError` mang mã HTTP và `detail` của backend.
- `features/database-connections/`:
  - `types.ts`: kiểu dữ liệu khớp schema Pydantic của backend, giữ nguyên tên trường `snake_case`.
  - `api.ts`: hook SWR để đọc dữ liệu và các hàm ghi (tạo, sửa, xóa, kiểm tra, đồng bộ); sau khi ghi, hàm tự làm mới cache liên quan.
  - `connections-view.tsx`, `connection-form-dialog.tsx`, `delete-connection-dialog.tsx`: nội dung trang `/`, gồm tìm kiếm, sắp xếp, dạng lưới/danh sách, thêm, sửa, bật/tắt, xóa và đồng bộ.
  - `connection-stats.tsx`: ba thẻ số liệu kết nối ở đầu trang.
  - `connection-format.tsx`, `sync-with-toast.ts`: định dạng ngày, nhãn trạng thái và thao tác đồng bộ kèm thông báo, dùng chung cho danh sách và trang chi tiết.
  - `detail/`: phần đầu trang chi tiết kèm thanh điều hướng (`connection-layout.tsx`) và nội dung từng mục (`connection-overview.tsx`, `metadata-explorer.tsx`, `connection-settings.tsx`). Biểu đồ dùng component `chart` của shadcn (Recharts), màu lấy từ token `--chart-1` (xanh) và `--chart-2` (cam), đã kiểm tra phân biệt được với người mù màu trên cả nền sáng và tối. Các biểu đồ khác sẽ được thêm dần vào mục `Tổng quan`.

Không có route login, middleware xác thực hay tích hợp Keycloak. Dữ liệu được gọi từ trình duyệt nên backend phải cho phép CORS với origin của frontend. Lỗi `409` khi tạo hoặc sửa được hiển thị ở ô tên; lỗi `422` và `503` hiển thị ở ô URI; các lỗi khác hiển thị dạng thông báo. URI chỉ được gửi lên, không bao giờ được đọc lại. Khi sửa kết nối, frontend chỉ gửi những trường đã thay đổi.

Form kết nối có hai cách nhập: từng thành phần (máy chủ, cổng, database, người dùng, mật khẩu) hoặc URI đầy đủ. Chế độ từng thành phần ghép URI `dialect+driver://...` ở trình duyệt và mã hóa ký tự đặc biệt trong thông tin đăng nhập, tên database trước khi gọi cùng API hiện có. Khi sửa, người dùng có thể để trống thông tin kết nối để chỉ đổi tên hoặc trạng thái; URI cũ không được đọc từ backend.

Thông báo dùng `sonner`; giao diện sáng/tối dùng `next-themes`, lưu lựa chọn trong `localStorage` với khóa `theme`.

Sao chép `frontend/.env.example` thành `frontend/.env.local` nếu backend không chạy ở `http://localhost:8000`. Chạy `npm install`, `npm run dev` trong `frontend/`. Kiểm tra bằng `npm run lint`, `npm run typecheck` và `npm run build`.
