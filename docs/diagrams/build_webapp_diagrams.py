#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generator for the SmartDocs **WebApp** diagram set (Vietnamese labels).

Reuses the layout/render core of build_diagrams.py (same directory) and emits
BOTH <name>.drawio (editable) and <name>.svg (publication) per diagram.

The set mirrors the DesktopApp diagram set (SmartDocs-Agent-DesktopApp,
docs/diagrams/build_desktop_diagrams.py) for the parts the two apps share —
Model Registry/Router, Local-only, key storage, URL policy — WITHOUT any
desktop-only concept (Tauri, UI gateway, runtime selector, runtime.json):

  W1  webapp-overall-architecture   Kiến trúc tổng thể WebApp
  W2  webapp-model-routing          Model Registry & Router theo tác vụ
  W3  webapp-privacy-local-only     Local-only · khóa API · chính sách URL

Run:  python3 build_webapp_diagrams.py
"""
import os

import build_diagrams as B

OUT = os.path.dirname(os.path.abspath(__file__))


def write(d):
    with open(os.path.join(OUT, d.name + '.drawio'), 'w', encoding='utf-8') as f:
        f.write(B.render_drawio(d))
    with open(os.path.join(OUT, d.name + '.svg'), 'w', encoding='utf-8') as f:
        f.write(B.render_svg(d))
    print('wrote', d.name + '.drawio', '+', d.name + '.svg', '(%dx%d)' % (d.w, d.h))


# ================================================================ W1
def w1_overall():
    d = B.Diagram('webapp-overall-architecture',
                  'W1 · Kiến trúc tổng thể SmartDocs WebApp', 1360, 800)
    # ── browser
    d.container('FE', 40, 64, 1280, 108,
                'Trình duyệt (máy khách) — SPA thuần JS, cùng cấu trúc UI với DesktopApp', 'fe')
    d.node('spa', 64, 104, 560, 52,
           'SPA chính + sidebar điều hướng\nTrang chủ · OCR · Sửa lỗi · Dịch · Tóm tắt · Tài liệu · SmartDocs AI · Agent · Cài đặt',
           'fe', parent='FE', fontsize=11)
    d.node('settings', 640, 104, 330, 52,
           'Trang Cài đặt\nAI models · Quyền riêng tư · Khóa cloud', 'fe', parent='FE', fontsize=11.5)
    d.node('agui', 986, 104, 310, 52,
           'Không gian Agent (/agent)\n+ Admin console (/admin)', 'fe', parent='FE', fontsize=11.5)
    # ── flask
    d.container('BE', 40, 196, 1280, 104,
                'Flask backend — một tiến trình trên server (app.py)', 'be')
    bx = B.row_x(64, 1296, 5, 232)
    bps = ['auth_bp\n/login · /api/auth/me',
           'app.py routes\n/api/upload · /api/ocr/* · /api/documents/*',
           'chat_bp · agent_bp\n/api/chat/* · /api/agent/*',
           'models_bp\n/api/models · self-hosted · routing',
           'settings_bp · admin_bp\n/api/settings/* · /admin/*']
    for i, lab in enumerate(bps):
        d.node('bp%d' % i, int(bx[i]), 236, 232, 52, lab, 'be', parent='BE', fontsize=10.5)
    # ── services
    d.container('SVC', 40, 324, 1280, 112, 'Dịch vụ xử lý (services/ · agent/)', 'ocr')
    sx = B.row_x(64, 1296, 4, 296)
    svcs = [('OCR pipeline\nPaddleOCR (legacy · modern) · VietOCR · GLM-OCR', 'ocr'),
            ('Dịch vụ AI\nsửa lỗi · dịch thuật · tóm tắt · viết lại AI', 'ai'),
            ('Chat / RAG\nSBERT / hashing + FAISS — trả lời kèm trích dẫn', 'rag'),
            ('AgentCore\nvòng lặp tool có giới hạn bước + thời gian', 'agent')]
    for i, (lab, key) in enumerate(svcs):
        d.node('sv%d' % i, int(sx[i]), 364, 296, 56, lab, key, parent='SVC', fontsize=11)
    # ── router band
    d.container('ROUTE', 40, 460, 1280, 96,
                'Model Router — llm_gateway.resolve(task): Chat/QA · Tóm tắt · Viết lại AI · Agent', 'agent')
    d.node('route1', 64, 500, 612, 44,
           'auto = hành vi cũ · model chỉ định được kiểm tra, KHÔNG bị thay ngầm', 'agent',
           parent='ROUTE', fontsize=11.5)
    d.node('route2', 700, 500, 596, 44,
           'Local-only ⇒ chặn cloud, cho phép cục bộ + self-hosted — lỗi rõ ràng', 'sec',
           parent='ROUTE', fontsize=11.5)
    # ── providers
    d.container('PROV', 40, 580, 760, 108, 'Nhà cung cấp mô hình (Model Registry)', 'llm')
    px = B.row_x(60, 780, 4, 168)
    provs = ['Qwen cục bộ\n(fallback cuối)', 'Self-hosted /v1\nOllama · vLLM ·\nllama.cpp · LM Studio',
             'Groq (cloud)\ncần khóa API', 'Gemini (cloud)\ncần khóa API']
    for i, lab in enumerate(provs):
        d.node('p%d' % i, int(px[i]), 618, 168, 60, lab, 'llm', parent='PROV', fontsize=10.5)
    d.node('db', 846, 592, 220, 96, 'SQLite + uploads + artifacts\n(trên server)', 'db', shape='cyl', fontsize=11)
    d.node('keys', 1096, 596, 224, 88, 'Kho khóa qua keyring\ntrên máy chủ chạy WebApp\n(không ghi khóa thô ra file)', 'sec',
           fontsize=10.5)
    # ── edges
    d.edge('FE', 'BE', label='HTTP(S) — phiên đăng nhập Flask-Login', srcside='bottom', dstside='top', color='#6C8EBF')
    d.edge('BE', 'SVC', srcside='bottom', dstside='top', color='#3F61A8')
    d.edge('SVC', 'ROUTE', label='mọi lời gọi LLM đều hỏi Router', srcside='bottom', dstside='top', color='#9673A6')
    d.edge('ROUTE', 'PROV', srcside='bottom', dstside='top', color='#D6B656')
    d.edge('SVC', 'db', dashed=True, srcside='bottom', dstside='top', color='#5A5A5A',
           waypoints=[(956, 566)])
    d.edge('settings', 'keys', label='khóa API', dashed=True, srcside='bottom', dstside='top', color='#B85450',
           waypoints=[(805, 184), (1330, 184), (1330, 570), (1208, 570)])
    d.node('scope', 40, 716, 1280, 48,
           'WebApp là ứng dụng chạy trên server — KHÔNG có Tauri shell, UI gateway, trình chọn runtime hay runtime.json (các phần đó thuộc riêng DesktopApp)',
           'note', fontsize=11.5)
    return d


# ================================================================ W2 (same shape as DesktopApp D6)
def w2_model_routing():
    d = B.Diagram('webapp-model-routing',
                  'W2 · Định tuyến mô hình AI theo tác vụ — Model Registry & Router (WebApp)', 1360, 700)
    d.container('SET', 40, 64, 620, 180, 'Cài đặt → AI models', 'fe')
    d.node('cfg1', 64, 104, 572, 48,
           'Định tuyến theo tác vụ (task_models):\nChat / Hỏi đáp tài liệu · Tóm tắt · Viết lại AI · Agent', 'fe',
           parent='SET', fontsize=11.5)
    d.node('cfg2', 64, 160, 572, 36, 'Model dự phòng (fallback_model) — tùy chọn, chính sách tường minh', 'fe',
           parent='SET', fontsize=11.5)
    d.node('cfg3', 64, 202, 572, 36, 'Mặc định: Automatic (auto) = giữ nguyên hành vi trước đây', 'fe',
           parent='SET', fontsize=11.5)
    d.container('CONS', 700, 64, 620, 180, 'Các consumer LLM (mọi lời gọi đều hỏi Router)', 'rag')
    d.node('u1', 724, 104, 286, 48, 'Chat / Hỏi đáp tài liệu', 'rag', parent='CONS', fontsize=12)
    d.node('u2', 1030, 104, 266, 48, 'Tóm tắt · Viết lại AI', 'rag', parent='CONS', fontsize=12)
    d.node('u3', 724, 168, 572, 48, 'Agent — lập kế hoạch & tổng hợp (tác vụ “agent”)', 'rag',
           parent='CONS', fontsize=12)
    d.container('ROUTE', 40, 270, 1280, 226, 'Model Router — llm_gateway.resolve(task)', 'agent')
    d.node('auto', 64, 310, 390, 76,
           'auto → chuỗi legacy (offline-first):\nGroq → Gemini → self-hosted → Qwen cục bộ\n(cloud chỉ khi CÓ khóa và ĐƯỢC phép)', 'agent',
           parent='ROUTE', fontsize=11)
    d.node('expl', 478, 310, 390, 76,
           'Model chỉ định → kiểm tra:\ncòn tồn tại · hỗ trợ tác vụ · đã cấu hình\nLocal-only ⇒ chặn model cloud', 'agent',
           parent='ROUTE', fontsize=11)
    d.node('err', 892, 310, 404, 76,
           'Không đạt ⇒ RouteError (thông báo rõ, xử lý được)\nKHÔNG âm thầm đổi model\nKHÔNG fallback ngầm sang cloud', 'sec',
           parent='ROUTE', fontsize=11)
    d.node('fit', 64, 406, 520, 56,
           'Vừa khít ngữ cảnh: cắt prompt theo context_limit\ncủa model (ưu tiên nội dung mới nhất)', 'agent',
           parent='ROUTE', fontsize=11)
    d.node('fb', 608, 406, 688, 56,
           'fallback_model (nếu đặt) chỉ được dùng khi vượt qua CÙNG các kiểm tra —\nfallback bị chặn không bao giờ được thay thế vào', 'agent',
           parent='ROUTE', fontsize=11)
    d.container('REG', 40, 522, 1280, 142, 'Model Registry — danh mục model (không bao giờ giữ khóa API)', 'llm')
    rx = B.row_x(64, 1296, 5, 236)
    regs = ['Bundled local\nQwen cục bộ (CPU)\nctx ~4096',
            'Managed local\nsnapshot HF (tùy chọn)',
            'Self-hosted (OpenAI-compatible)\nOllama · vLLM · llama.cpp\n· LM Studio',
            'Groq (cloud)\ncần khóa API · ctx 32k',
            'Gemini (cloud)\ncần khóa API · ctx 131k']
    for i, lab in enumerate(regs):
        d.node('r%d' % i, int(rx[i]), 562, 236, 76, lab, 'llm', parent='REG', fontsize=10.5)
    d.edge('SET', 'ROUTE', label='cấu hình', dashed=True, srcside='bottom', dstside='top', color='#6C8EBF')
    d.edge('CONS', 'ROUTE', label='resolve(task)', srcside='bottom', dstside='top', color='#82B366')
    d.edge('ROUTE', 'REG', label='tra cứu model → build provider (+ fit ngữ cảnh)', srcside='bottom', dstside='top', color='#D6B656')
    return d


# ================================================================ W3 (same shape as DesktopApp D7)
def w3_privacy():
    d = B.Diagram('webapp-privacy-local-only',
                  'W3 · Quyền riêng tư (WebApp) — Local-only · khóa API · chính sách URL', 1360, 650)
    d.container('LO', 40, 64, 620, 196, 'Local-only (Cài đặt → Quyền riêng tư)', 'sec')
    d.node('lo1', 64, 104, 572, 42, 'CHẶN Groq · Gemini — không dữ liệu nào được gửi lên cloud', 'sec',
           parent='LO', fontsize=11.5)
    d.node('lo2', 64, 154, 572, 42, 'CHO PHÉP model cục bộ và server tự host (mạng của bạn)', 'rag',
           parent='LO', fontsize=11.5)
    d.node('lo3', 64, 204, 572, 42, 'Không fallback ngầm sang cloud — báo lỗi rõ ràng, có hướng xử lý', 'sec',
           parent='LO', fontsize=11.5)
    d.container('KEY', 700, 64, 620, 196, 'Khóa API — CHỈ nằm trong kho khóa (keyring) trên server', 'be')
    d.node('k1', 724, 104, 572, 42, 'keyring trên máy chủ chạy WebApp (Keychain · Credential Manager · Secret Service)', 'be',
           parent='KEY', fontsize=11)
    d.node('k2', 724, 154, 572, 42, 'Trình duyệt chỉ nhận dạng che (4 ký tự cuối) — không bao giờ trả khóa đầy đủ', 'be',
           parent='KEY', fontsize=11.5)
    d.node('k3', 724, 204, 572, 42, 'Kho khóa không khả dụng → cảnh báo rõ + TỪ CHỐI lưu (không âm thầm)', 'be',
           parent='KEY', fontsize=11.5)
    d.table('url', 40, 296, 620, 'Chính sách URL — server LLM tự host', [
        ('HTTPS', 'luôn cho phép'),
        ('HTTP → localhost / 127.0.0.1 / ::1', 'cho phép'),
        ('HTTP → IP LAN riêng (10/8 · 172.16/12 · 192.168/16 · fc00::/7)', 'bật tùy chọn + xác nhận'),
        ('HTTP → địa chỉ công cộng hoặc hostname', 'từ chối'),
        ('URL chứa thông tin đăng nhập (user:pass@)', 'từ chối'),
        ('Hạ cấp HTTPS xuống HTTP', 'không bao giờ'),
    ], 'llm', rowh=24)
    d.table('probe', 700, 296, 620, 'Kiểm tra kết nối self-hosted — các trạng thái hiển thị', [
        ('Đã kết nối (connected) — server & model sẵn sàng', ''),
        ('Không truy cập được (unavailable)', ''),
        ('Xác thực thất bại (auth_failed — 401 · 403)', ''),
        ('Không tìm thấy model (model_not_found)', ''),
        ('Phản hồi không tương thích (incompatible)', ''),
        ('Hết thời gian chờ (timeout)', ''),
        ('Bị chính sách URL chặn (policy_blocked)', ''),
        ('Giới hạn ngữ cảnh quá nhỏ (context_insufficient)', ''),
    ], 'rag', rowh=24)
    d.node('note', 40, 546, 1280, 56,
           'Kiểm tra kết nối: GET /v1/models (kèm Bearer nếu có khóa) → nếu server không hỗ trợ, thử chat completion tối thiểu (max_tokens = 1).\nKHÔNG bao giờ gửi nội dung tài liệu ra ngoài khi kiểm tra.',
           'note', fontsize=11.5)
    return d


DIAGRAMS = [w1_overall, w2_model_routing, w3_privacy]

if __name__ == '__main__':
    for fn in DIAGRAMS:
        write(fn())
