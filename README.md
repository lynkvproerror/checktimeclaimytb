# YouTube Claim Checker - Kiểm Tra File WAV Bị Claim

Công cụ tự động hóa kiểm tra bản quyền (Content ID claim) cho các file âm thanh WAV/MP3 trên YouTube Studio bằng hình ảnh OCR / API.

## Tính năng chính

- **Kiểm tra Claim qua OCR & YouTube API**: Nhận diện thông báo bản quyền, so khớp tên bài hát và mốc thời gian bị claim.
- **Workflow Studio Unified**: Hỗ trợ tạo video kiểm tra hàng loạt, ghép nhạc màn hình đen / hình ảnh, render video và tải lên YouTube chế độ Unlisted/Private để kiểm tra.
- **Báo cáo chi tiết**: Xuất kết quả kiểm tra theo tracklist, độ trùng khớp (matching percent) và thời lượng vi phạm.

## Cấu trúc thư mục

- `claim_checker_v4.0.0_unified.pyw`: Giao diện chính YouTube Claim Workflow Studio v4.0.0.
- `claim_checker_v3.9.2.pyw`: Bản v3.9.2 trước đó.
- `workflow_render_engine.py`: Động cơ render video và chuẩn bị workflow upload.
- `youtube_api_pool.py`: Xử lý kết nối, xác thực và gọi API YouTube Data v3.
- `matching_settings.json`: Cấu hình ngưỡng so khớp tên và độ trùng lặp thời gian.
- `youtube_api_settings.example.json`: File mẫu cấu hình OAuth & Upload YouTube.
- `generator_settings.example.json`: File mẫu cấu hình tạo video test.
- `v1/`, `v2/`, `v3/`: Các phiên bản phát triển trước đây.

## Cài đặt & Sử dụng

### 1. Yêu cầu hệ thống
- Python 3.8+
- Tesseract OCR (nếu sử dụng tính năng OCR từ màn hình YouTube Studio)

### 2. Cài đặt thư viện
```bash
pip install -r requirements.txt
```

### 3. Cấu hình
1. Đổi tên hoặc sao chép `youtube_api_settings.example.json` thành `youtube_api_settings.json`.
2. Đặt file OAuth Client Secret từ Google Cloud Console vào thư mục dự án và cập nhật đường dẫn tương ứng.

### 4. Khởi chạy
- Chạy file `run_app.bat` hoặc:
```bash
python claim_checker_v4.0.0_unified.pyw
```
