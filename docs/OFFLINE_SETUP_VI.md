# Cài đặt Offline / Clean-Clone (Tiếng Việt)

SmartDocs-Agent theo hướng **offline-first**: với `OFFLINE=1` (mặc định), mọi mô
hình AI chỉ nạp từ cache cục bộ — **không tải gì lúc chạy**. Do đó một bản clone
mới phải được **chuẩn bị một lần khi có mạng** thì các tính năng AI mới hoạt động.
Tài liệu này liệt kê chính xác mỗi tính năng cần mô hình nào, cách tải, và cách
kiểm tra mức sẵn sàng.

> Ứng dụng web, đăng nhập, tải lên, quản lý tài liệu và **sửa lỗi văn bản cơ bản**
> chạy được ngay, không cần tải mô hình. Phần dưới đây nói về các tính năng AI
> (các engine OCR ngoài Paddle, chat, viết lại, dịch, GLM).

---

## Tóm tắt — chuẩn bị một lần cho bản clone sạch

```bash
scripts/setup.sh                        # venv chính + deps + .env + thư mục
python tools/setup_offline.py           # tải TẤT CẢ mô hình offline (cần mạng, một lần)
scripts/setup_glm.sh --precache-layout  # (chỉ Apple Silicon) venv GLM + mô hình layout
scripts/check_offline.sh                # kiểm tra: dùng được / cần cài / đang dùng fallback
scripts/start.sh                        # chạy hệ thống
```

`tools/setup_offline.py` phải chạy **trong virtualenv chính** (cần `torch`,
`transformers`, `paddleocr`, `vietocr`, `argostranslate`). Nếu dùng `scripts/`,
hãy kích hoạt venv trước hoặc chạy bằng Python của venv:

```bash
.venv/bin/python tools/setup_offline.py         # hoặc ../.venv/bin/python …
```

---

## Mỗi tính năng cần gì

| Tính năng | Cần (cục bộ) | Được tải bởi | Nếu thiếu → |
|---|---|---|---|
| Paddle OCR Legacy / Modern | cache mô hình PaddleX | `setup_offline.py` (hoặc lần OCR đầu có mạng) | tải ở lần chạy đầu (cần mạng một lần) |
| **VietOCR** | `models/vietocr/config.yml` **+** `vgg_transformer.pth` | `setup_offline.py` | OCR trả lỗi rõ ràng "chạy setup_offline" |
| **GLM OCR** | `.venv-sdk` + `mlx_config.yaml` (`pipeline.layout.model_dir`) + PP-DocLayoutV3 trong HF cache mặc định + máy chủ MLX | `setup_glm.sh --precache-layout` | lỗi "pipeline.layout.model_dir is required" / thông báo server chưa chạy |
| **AI Chat / AI Rewrite / Agent** | LLM cục bộ **Qwen 2.5 1.5B** (mặc định, `CHAT_MODEL` = `QWEN_MODEL` = `FALLBACK_CHAT_MODEL`) | `setup_offline.py` | "No chat model could be loaded" |
| Tóm tắt PhoBERT | `vinai/phobert-base-v2` | `setup_offline.py` | **fallback** sang TF-IDF trích xuất (vẫn chạy) |
| Embeddings RAG | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | `setup_offline.py` | **fallback** sang truy hồi char-hash (vẫn chạy) |
| **Dịch offline** | gói Argos trong `models/argos/packages/` | `setup_offline.py` | vẫn dịch online bằng Google |

Lưu ý:

- **LLM cục bộ mặc định = Qwen 2.5 1.5B-Instruct.** Chat, viết lại AI và provider
  cục bộ của agent đều dùng nó, nên `setup_offline.py` chỉ tải **một lần**. Các mô
  hình lớn hơn (vd 3B) **không** phải mặc định và **không** được tải trừ khi bạn đặt
  `CHAT_MODEL`/`QWEN_MODEL` trong `.env` — 3B là tuỳ chọn, tự bật. Thiếu 3B **không**
  khiến chat/rewrite báo hỏng.
- **Mô hình layout GLM nằm trong HF cache MẶC ĐỊNH** (`~/.cache/huggingface`), không
  phải trong `models/`. `glm_adapter.py` cố ý bỏ `HF_HOME` trước khi gọi `glmocr`,
  nên checkpoint layout phải được cache ở đó. `setup_glm.sh --precache-layout` tải
  đúng chỗ; sau đó chạy được với `HF_HUB_OFFLINE=1`.

---

## Cấu hình layout GLM self-hosted

Chế độ self-hosted của `glmocr` **bắt buộc** có `pipeline.layout.model_dir`.
`setup_glm.sh` ghi giá trị này vào `GLM-OCR/mlx_config.yaml`:

```yaml
pipeline:
  maas: { enabled: false }
  ocr_api: { api_host: localhost, api_port: 8080, model: mlx-community/GLM-OCR-bf16, api_mode: openai, verify_ssl: false }
  layout:
    model_dir: PaddlePaddle/PP-DocLayoutV3_safetensors   # HF id hoặc thư mục cục bộ
    device: cpu
```

- Đổi checkpoint qua `GLM_LAYOUT_MODEL_DIR` trong `.env` (HF id hoặc đường dẫn tuyệt đối).
- Nếu `mlx_config.yaml` **cũ** (tạo trước bản sửa này) thiếu `layout.model_dir`,
  `setup_glm.sh` sẽ tạo lại (sao lưu bản cũ thành `mlx_config.yaml.bak`).

---

## Kiểm tra mức sẵn sàng

```bash
scripts/check_offline.sh
```

Báo cáo theo từng tính năng: **dùng được ngay**, **cần cài online**, hoặc **đang
dùng fallback** — cùng Python/Pillow chính, config/weights VietOCR, cache Paddle,
cả hai venv GLM, giá trị `pipeline.layout.model_dir`, và mô hình layout GLM đã cache
hay chưa. Script không thay đổi gì.

`scripts/check.sh` lo phần runtime/venv và trỏ sang đây cho ma trận mô hình.

---

## Sau khi đã chuẩn bị: chạy hoàn toàn offline

Sau khi đã tải, giữ `OFFLINE=1` trong `.env`. Ứng dụng chỉ nạp mô hình
HuggingFace / Argos / Stanza từ `MODEL_DIR`, không chạm mạng. Sao chép toàn bộ thư
mục dự án (kèm `models/`) cùng HF cache mặc định sang máy air-gapped để chạy không cần mạng.
