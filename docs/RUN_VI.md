# Chạy SmartDocs-Agent (Tiếng Việt)

Hướng dẫn thực hành để chạy SmartDocs-Agent trên máy cục bộ bằng các script
trong `scripts/`. Các script tự động tìm virtualenv Python và đường dẫn dự án —
**bạn không cần kích hoạt venv hay `cd` vào đâu cả.**

> GLM OCR là **tuỳ chọn** và chỉ chạy trên Apple Silicon (MLX). Ứng dụng web và
> các engine Legacy / VietOCR / Modern vẫn hoạt động bình thường khi không có GLM.

---

## 1. Cài đặt lần đầu

```bash
scripts/setup.sh
```

Script này sẽ:

- tìm virtualenv có sẵn (`./.venv` hoặc `../.venv` ở thư mục cha), hoặc tạo mới
  `./.venv` nếu chưa có — không bao giờ ghi đè venv đang dùng được;
- cài `requirements.txt` vào venv đó;
- tạo `.env` từ `.env.example` nếu bạn chưa có;
- tạo các thư mục runtime `logs/`, `uploads/`, `artifacts/`.

## 2. Kiểm tra môi trường

```bash
scripts/check.sh
```

Báo cáo Python + venv, các thư viện quan trọng, trạng thái cổng web và GLM, và
tình trạng "sức khoẻ" của SmartDocs cùng (tuỳ chọn) máy chủ GLM. Script này
không thay đổi gì và không báo lỗi chỉ vì GLM đang tắt.

## 3. Khởi động

### Toàn bộ hệ thống (khuyến nghị)

```bash
scripts/start.sh
```

- Khởi động máy chủ GLM ở chế độ nền **nếu** `ENABLE_GLM=true` và venv MLX có
  sẵn; nếu không sẽ in cảnh báo rõ ràng và **vẫn tiếp tục** chạy mà không cần GLM.
- Khởi động ứng dụng web ở chế độ tiền cảnh. Nhấn **Ctrl-C** để dừng web (và cả
  GLM, nếu lệnh này đã khởi động nó).

Mở **http://localhost:5002** (hoặc `SMARTDOCS_PORT` của bạn) và đăng nhập.

### Từng dịch vụ riêng lẻ

```bash
scripts/start_web.sh        # chỉ ứng dụng web (tiền cảnh)
scripts/start_web.sh -b     # chỉ ứng dụng web (chạy nền -> logs/web.log)

scripts/start_glm.sh        # chỉ máy chủ GLM (tiền cảnh)
scripts/start_glm.sh -b     # chỉ máy chủ GLM (chạy nền -> logs/glm.log)
```

## 4. Dừng

```bash
scripts/stop.sh             # dừng web + GLM chạy nền (chỉ tiến trình do script khởi động)
scripts/stop.sh web         # chỉ dừng web
scripts/stop.sh glm         # chỉ dừng GLM
scripts/stop.sh --force     # dừng luôn tiến trình đang giữ cổng (dùng cẩn thận)
```

Mặc định `stop.sh` chỉ dừng tiến trình do chính script khởi động (theo dõi qua
file PID trong `logs/`). Nó **không** giết một tiến trình lạ chỉ vì tiến trình đó
đang giữ cổng — quan trọng trên máy dùng chung. Dùng `--force` để dừng cả tiến
trình cũ/không được theo dõi trên cổng. Dịch vụ chạy tiền cảnh (không có `-b`)
thì dừng bằng **Ctrl-C**.

---

## Cấu hình (`.env`)

Sao chép `.env.example` thành `.env` rồi chỉnh sửa. Các tham số runtime mà
script sử dụng:

| Biến             | Mặc định                         | Ý nghĩa                                              |
|------------------|----------------------------------|-----------------------------------------------------|
| `SMARTDOCS_PORT` | `5002`                           | Cổng web (script ánh xạ sang biến `PORT` của app).  |
| `GLM_PORT`       | `8080`                           | Cổng máy chủ mô hình GLM.                            |
| `GLM_MODEL`      | `mlx-community/GLM-OCR-bf16`     | Nhãn mô hình dùng cho kiểm tra sức khoẻ.            |
| `ENABLE_GLM`     | `true`                           | `start.sh` có cố khởi động GLM hay không.            |

Mọi biến khác trong `.env` (mô hình, thiết bị, API key, chế độ offline) được app
đọc trực tiếp — xem chú thích trong `.env.example`.

---

## Kiểm thử khi CÓ và KHÔNG có GLM

**Không có GLM** (mọi máy, kể cả không phải Mac):

```bash
ENABLE_GLM=false scripts/start.sh
```

App khởi động bình thường. Trong giao diện, Legacy PaddleOCR, PaddleOCR Modern và
VietOCR đều chạy được. Khi chọn engine **GLM OCR** sẽ hiện thông báo lỗi rõ ràng
yêu cầu bật máy chủ GLM — không có gì bị sập.

**Có GLM** (chỉ Apple Silicon):

```bash
scripts/start_glm.sh -b      # bật máy chủ mô hình (lần đầu sẽ nạp mô hình)
scripts/check.sh             # kỳ vọng: "GLM health: 200"
scripts/start_web.sh         # hoặc scripts/start.sh để bật cả hai
```

Sau đó trong giao diện: tab OCR → tải ảnh lên → chọn **🧠 GLM OCR (Structured)** →
Run OCR.

---

## Xử lý sự cố

- **`Flask is not installed`** — chạy `scripts/setup.sh`.
- **`Port 5002 already in use`** — SmartDocs đang chạy rồi; dùng `scripts/stop.sh`
  hoặc đặt `SMARTDOCS_PORT` khác.
- **GLM health không phải 200** — kiểm tra `scripts/start_glm.sh` còn chạy và mô
  hình đã nạp xong (xem `logs/glm.log`). GLM chỉ chạy trên Apple Silicon.
- **Nhật ký (logs)** — dịch vụ chạy nền ghi vào `logs/web.log` và `logs/glm.log`.
