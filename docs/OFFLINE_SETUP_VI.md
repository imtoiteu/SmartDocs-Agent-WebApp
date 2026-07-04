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
scripts/setup_offline.sh                # tải TẤT CẢ mô hình offline (cần mạng, một lần)
scripts/setup_glm.sh --precache-layout  # (chỉ Apple Silicon) venv GLM + mô hình layout
scripts/check_offline.sh                # kiểm tra: dùng được / cần cài / đang dùng fallback
scripts/start.sh                        # chạy hệ thống
```

> **Luôn dùng `scripts/setup_offline.sh`, không dùng `python tools/setup_offline.py`.**
> Lệnh `python` trần thường trỏ tới Python HỆ THỐNG — không có dependency nào của
> ứng dụng — nên các bước tải thuần vẫn "thành công" nhưng VietOCR `config.yml`,
> Argos và embeddings bị bỏ qua âm thầm với lỗi `No module named 'vietocr' /
> 'PIL' / …`. Wrapper này tìm venv chính của SmartDocs đúng như `scripts/check.sh`
> (`$SMARTDOCS_PYTHON` → `<repo>/.venv` → `<repo>/../.venv`) và từ chối chạy với
> interpreter khác. Bản thân `tools/setup_offline.py` cũng in ra Python đang dùng
> và kết quả import `PIL` / `vietocr` / `argostranslate` / `sentence_transformers`
> — cảnh báo rõ nếu interpreter có vẻ sai. Cả bốn gói đều nằm trong
> `requirements.txt` của venv chính.

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

Bản kiểm tra **nhận biết tính đầy đủ**: một mô hình chỉ được coi là sẵn sàng khi có
snapshot HF hoàn chỉnh (config + weights) trong cache của ứng dụng
(`models/huggingface/`) — tải dở hoặc bị hủy giữa chừng sẽ báo **thiếu**, không phải
✅, nên kết quả kiểm tra luôn khớp với những gì ứng dụng thực sự nạp được. (Mô hình
layout GLM là ngoại lệ, được kiểm tra trong cache mặc định `~/.cache/huggingface`.)

---

## Khắc phục sự cố

- **Cài đặt in ra `No module named 'vietocr' / 'PIL' / 'argostranslate' / 'sentence_transformers'`** —
  bạn đã chạy tool bằng Python sai (hệ thống). Hãy dùng wrapper:
  ```bash
  scripts/setup_offline.sh
  ```
- **`check_offline.sh` báo thiếu mô hình bắt buộc ngay sau khi cài** — quá trình tải
  bị gián đoạn (hoặc một sự cố crash làm `setup_offline.py` dừng giữa chừng). Chỉ cần
  chạy lại; các phần đã xong sẽ được bỏ qua:
  ```bash
  scripts/setup_offline.sh
  ```
  `setup_offline.py` chạy bước PaddleOCR (dễ crash) **sau cùng**, nên VietOCR, Argos
  và các mô hình Qwen/PhoBERT/embedding đã nằm trên đĩa ngay cả khi Paddle gặp lỗi.
- **"No chat model could be loaded" dù trước đó báo ✅** — đó là bản kiểm tra cũ chỉ
  xét sự tồn tại thư mục. Cập nhật lại mã, chạy lại `check_offline.sh`; nếu giờ báo
  thiếu Local LLM, chạy `setup_offline.py`.
- **Thiếu dịch offline Argos / một cặp không cài được** — mỗi cặp cài độc lập nên các
  cặp khác vẫn thành công. Cài thủ công cặp lõi:
  ```bash
  argospm install translate-en_vi
  argospm install translate-vi_en
  # …hoặc bỏ file .argosmodel vào models/argos/packages/
  ```
  Dịch Google online vẫn hoạt động bình thường.

---

## Sau khi đã chuẩn bị: chạy hoàn toàn offline

Sau khi đã tải, giữ `OFFLINE=1` trong `.env`. Ứng dụng chỉ nạp mô hình
HuggingFace / Argos / Stanza từ `MODEL_DIR`, không chạm mạng. Sao chép toàn bộ thư
mục dự án (kèm `models/`) cùng HF cache mặc định sang máy air-gapped để chạy không cần mạng.
