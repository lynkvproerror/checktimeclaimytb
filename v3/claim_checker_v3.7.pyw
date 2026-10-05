"""
YouTube Claim Checker v3.7
Logic Đồng Bộ Hoàn Toàn - OCR và Text Input sử dụng cùng 1 pipeline

Author: AI Assistant
Version: 3.1.0
Date: 2024
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import re
from datetime import timedelta
from pathlib import Path
import pytesseract
from PIL import Image, ImageGrab, ImageEnhance, ImageFilter
import os
import difflib


# ============================================================================
# UNIFIED CLAIM PARSER - Core Logic Module
# ============================================================================

class UnifiedClaimParser:
    """
    Parser thống nhất cho cả OCR và Text Input
    Đảm bảo logic xử lý 100% giống nhau
    """
    
    def __init__(self):
        # ✅ CHUNG - Bộ patterns MỞ RỘNG cho YouTube
        self.timestamp_patterns = [
            # === PATTERNS CŨ (giữ nguyên) ===
            r'(\d{1,2}):(\d{2}):(\d{2})\s*[——–\-]\s*(\d{1,2}):(\d{2}):(\d{2})',
            r'(\d{1,2}):(\d{2}):(\d{2})\s+[——–\-]\s+(\d{1,2}):(\d{2}):(\d{2})',
            r'(\d{1,2}):(\d{2}):(\d{2})[——–\-](\d{1,2}):(\d{2}):(\d{2})',
            
            # === PATTERNS MỚI cho YouTube ===
            # Pattern 4: YouTube với | separator và em dash
            r'(\d{1,2}):(\d{2}):(\d{2})\s*[——–\-]\s*(\d{1,2}):(\d{2}):(\d{2})\s*\|',
            
            # Pattern 5: Timestamp dính liền hoàn toàn (không space, không separator)
            r'(\d{1,2}):(\d{2}):(\d{2})([——–\-])(\d{1,2}):(\d{2}):(\d{2})([——–\-])(\d{1,2}):(\d{2}):(\d{2})',
            
            # Pattern 6: Format ngắn MM:SS (không có giờ)
            r'(\d{1,2}):(\d{2})\s*[——–\-]\s*(\d{1,2}):(\d{2})',
            
            # Pattern 7: Có thể có space hoặc không có space sau dấu gạch
            r'(\d{1,2}):(\d{2}):(\d{2})[——–\-]\s*(\d{1,2}):(\d{2}):(\d{2})',
        ]
        
        # ✅ Noise patterns (giữ nguyên + thêm)
        self.noise_patterns = [
            # Tiếng Việt
            r'Nội dung được tìm thấy trong',
            r'Nội dung',
            r'được tìm thấy',
            r'Loại nội dung',
            r'Video sử dụng giai điệu',
            r'Các bên xác nhận',
            r'Giai điệu hoặc bài hát',
            
            # Tiếng Anh
            r'Content found in',
            r'Content type',
            r'Melody or lyrics',
            r'Video uses this song\'s melody or lyrics',
            r'Video uses this song',
            r'Verified parties',
            r'Content',
            r'found in',
        ]
    
    def normalize_text(self, text, source_type="unknown"):
        """
        ✅ v3.7: NÂNG CẤP - Xử lý đặc biệt cho timestamps dính liền
        
        Args:
            text: Raw text từ OCR hoặc user paste
            source_type: "ocr" hoặc "text"
            
        Returns:
            Normalized text
        """
        # BƯỚC 1: Loại bỏ ALL noise text
        unwanted_patterns = [
            r'Video sử dụng giai điệu',
            r'Các bên xác nhận',
            r'Loại nội dung',
        ]
        for pattern in unwanted_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # BƯỚC 2: Chuẩn hóa Unicode dashes về hyphen thống nhất
        text = text.replace('\u2014', '—')  # Em dash
        text = text.replace('\u2013', '—')  # En dash  
        text = text.replace('\u2012', '—')  # Figure dash
        text = text.replace('–', '—')       # En dash (visual)
        text = text.replace('-', '—')       # Hyphen
        
        # ✅ BƯỚC 3: XỬ LÝ TIMESTAMPS DÍNH LIỀN - NÂNG CẤP v3.7
        # Case 1: "4:15" + "1:54:41" (MM:SS + H:MM:SS)
        # Tìm: số cuối của timestamp trước + số đầu của timestamp sau
        text = re.sub(
            r'(\d{1,2}:\d{2})(\d{1,2}:\d{2}:\d{2})',
            r'\1 | \2',
            text
        )
        
        # Case 2: "1:15:30" + "2:20:45" (H:MM:SS + H:MM:SS)
        text = re.sub(
            r'(\d{1,2}:\d{2}:\d{2})(\d{1,2}:\d{2}:\d{2})',
            r'\1 | \2',
            text
        )
        
        # Case 3: "4:151:54:41" → "4:15 | 1:54:41"
        # Pattern đặc biệt: SSHH:MM:SS
        text = re.sub(
            r'(\d{2})(\d{1,2}:\d{2}:\d{2})',
            r'\1 | \2',
            text
        )
        
        # Chạy lại 2 lần để catch các case phức tạp
        text = re.sub(
            r'(\d{1,2}:\d{2})(\d{1,2}:\d{2}:\d{2})',
            r'\1 | \2',
            text
        )
        
        text = re.sub(
            r'(\d{1,2}:\d{2}:\d{2})(\d{1,2}:\d{2}:\d{2})',
            r'\1 | \2',
            text
        )
        
        # BƯỚC 4: Chuẩn hóa whitespace
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Chuẩn hóa spaces trong mỗi dòng
            line = re.sub(r'[ \t]+', ' ', line).strip()
            cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)
        
        # BƯỚC 5: Clean up pipes thừa
        text = re.sub(r'\|\s*\|', '|', text)  # Remove double pipes
        text = re.sub(r'^\s*\|\s*', '', text)  # Remove leading pipe
        text = re.sub(r'\s*\|\s*$', '', text)  # Remove trailing pipe
        
        # ✅ BƯỚC 6: Xử lý separator lines (===, ---)
        lines = text.split('\n')
        filtered_lines = []
        for line in lines:
            # Bỏ qua dòng toàn bộ là dấu =, -, hoặc khoảng trắng
            if re.match(r'^[=\-\s]{10,}$', line):
                continue
            filtered_lines.append(line)
        
        text = '\n'.join(filtered_lines)
        
        return text.strip()
    
    def extract_song_name(self, text, source_type="unknown"):
        """
        ✅ v3.7: Extract tên bài hát - LINH HOẠT HƠN
        
        Returns:
            (song_name, song_confidence) tuple - Trả về 1 bài đầu tiên tìm thấy
        """
        lines = text.split('\n')
        
        for i, line in enumerate(lines[:15]):  # Check 15 dòng đầu
            line = line.strip()
            
            # Bỏ qua dòng trống hoặc quá ngắn
            if len(line) < 3:
                continue
            
            # Bỏ qua dòng chỉ có timestamps
            if re.match(r'^[\d:–—\-\|\s]+$', line):
                continue
            
            # Bỏ qua noise keywords
            if any(noise in line.lower() for noise in [
                'nội dung', 'được tìm thấy', 'content found',
                'loại nội dung', 'video sử dụng', 'các bên xác nhận'
            ]):
                continue
            
            # ✅ KIỂM TRA: Dòng tiếp theo có phải "Nội dung..." không?
            # Nếu có → chắc chắn đây là tên bài
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip().lower()
                if 'nội dung' in next_line or 'content found' in next_line:
                    confidence = 100 if source_type == "text" else 85
                    print(f"🎵 Found song with 'Nội dung...' marker: '{line}'")
                    return (line, confidence)
            
            # ✅ FALLBACK: Nếu không có marker, vẫn coi dòng đầu tiên hợp lệ là tên bài
            # (Tương tự V3.2)
            confidence = 100 if source_type == "text" else 70
            print(f"🎵 Found song (no marker): '{line}' - confidence: {confidence}%")
            return (line, confidence)
        
        print("⚠️ No song name found, returning 'Unknown'")
        return ("Unknown", 0)  # ✅ FIX: Thêm dấu đóng ngoặc
    
    def extract_timestamps(self, text):
        """
        ✅ v3.7: NÂNG CẤP - Extract timestamps với YOUTUBE support
        
        Returns:
            List of (start_seconds, end_seconds) tuples
        """
        timestamps = []
        
        # BƯỚC 1: Thử TẤT CẢ patterns
        for pattern_idx, pattern in enumerate(self.timestamp_patterns):
            matches = re.findall(pattern, text)
            
            for match in matches:
                try:
                    # Handle different pattern formats
                    if len(match) == 6:  # Standard H:M:S - H:M:S
                        start_h, start_m, start_s, end_h, end_m, end_s = map(int, match)
                    
                    elif len(match) == 4:  # Short format M:S - M:S
                        start_m, start_s, end_m, end_s = map(int, match)
                        start_h = 0
                        end_h = 0
                    
                    elif len(match) > 6:  # Complex pattern with extra captures
                        # Extract only the numeric parts
                        numbers = [int(x) for x in match if x.isdigit() or (isinstance(x, str) and x.replace(':', '').isdigit())]
                        if len(numbers) >= 6:
                            start_h, start_m, start_s = numbers[0:3]
                            end_h, end_m, end_s = numbers[3:6]
                        else:
                            continue
                    else:
                        continue
                    
                    start_seconds = start_h * 3600 + start_m * 60 + start_s
                    end_seconds = end_h * 3600 + end_m * 60 + end_s
                    
                    # ✅ VALIDATION CHUNG
                    if not self._is_valid_timestamp(start_seconds, end_seconds):
                        continue
                    
                    timestamps.append((start_seconds, end_seconds))
                    
                except (ValueError, IndexError) as e:
                    continue
        
        # BƯỚC 2: Xử lý case đặc biệt - timestamps nằm trên nhiều dòng
        # VD: "2:34:30 -\n2:37:08"
        lines = text.split('\n')
        for i in range(len(lines) - 1):
            combined = lines[i].strip() + ' ' + lines[i+1].strip()
            for pattern in self.timestamp_patterns:
                matches = re.findall(pattern, combined)
                for match in matches:
                    try:
                        if len(match) == 6:
                            start_h, start_m, start_s, end_h, end_m, end_s = map(int, match)
                            start_seconds = start_h * 3600 + start_m * 60 + start_s
                            end_seconds = end_h * 3600 + end_m * 60 + end_s
                            
                            if self._is_valid_timestamp(start_seconds, end_seconds):
                                timestamps.append((start_seconds, end_seconds))
                    except:
                        continue
        
        # BƯỚC 3: Loại bỏ duplicates và sort
        timestamps = list(set(timestamps))
        timestamps.sort(key=lambda x: x[0])
        
        # BƯỚC 4: Merge timestamps gần nhau (tolerance 3 giây)
        merged_timestamps = []
        for ts in timestamps:
            if not merged_timestamps:
                merged_timestamps.append(ts)
            else:
                last = merged_timestamps[-1]
                # Nếu gần nhau, chỉ giữ 1
                if abs(ts[0] - last[0]) <= 3 and abs(ts[1] - last[1]) <= 3:
                    continue
                merged_timestamps.append(ts)
        
        return merged_timestamps
    
    def _is_valid_timestamp(self, start, end):
        """
        ✅ VALIDATION CHUNG cho timestamps
        """
        # Start phải < End
        if start >= end:
            return False
        
        # Duration phải hợp lý: 1 giây đến 4 giờ
        duration = end - start
        if duration < 1 or duration > 14400:
            return False
        
        # Timestamps không được âm
        if start < 0 or end < 0:
            return False
        
        return True

    def parse_claims_simple(self, raw_data, source_type, source_name="Unknown"):
        """
        ✅ v3.7: SIMPLE PARSING - Tương tự V3.2
        
        Logic đơn giản:
        1. Normalize text
        2. Extract 1 song name (dòng đầu tiên hợp lệ)
        3. Extract tất cả timestamps
        4. Gán CÙNG song name cho tất cả timestamps
        
        → Phù hợp với OCR text đơn giản không có separators
        
        Args:
            raw_data: Text từ OCR hoặc user paste
            source_type: "ocr" hoặc "text"
            source_name: Tên nguồn
            
        Returns:
            List of claim dictionaries
        """
        claims = []
        
        # BƯỚC 1: Normalize
        normalized_text = self.normalize_text(raw_data, source_type)
        
        print("\n" + "="*80)
        print("🔄 USING SIMPLE PARSING (V3.2 style)")
        print("="*80)
        
        # BƯỚC 2: Extract song name (1 lần duy nhất)
        song_name, song_confidence = self.extract_song_name(normalized_text, source_type)
        
        if song_name == "Unknown":
            print("⚠️ No valid song name found in simple parsing")
            return []
        
        print(f"🎵 Song: '{song_name}' (confidence: {song_confidence}%)")
        
        # BƯỚC 3: Extract tất cả timestamps
        timestamps = self.extract_timestamps(normalized_text)
        
        if not timestamps:
            print("⚠️ No timestamps found in simple parsing")
            return []
        
        print(f"⏱️  Found {len(timestamps)} timestamp(s)")
        
        # BƯỚC 4: Tạo claims - GÁN CÙNG song name cho tất cả
        for start, end in timestamps:
            claim = {
                'song': song_name,
                'start': start,
                'end': end,
                'duration': end - start,
                'source': source_name,
                'source_type': source_type,
                'confidence': 100 if source_type == "text" else song_confidence,
                'song_confidence': song_confidence
            }
            claims.append(claim)
            print(f"  ✅ Added: '{song_name}' - {self.format_time_clean(start)} → {self.format_time_clean(end)}")
        
        print(f"\n{'='*80}")
        print(f"🎯 SIMPLE PARSING RESULT: {len(claims)} claims from '{song_name}'")
        print(f"{'='*80}\n")
        
        return claims
    
    def parse_claims(self, raw_data, source_type, source_name="Unknown"):
        """
        ✅ v3.7: SMART PARSING với FALLBACK
        
        Logic:
        1. Thử BLOCK-BASED parsing (v3.7) - Chính xác cho multi-song
        2. Nếu thất bại → FALLBACK: SIMPLE parsing (V3.2) - Robust cho OCR
        
        Args:
            raw_data: Text từ OCR hoặc user paste
            source_type: "ocr" hoặc "text"
            source_name: Tên nguồn
            
        Returns:
            List of claim dictionaries
        """
        # BƯỚC 1: Normalize
        normalized_text = self.normalize_text(raw_data, source_type)
        
        print("\n" + "="*80)
        print("📋 NORMALIZED TEXT (first 600 chars):")
        print("="*80)
        print(normalized_text[:600])
        print("="*80 + "\n")
        
        # BƯỚC 2: Thử BLOCK-BASED PARSING trước
        claims = self._parse_claims_by_blocks(normalized_text, source_type, source_name)
        
        # BƯỚC 3: Nếu thất bại → FALLBACK to SIMPLE parsing
        if not claims:
            print("\n" + "⚠️"*40)
            print("⚠️  BLOCK PARSING FAILED - Switching to SIMPLE PARSING")
            print("⚠️"*40 + "\n")
            
            claims = self.parse_claims_simple(raw_data, source_type, source_name)
        
        return claims


    def _parse_claims_by_blocks(self, normalized_text, source_type, source_name):
        """
        ✅ v3.7: BLOCK-BASED PARSING - Logic v3.7 gốc
        
        Tách riêng thành private method để dễ maintain
        
        Returns:
            List of claims (empty nếu không parse được)
        """
        claims = []
        
        # SPLIT THEO "Nội dung được tìm thấy trong"
        blocks = []
        lines = normalized_text.split('\n')
        
        current_block = []
        in_block = False
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Bỏ qua separator lines
            if re.match(r'^={10,}$', line_stripped):
                if current_block:
                    blocks.append('\n'.join(current_block))
                    current_block = []
                    in_block = False
                continue
            
            # Bỏ qua dòng trống
            if not line_stripped:
                continue
            
            # Kiểm tra có phải dòng "Nội dung..." không
            if 'nội dung' in line_stripped.lower() or 'content found' in line_stripped.lower():
                in_block = True
                current_block.append(line)
                continue
            
            # Nếu đang trong block hoặc là tên bài
            if in_block:
                # Nếu gặp dòng KHÔNG phải timestamp → Bắt đầu block mới
                if not re.search(r'\d{1,2}:\d{2}', line_stripped):
                    # Lưu block cũ
                    if current_block:
                        blocks.append('\n'.join(current_block))
                        current_block = []
                        in_block = False
                    # Bắt đầu block mới với tên bài này
                    current_block = [line]
                else:
                    # Dòng timestamps → Thêm vào block hiện tại
                    current_block.append(line)
            else:
                # Chưa trong block → Có thể là tên bài
                current_block.append(line)
        
        # Lưu block cuối
        if current_block:
            blocks.append('\n'.join(current_block))
        
        print(f"📦 Split into {len(blocks)} block(s)\n")
        
        # ✅ Nếu không có block nào → Return empty (sẽ fallback)
        if not blocks:
            return []
        
        # Xử lý từng block
        for block_idx, block in enumerate(blocks, 1):
            block = block.strip()
            if len(block) < 10:
                continue
            
            print(f"\n{'─'*80}")
            print(f"📦 BLOCK {block_idx}:")
            print(f"{'─'*80}")
            print(block[:300])
            print()
            
            # Extract song name
            song_name, song_confidence = self.extract_song_name(block, source_type)
            
            if song_name == "Unknown":
                print(f"⚠️  Block {block_idx}: No valid song name found\n")
                continue
            
            # Extract timestamps
            timestamps = self.extract_timestamps(block)
            
            if not timestamps:
                print(f"⚠️  Block {block_idx}: No timestamps for '{song_name}'\n")
                continue
            
            # Tạo claims
            for start, end in timestamps:
                claim = {
                    'song': song_name,
                    'start': start,
                    'end': end,
                    'duration': end - start,
                    'source': source_name,
                    'source_type': source_type,
                    'confidence': 100 if source_type == "text" else song_confidence,
                    'song_confidence': song_confidence
                }
                claims.append(claim)
                print(f"✅ Added: '{song_name}' - {self.format_time_clean(start)} → {self.format_time_clean(end)}")
        
        if claims:
            print(f"\n{'='*80}")
            print(f"🎯 BLOCK PARSING SUCCESS: {len(claims)} claims from {len(set(c['song'] for c in claims))} songs")
            print(f"{'='*80}\n")
        
        return claims
    
    @staticmethod
    def format_time(seconds):
        """Format seconds to HH:MM:SS"""
        return str(timedelta(seconds=seconds))

    @staticmethod
    def format_time_clean(seconds):
        """
        ✅ v3.7: Format thời gian KHÔNG leading zeros
        
        VD: 
            - 17 giây → "0:17" (không phải "0:00:17")
            - 1h 54m 41s → "1:54:41"
            - 4h 15m → "4:15:00"
        
        Args:
            seconds: Số giây
            
        Returns:
            String format H:MM:SS hoặc M:SS
        """
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        
        if h > 0:
            # Có giờ: H:MM:SS
            return f"{h}:{m:02d}:{s:02d}"
        else:
            # Không có giờ: M:SS
            return f"{m}:{s:02d}"

    @staticmethod
    def format_claims_by_song(claims, numbered=False):
        """
        ✅ v3.7: FORMAT OUTPUT CHUẨN - Giữ nguyên format gốc
        
        Output mong muốn:
            1. Alívio (Cover): 0:17 — 4:15 | 1:54:41 — 1:57:27 | 3:06:47 — 3:08:28
            2. Deus Proverá: 1:11:49 — 1:12:59 | 4:10:44 — 4:11:51
        
        KHÔNG PHẢI:
            1. Alívio (Cover): 0:00:17 – 0:04:15 | 0:01:54:41 – 0:01:57:27
        """
        songs = {}
        
        for claim in claims:
            song = claim['song']
            if song not in songs:
                songs[song] = []
            
            # ✅ Sử dụng format_time_clean() thay vì format_time()
            start_str = UnifiedClaimParser.format_time_clean(claim['start'])
            end_str = UnifiedClaimParser.format_time_clean(claim['end'])
            
            # ✅ Giữ dấu — (em dash) giống YouTube
            time_range = f"{start_str} — {end_str}"
            songs[song].append(time_range)
        
        # Format output
        output_lines = []
        for idx, (song_name, time_ranges) in enumerate(sorted(songs.items()), 1):
            if numbered:
                # ✅ Nối timestamps bằng " | "
                line = f"{idx}. {song_name}: {' | '.join(time_ranges)}"
            else:
                line = f"{song_name}: {' | '.join(time_ranges)}"
            output_lines.append(line)
        
        return "\n".join(output_lines)



# ============================================================================
# MAIN APPLICATION
# ============================================================================

class ClaimCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Claim Checker v3.7 - Logic Đồng Bộ Hoàn Toàn")
        self.root.geometry("1400x900")
        
        # Configure Tesseract path for Windows
        if os.name == 'nt':
            tesseract_paths = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                r'C:\Users\Linh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
            ]
            for path in tesseract_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    break
        
        # ✅ KHỞI TẠO UNIFIED PARSER
        self.claim_parser = UnifiedClaimParser()
        
        # Data storage
        self.tracklist = []
        self.claims = []
        self.results = []
        self.pasted_images = []
        self.ambiguous_claims = []
        self.auto_accepted_claims = []
        self.input_mode = tk.StringVar(value="image")
        
        self.setup_ui()
        self.setup_paste_handler()
        self.setup_review_context_menu()  # ✅ THÊM DÒNG NÀY
    
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        title_label = ttk.Label(main_frame, text="YOUTUBE CLAIM CHECKER v3.7 - LOGIC ĐỒNG BỘ", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=10)
        
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.main_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.main_tab, text="Kiểm Tra Claims")
        self.setup_main_tab()
        
        self.review_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.review_tab, text="Review Claims (0)")
        self.setup_review_tab()
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
    
    def setup_main_tab(self):
        # File input section
        input_frame = ttk.LabelFrame(self.main_tab, text="1. Chọn File Tracklist", padding="10")
        input_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(input_frame, text="File TXT (Tracklist):").grid(row=0, column=0, sticky=tk.W)
        self.txt_path = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.txt_path, width=60).grid(row=0, column=1, padx=5)
        ttk.Button(input_frame, text="Chọn TXT", command=self.load_txt).grid(row=0, column=2)
        
        # Input mode selection
        mode_frame = ttk.LabelFrame(self.main_tab, text="2. Chọn Phương Thức Nhập Claim", padding="10")
        mode_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Radiobutton(mode_frame, text="📷 Nhập từ ảnh (OCR)", 
                       variable=self.input_mode, value="image",
                       command=self.toggle_input_mode).grid(row=0, column=0, padx=10, pady=5)
        ttk.Radiobutton(mode_frame, text="📝 Nhập từ text (paste)", 
                       variable=self.input_mode, value="text",
                       command=self.toggle_input_mode).grid(row=0, column=1, padx=10, pady=5)
        
        # Image input section
        self.image_frame = ttk.LabelFrame(self.main_tab, text="Nhập Claims từ Ảnh", padding="10")
        self.image_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(self.image_frame, text="Ảnh Claim:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.img_count = tk.StringVar(value="0 ảnh")
        ttk.Label(self.image_frame, textvariable=self.img_count).grid(row=0, column=1, sticky=tk.W)
        
        img_btn_frame = ttk.Frame(self.image_frame)
        img_btn_frame.grid(row=0, column=2)
        ttk.Button(img_btn_frame, text="🖼️ Chọn File", command=self.load_images).pack(side=tk.LEFT, padx=2)
        ttk.Button(img_btn_frame, text="📋 Paste (Ctrl+V)", command=self.paste_image).pack(side=tk.LEFT, padx=2)
        ttk.Button(img_btn_frame, text="🗑️ Xóa", command=self.clear_images).pack(side=tk.LEFT, padx=2)
        
        # ✅ THÊM BUTTON MỚI:
        ttk.Button(img_btn_frame, text="🐛 Debug OCR", command=self.debug_last_image).pack(side=tk.LEFT, padx=2)
        
        # Text input section
        self.text_frame = ttk.LabelFrame(self.main_tab, text="Nhập Claims từ Text", padding="10")
        self.text_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        self.text_frame.grid_remove()
        
        # Header với nút Paste
        text_header_frame = ttk.Frame(self.text_frame)
        text_header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))

        ttk.Label(text_header_frame, text="Paste text claim vào đây (có thể paste nhiều lần):").pack(side=tk.LEFT)
        ttk.Button(text_header_frame, text="📋 Paste", command=self.paste_text_claim).pack(side=tk.LEFT, padx=10)

        self.text_input = scrolledtext.ScrolledText(self.text_frame, width=100, height=8, 
                                                    font=('Consolas', 9))
        self.text_input.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        text_btn_frame = ttk.Frame(self.text_frame)
        text_btn_frame.grid(row=2, column=0, pady=5)
        ttk.Button(text_btn_frame, text="➕ Thêm Claims", command=self.add_text_claims).pack(side=tk.LEFT, padx=2)
        ttk.Button(text_btn_frame, text="🔄 Sắp Xếp Text", command=self.sort_text_input).pack(side=tk.LEFT, padx=2)
        ttk.Button(text_btn_frame, text="🗑️ Xóa Text", command=self.clear_text_input).pack(side=tk.LEFT, padx=2)
        ttk.Button(text_btn_frame, text="🗑️ Xóa Tất Cả", command=self.clear_all_text_claims).pack(side=tk.LEFT, padx=2)
        ttk.Button(text_btn_frame, text="📜 Xem Lịch Sử", command=self.view_text_history).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(self.text_frame, text="Claims đã nhập:").grid(row=3, column=0, sticky=tk.W, pady=(10,0))
        self.text_claims_display = scrolledtext.ScrolledText(
            self.text_frame, 
            width=100, 
            height=10,  # ✅ Tăng height để hiển thị nhiều dòng hơn
            font=('Consolas', 9), 
            wrap=tk.WORD,  # ✅ THÊM: Word wrap
            state='disabled'
        )
        self.text_claims_display.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Process button
        ttk.Button(self.main_tab, text="🔍 KIỂM TRA CLAIM", 
                  command=self.process_claims).grid(row=3, column=0, columnspan=3, pady=10)
        
        # Results section
        results_frame = ttk.LabelFrame(self.main_tab, text="3. Kết Quả Kiểm Tra", padding="10")
        results_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.results_text = scrolledtext.ScrolledText(results_frame, width=160, height=25, 
                                                      font=('Consolas', 9))
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        export_frame = ttk.Frame(results_frame)
        export_frame.grid(row=1, column=0, pady=5)
        ttk.Button(export_frame, text="💾 Xuất TXT", command=self.export_results).pack(side=tk.LEFT, padx=2)
        ttk.Button(export_frame, text="📊 Xuất CSV", command=self.export_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(export_frame, text="📄 Xuất Chi Tiết", command=self.export_detailed).pack(side=tk.LEFT, padx=2)
        
        self.main_tab.columnconfigure(0, weight=1)
        self.main_tab.rowconfigure(2, weight=1)
        self.main_tab.rowconfigure(4, weight=2)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        self.text_frame.columnconfigure(0, weight=1)
        self.text_frame.rowconfigure(1, weight=1)
        self.text_frame.rowconfigure(4, weight=1)
    
    def toggle_input_mode(self):
        mode = self.input_mode.get()
        if mode == "image":
            self.image_frame.grid()
            self.text_frame.grid_remove()
        else:
            self.image_frame.grid_remove()
            self.text_frame.grid()
    
    # ============================================
    # ✅ TEXT INPUT - Sử dụng Unified Parser
    # ============================================
    
    def add_text_claims(self):
        """
        ✅ v3.7: Text Input với DEDUPLICATION + Giữ nguyên text input + DEBUG
        """
        text = self.text_input.get("1.0", tk.END).strip()
        
        if not text:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập text claim!")
            return
        
        # ✅ Loại bỏ các dòng separator (=== và ---) 
        # Giữ nguyên cấu trúc dữ liệu gốc
        lines = text.split('\n')
        filtered_lines = []
        
        for line in lines:
            # Chỉ skip dòng toàn bộ là dấu =, -, hoặc khoảng trắng (tối thiểu 10 ký tự)
            if re.match(r'^[=\-\s]{10,}$', line):
                continue
            filtered_lines.append(line)
        
        text = '\n'.join(filtered_lines)
        
        # ✅ DEBUG 1: In ra text sau khi filter
        print("\n" + "="*80)
        print("🔍 DEBUG 1: TEXT SAU KHI FILTER SEPARATORS")
        print("="*80)
        print(text[:800])  # In 800 ký tự đầu
        print("="*80 + "\n")
        
        try:
            # Đếm claims cũ trước khi thêm
            old_count = len([c for c in self.claims if c.get('source_type') == 'text'])
            
            # ✅ GỌI UNIFIED PARSER
            parsed_claims = self.claim_parser.parse_claims(
                raw_data=text,
                source_type="text",
                source_name="Text Input"
            )
            
            # ✅ DEBUG 2: In ra parsed claims
            print("\n" + "="*80)
            print(f"🔍 DEBUG 2: PARSED {len(parsed_claims)} CLAIMS TỪ TEXT")
            print("="*80)
            if parsed_claims:
                for idx, claim in enumerate(parsed_claims[:10], 1):  # In 10 claims đầu
                    print(f"{idx}. Song: {claim['song']}")
                    print(f"   Time: {self.claim_parser.format_time(claim['start'])} → {self.claim_parser.format_time(claim['end'])}")
                    print(f"   Confidence: {claim['confidence']}%")
                    print()
            else:
                print("⚠️ KHÔNG TÌM THẤY CLAIM NÀO!")
            print("="*80 + "\n")
            
            if not parsed_claims:
                messagebox.showwarning("Cảnh báo", 
                    "Không tìm thấy claim hợp lệ trong text!\n\n"
                    "Kiểm tra Console (terminal) để xem debug info.")
                return
            
            # ✅ DEDUPLICATION - Kiểm tra trùng lặp
            new_claims_added = 0
            duplicates_skipped = 0
            
            for new_claim in parsed_claims:
                is_duplicate = False
                
                # Kiểm tra với tất cả claims đã có
                for existing_claim in self.claims:
                    # Chỉ so sánh với text claims
                    if existing_claim.get('source_type') != 'text':
                        continue
                    
                    # Điều kiện trùng: cùng bài + timestamps gần nhau (tolerance 3 giây)
                    same_song = existing_claim['song'].strip().lower() == new_claim['song'].strip().lower()
                    start_diff = abs(existing_claim['start'] - new_claim['start'])
                    end_diff = abs(existing_claim['end'] - new_claim['end'])
                    
                    if same_song and start_diff <= 3 and end_diff <= 3:
                        is_duplicate = True
                        duplicates_skipped += 1
                        print(f"⚠️ SKIP DUPLICATE: {new_claim['song']} - {self.claim_parser.format_time(new_claim['start'])}")
                        break
                
                # Chỉ thêm nếu không trùng
                if not is_duplicate:
                    self.claims.append(new_claim)
                    new_claims_added += 1
            
            # ✅ DEBUG 3: In ra kết quả deduplication
            print("\n" + "="*80)
            print(f"🔍 DEBUG 3: DEDUPLICATION RESULTS")
            print("="*80)
            print(f"✅ New claims added: {new_claims_added}")
            print(f"⚠️ Duplicates skipped: {duplicates_skipped}")
            print(f"📝 Total text claims: {len([c for c in self.claims if c.get('source_type') == 'text'])}")
            print("="*80 + "\n")
            
            # ✅ Lưu history
            if new_claims_added > 0:
                self.save_text_claims_history()
            
            # ✅ Update display
            self.update_text_claims_display()
            
            # ✅ KHÔNG XÓA text input - giữ nguyên để user có thể xem lại
            # self.text_input.delete("1.0", tk.END)  # <-- COMMENTED OUT
            
            # Thông báo chi tiết
            new_total = len([c for c in self.claims if c.get('source_type') == 'text'])
            
            message = f"✅ Đã thêm {new_claims_added} claims mới từ text!"
            if duplicates_skipped > 0:
                message += f"\n⚠️ Bỏ qua {duplicates_skipped} claims trùng lặp"
            message += f"\n📝 Tổng cộng: {new_total} claims"
            message += f"\n\n💡 Xem Console để kiểm tra chi tiết"
            
            messagebox.showinfo("Thành công", message)
            
        except Exception as e:
            print("\n" + "="*80)
            print("❌ DEBUG: ERROR")
            print("="*80)
            import traceback
            traceback.print_exc()
            print("="*80 + "\n")
            
            messagebox.showerror("Lỗi", f"Không thể parse text:\n{str(e)}")
    
    def update_text_claims_display(self):
        """
        ✅ v3.7: Hiển thị SẠCH - MỖI BÀI 1 DÒNG RIÊNG với format chuẩn
        """
        self.text_claims_display.config(state='normal')
        self.text_claims_display.delete("1.0", tk.END)
        
        text_claims = [c for c in self.claims if c.get('source_type') == 'text']
        
        if not text_claims:
            self.text_claims_display.config(state='disabled')
            self.img_count.set("0 claims từ text")
            return
        
        # ✅ DEDUPLICATION
        unique_claims = []
        seen = set()
        
        for claim in text_claims:
            start_rounded = (claim['start'] // 3) * 3
            end_rounded = (claim['end'] // 3) * 3
            key = (claim['song'].strip().lower(), start_rounded, end_rounded)
            
            if key not in seen:
                seen.add(key)
                unique_claims.append(claim)
        
        # ✅ SỬ DỤNG format_claims_by_song() ĐÃ ĐƯỢC SỬA
        formatted_output = self.claim_parser.format_claims_by_song(unique_claims, numbered=True)
        
        # Insert vào display
        self.text_claims_display.insert(tk.END, formatted_output)
        
        # Thống kê (nếu có deduplication)
        if len(text_claims) > len(unique_claims):
            stats = f"\n\nℹ️ Đã gộp {len(text_claims)} claims → {len(unique_claims)} unique claims\n"
            self.text_claims_display.insert(tk.END, stats)
        
        self.text_claims_display.config(state='disabled')
        
        # Update counter
        unique_songs = len(set(c['song'] for c in unique_claims))
        self.img_count.set(f"{len(unique_claims)} claims từ text ({unique_songs} bài)")

    def save_text_claims_history(self):
        """
        ✅ v3.7: Lưu lịch sử text claims vào file tạm
        Cho phép user xem lại những gì đã paste trước đó
        """
        text_claims = [c for c in self.claims if c.get('source_type') == 'text']
        
        if not text_claims:
            return
        
        # Tạo folder lưu history
        history_folder = Path.cwd() / "claim_history"
        history_folder.mkdir(exist_ok=True)
        
        # Tạo file với timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        history_file = history_folder / f"text_claims_{timestamp}.txt"
        
        # Lưu formatted output
        formatted_output = self.claim_parser.format_claims_by_song(text_claims, numbered=True)
        
        with open(history_file, 'w', encoding='utf-8-sig') as f:
            f.write("="*80 + "\n")
            f.write(f"TEXT CLAIMS HISTORY - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n\n")
            f.write(formatted_output)
            f.write(f"\n\n{'='*80}\n")
            f.write(f"Total: {len(text_claims)} claims from {len(set(c['song'] for c in text_claims))} songs\n")

    def view_text_history(self):
        """
        ✅ v3.7: Mở folder chứa lịch sử text claims
        """
        history_folder = Path.cwd() / "claim_history"
        
        if not history_folder.exists():
            messagebox.showinfo("Thông báo", "Chưa có lịch sử nào được lưu!")
            return
        
        history_files = list(history_folder.glob("text_claims_*.txt"))
        
        if not history_files:
            messagebox.showinfo("Thông báo", "Chưa có lịch sử nào được lưu!")
            return
        
        # Mở folder trong file explorer
        import subprocess
        import platform
        
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(history_folder)
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", history_folder])
            else:  # Linux
                subprocess.Popen(["xdg-open", history_folder])
            
            messagebox.showinfo("Thành công", 
                              f"✅ Đã mở folder lịch sử\n"
                              f"📂 {history_folder}\n"
                              f"📝 {len(history_files)} file(s)")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở folder:\n{str(e)}")
    
    def clear_text_input(self):
        self.text_input.delete("1.0", tk.END)

    def paste_text_claim(self):
        """
        ✅ v3.7: Paste text từ clipboard vào text input
        """
        try:
            # Lấy text từ clipboard
            clipboard_text = self.root.clipboard_get()
            
            if not clipboard_text or not clipboard_text.strip():
                messagebox.showwarning("Clipboard Trống", "Không có text trong clipboard!")
                return
            
            # Insert vào cuối text hiện tại (không xóa text cũ)
            current_text = self.text_input.get("1.0", tk.END).strip()
            
            if current_text:
                # Nếu đã có text, thêm separator
                self.text_input.insert(tk.END, "\n\n" + "="*80 + "\n\n")
            
            self.text_input.insert(tk.END, clipboard_text)
            
            # Scroll xuống cuối
            self.text_input.see(tk.END)
            
            messagebox.showinfo("Paste Thành Công", 
                              f"✅ Đã paste {len(clipboard_text)} ký tự\n"
                              f"📝 Nhấn 'Thêm Claims' để xử lý")
            
        except tk.TclError:
            messagebox.showerror("Lỗi", "Không thể đọc clipboard!\n\nKhông có text trong clipboard.")
        except Exception as e:
            messagebox.showerror("Lỗi Paste", f"Không thể paste text!\n\n{str(e)}")

    def sort_text_input(self):
        """
        ✅ v3.7: Sắp xếp text trong input box theo thứ tự thời gian
        """
        text = self.text_input.get("1.0", tk.END).strip()
        
        if not text:
            messagebox.showinfo("Thông báo", "Không có text để sắp xếp!")
            return
        
        try:
            # Parse text thành claims tạm thời
            temp_claims = self.claim_parser.parse_claims(
                raw_data=text,
                source_type="text",
                source_name="Temp"
            )
            
            if not temp_claims:
                messagebox.showwarning("Cảnh báo", "Không tìm thấy timestamps để sắp xếp!")
                return
            
            # Sắp xếp theo start time
            sorted_claims = sorted(temp_claims, key=lambda x: x['start'])
            
            # Format lại thành text
            formatted_lines = []
            for claim in sorted_claims:
                time_str = f"{self.claim_parser.format_time(claim['start'])} – {self.claim_parser.format_time(claim['end'])}"
                formatted_lines.append(f"{claim['song']}: {time_str}")
            
            # Cập nhật text input
            self.text_input.delete("1.0", tk.END)
            self.text_input.insert("1.0", "\n".join(formatted_lines))
            
            messagebox.showinfo("Thành công", 
                              f"✅ Đã sắp xếp {len(sorted_claims)} claims theo thời gian!")
            
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể sắp xếp text:\n{str(e)}")
    
    def clear_all_text_claims(self):
        """
        ✅ v3.7: Clear text claims + RESET validation state nếu cần
        """
        if not any(c.get('source_type') == 'text' for c in self.claims):
            messagebox.showinfo("Thông báo", "Chưa có claim nào từ text")
            return
        
        confirm = messagebox.askyesno("Xác nhận", "Xóa tất cả claims từ text?")
        if confirm:
            # Xóa text claims
            self.claims = [c for c in self.claims if c.get('source_type') != 'text']
            self.auto_accepted_claims = [c for c in self.auto_accepted_claims if c.get('source_type') != 'text']
            self.ambiguous_claims = [c for c in self.ambiguous_claims if c.get('source_type') != 'text']
            
            # ✅ Nếu không còn claims nào → Reset validation
            if not self.claims:
                self._validated = False
            
            self.update_text_claims_display()
            messagebox.showinfo("Thành công", "Đã xóa tất cả claims từ text")
    
    # ============================================
    # ✅ IMAGE/OCR INPUT - Sử dụng Unified Parser
    # ============================================
    
    def setup_review_tab(self):
        """
        ✅ v3.7: Review Tab với Status Bar và UI cải tiến
        """
        # ============================================
        # PHẦN 1: INFO FRAME - Hướng dẫn chi tiết
        # ============================================
        info_frame = ttk.LabelFrame(self.review_tab, text="📋 Hướng Dẫn Review Claims", padding="10")
        info_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        info_text = (
            "🎯 MỤC ĐÍCH: Dọn dẹp claims có vấn đề trước khi xử lý\n\n"
            
            "⚠️ CLAIMS CẦN REVIEW KHI:\n"
            "  • OCR confidence < 50% (nhận dạng không chắc chắn)\n"
            "  • Không tìm thấy file match trong tracklist (có thể sai tên)\n"
            "  • Timestamp bất thường (quá dài/ngắn)\n\n"
            
            "✅ CÁC HÀNH ĐỘNG:\n"
            "  • ✅ Chấp Nhận: Claim đúng → Giữ lại\n"
            "  • ❌ Loại Bỏ: Claim sai/nhầm → Xóa hẳn (QUAN TRỌNG!)\n"
            "  • ✏️ Chỉnh Sửa: Sửa tên bài/timestamp → Tự động chấp nhận\n\n"
            
            "💡 SAU KHI REVIEW XONG:\n"
            "  1. Quay lại tab 'Kiểm Tra Claims'\n"
            "  2. Nhấn nút 'KIỂM TRA CLAIM'\n"
            "  3. Kết quả sẽ bao gồm claims đã review"
        )
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT, font=('Arial', 9))
        info_label.pack(anchor=tk.W)
        
        # ============================================
        # PHẦN 2: REVIEW FRAME - Treeview với claims
        # ============================================
        review_frame = ttk.LabelFrame(self.review_tab, text="Claims Cần Review", padding="10")
        review_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Treeview columns
        columns = ('claim_id', 'song', 'time_range', 'confidence', 'reason', 'matched_files')
        self.review_tree = ttk.Treeview(review_frame, columns=columns, show='headings', height=15)
        
        # Column headings
        self.review_tree.heading('claim_id', text='ID')
        self.review_tree.heading('song', text='Tên Bài Hát')
        self.review_tree.heading('time_range', text='Khoảng Thời Gian')
        self.review_tree.heading('confidence', text='Confidence')
        self.review_tree.heading('reason', text='Lý Do')
        self.review_tree.heading('matched_files', text='Files Có Thể Match')
        
        # Column widths
        self.review_tree.column('claim_id', width=50)
        self.review_tree.column('song', width=250)
        self.review_tree.column('time_range', width=150)
        self.review_tree.column('confidence', width=100)
        self.review_tree.column('reason', width=200)
        self.review_tree.column('matched_files', width=250)
        
        # Grid treeview
        self.review_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(review_frame, orient=tk.VERTICAL, command=self.review_tree.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.review_tree.configure(yscrollcommand=scrollbar.set)
        
        # ============================================
        # ✅ PHẦN 3: STATUS BAR - Hiển thị tiến độ
        # ============================================
        status_frame = ttk.Frame(review_frame)
        status_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(10, 5))
        
        # Label hiển thị status
        self.review_status_label = ttk.Label(
            status_frame, 
            text="", 
            font=('Arial', 10, 'bold'),
            foreground='blue'
        )
        self.review_status_label.pack(side=tk.LEFT, padx=5)
        
        # Progress indicator (optional - có thể thêm progressbar)
        self.review_progress_label = ttk.Label(
            status_frame,
            text="",
            font=('Arial', 9),
            foreground='gray'
        )
        self.review_progress_label.pack(side=tk.LEFT, padx=20)
        
        # ============================================
        # PHẦN 4: ACTION BUTTONS
        # ============================================
        action_frame = ttk.Frame(review_frame)
        action_frame.grid(row=2, column=0, pady=10)
        
        ttk.Button(action_frame, text="✅ Chấp Nhận", 
                  command=self.accept_claim, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="❌ Loại Bỏ", 
                  command=self.reject_claim, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="✏️ Chỉnh Sửa", 
                  command=self.edit_claim, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="✅ Chấp Nhận Tất Cả", 
                  command=self.accept_all_claims, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="◀️ Quay Lại", 
                  command=self.go_back_to_main_tab, width=15).pack(side=tk.LEFT, padx=5)
        
        # ============================================
        # PHẦN 5: GRID CONFIGURATION
        # ============================================
        self.review_tab.columnconfigure(0, weight=1)
        self.review_tab.rowconfigure(1, weight=1)
        review_frame.columnconfigure(0, weight=1)
        review_frame.rowconfigure(0, weight=1)

    def setup_review_context_menu(self):
        """
        ✅ v3.7: Context menu cho Review Tab
        """
        self.review_context_menu = tk.Menu(self.review_tree, tearoff=0)
        self.review_context_menu.add_command(label="✅ Chấp Nhận", command=self.accept_claim)
        self.review_context_menu.add_command(label="❌ Loại Bỏ", command=self.reject_claim)
        self.review_context_menu.add_command(label="✏️ Chỉnh Sửa", command=self.edit_claim)
        self.review_context_menu.add_separator()
        self.review_context_menu.add_command(label="📋 Copy Tên Bài", command=self.copy_song_name)
        self.review_context_menu.add_command(label="📋 Copy Timestamp", command=self.copy_timestamp)
        
        def show_context_menu(event):
            # Select item under cursor
            item = self.review_tree.identify_row(event.y)
            if item:
                self.review_tree.selection_set(item)
                self.review_context_menu.post(event.x_root, event.y_root)
        
        self.review_tree.bind('<Button-3>', show_context_menu)  # Right-click

    def copy_song_name(self):
        """Copy tên bài hát sang clipboard"""
        selection = self.review_tree.selection()
        if not selection:
            return
        
        item = self.review_tree.item(selection[0])
        claim_id = int(item['values'][0]) - 1
        
        if claim_id < len(self.ambiguous_claims):
            song_name = self.ambiguous_claims[claim_id]['song']
            self.root.clipboard_clear()
            self.root.clipboard_append(song_name)
            print(f"📋 Copied: {song_name}")

    def copy_timestamp(self):
        """Copy timestamp sang clipboard"""
        selection = self.review_tree.selection()
        if not selection:
            return
        
        item = self.review_tree.item(selection[0])
        timestamp = item['values'][2]  # time_range column
        self.root.clipboard_clear()
        self.root.clipboard_append(timestamp)
        print(f"📋 Copied: {timestamp}")
    
    def setup_paste_handler(self):
        self.root.bind('<Control-v>', lambda e: self.paste_image())
        self.root.bind('<Control-V>', lambda e: self.paste_image())
    
    def load_txt(self):
        filepath = filedialog.askopenfilename(
            title="Chọn file TXT",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filepath:
            try:
                self.txt_path.set(filepath)
                self.parse_tracklist(filepath)
                
                unique_extensions = set(Path(t['filename']).suffix for t in self.tracklist)
                ext_str = ", ".join(unique_extensions)
                
                messagebox.showinfo(
                    "Thành công", 
                    f"✅ Đã tải {len(self.tracklist)} bài hát từ tracklist\n\n"
                    f"Định dạng: {ext_str}\n"
                    f"Thời lượng: {self.claim_parser.format_time(self.tracklist[-1]['end'])}"
                )
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể tải file!\n\n{str(e)}")
    
    def load_images(self):
        """
        ✅ v3.7: FIX - Lưu ảnh vào pasted_images để debug
        """
        filepaths = filedialog.askopenfilenames(
            title="Chọn ảnh claim",
            filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")]
        )
        if filepaths:
            success_count = 0
            
            for filepath in filepaths:
                try:
                    # ✅ FIX: Load và lưu ảnh
                    img = Image.open(filepath)
                    self.pasted_images.append(img)
                    
                    # Extract claims
                    source_name = Path(filepath).name
                    self.extract_claims_from_pil_image(img, source_name)
                    
                    success_count += 1
                    
                except Exception as e:
                    print(f"❌ Error loading {filepath}: {e}")
                    continue
            
            self.remove_duplicate_claims()
            self.update_image_count()
            
            # ✅ Hiển thị thông tin chi tiết
            if self.claims:
                messagebox.showinfo(
                    "Thành công", 
                    f"✅ Đã tải {success_count} ảnh từ file\n"
                    f"🎯 Phát hiện {len(self.claims)} claims\n\n"
                    f"Click 'KIỂM TRA CLAIM' để tiếp tục."
                )
            else:
                # ⚠️ Không tìm thấy claim
                response = messagebox.askyesno(
                    "⚠️ Không tìm thấy claim",
                    f"Đã tải {success_count} ảnh nhưng OCR không phát hiện được claim.\n\n"
                    f"Có thể do:\n"
                    f"• Chất lượng ảnh thấp\n"
                    f"• Text trong ảnh khó đọc\n"
                    f"• Format không đúng\n\n"
                    f"Bạn có muốn debug ảnh cuối cùng không?"
                )
                if response:
                    self.debug_last_image()
    
    def paste_image(self):
        if self.input_mode.get() == "text":
            return
        
        try:
            img = ImageGrab.grabclipboard()
            
            if img is None:
                messagebox.showwarning("Clipboard Trống", "Không tìm thấy ảnh trong clipboard!")
                return
            
            if isinstance(img, list):
                if len(img) > 0:
                    img = img[0]
                else:
                    return
            
            if not isinstance(img, Image.Image):
                try:
                    img = img.convert('RGB')
                except:
                    messagebox.showerror("Lỗi", "Dữ liệu clipboard không phải ảnh hợp lệ!")
                    return
            
            self.pasted_images.append(img)
            self.extract_claims_from_pil_image(img, f"Pasted_Image_{len(self.pasted_images)}")
            
            self.remove_duplicate_claims()
            self.update_image_count()
            
            messagebox.showinfo("Paste Thành Công", f"✅ Đã paste ảnh #{len(self.pasted_images)}")
            
        except Exception as e:
            messagebox.showerror("Lỗi Paste Ảnh", f"Không thể paste ảnh!\n\n{str(e)}")
    
    def clear_images(self):
        """
        ✅ v3.7: Clear images + RESET validation state
        """
        if not self.claims and not self.pasted_images:
            messagebox.showinfo("Thông báo", "Chưa có ảnh nào được tải")
            return
        
        confirm = messagebox.askyesno("Xác nhận", "Xóa tất cả ảnh đã tải?")
        if confirm:
            self.claims = []
            self.pasted_images = []
            self.ambiguous_claims = []
            self.auto_accepted_claims = []
            self.ambiguous_claims = []
            self.auto_accepted_claims = []
            self._validated = False  # ✅ THÊM DÒNG NÀY - Track validation state
            self.input_mode = tk.StringVar(value="image")
            self._validated = False  # ✅ RESET validation flag
            self.update_image_count()
            self.update_review_tab()
            messagebox.showinfo("Thành công", "Đã xóa tất cả ảnh")

    def debug_last_image(self):
        """
        ✅ v3.7: DEBUG - Test OCR với ảnh cuối cùng
        """
        if not self.pasted_images:
            messagebox.showwarning(
                "Cảnh báo", 
                "Chưa có ảnh nào được load!\n\n"
                "Vui lòng:\n"
                "• Paste ảnh (Ctrl+V), HOẶC\n"
                "• Chọn file ảnh"
            )
            return
        
        # Lấy ảnh cuối cùng
        img = self.pasted_images[-1]
        source_name = f"Debug_Image_{len(self.pasted_images)}"
        
        print("\n" + "="*80)
        print("🐛 STARTING DEBUG MODE")
        print("="*80)
        
        # Chạy debug với OUTPUT CHI TIẾT
        self.debug_ocr_output(img, source_name)
        
        # Hiển thị hướng dẫn
        messagebox.showinfo(
            "Debug Complete",
            f"✅ Đã debug ảnh #{len(self.pasted_images)}\n\n"
            f"📊 Kiểm tra CONSOLE (terminal) để xem:\n"
            f"• Raw OCR text\n"
            f"• Normalized text\n"
            f"• Extracted timestamps\n\n"
            f"Nếu không thấy timestamps:\n"
            f"→ Chất lượng ảnh quá thấp\n"
            f"→ Thử copy text thay vì dùng ảnh"
        )
    
    def update_image_count(self):
        if self.input_mode.get() == "image":
            unique_sources = len(set(c.get('source', '') for c in self.claims if c.get('source_type') != 'text'))
            ocr_claims = len([c for c in self.claims if c.get('source_type') == 'ocr'])
            self.img_count.set(f"{unique_sources} ảnh - {ocr_claims} claim")
        else:
            text_claims_count = len([c for c in self.claims if c.get('source_type') == 'text'])
            self.img_count.set(f"{text_claims_count} claims từ text")
    
    def parse_tracklist(self, filepath):
        self.tracklist = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except:
            try:
                with open(filepath, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
            except:
                with open(filepath, 'r', encoding='latin-1') as f:
                    content = f.read()
        
        audio_extensions = r'(wav|mp3|m4a|flac|ogg|aac|wma|opus|webm|aiff|ape)'
        pattern = rf'│\s+(\d{{2}}:\d{{2}}:\d{{2}})\s+\|\s+(\d{{2}}:\d{{2}}:\d{{2}})\s+\|\s+(.+?)\.{audio_extensions}'
        
        matches = re.findall(pattern, content, re.IGNORECASE)
        
        if not matches:
            pattern_alt = rf'(\d{{2}}:\d{{2}}:\d{{2}})\s+[|]\s+(\d{{2}}:\d{{2}}:\d{{2}})\s+[|]\s+(.+?)\.{audio_extensions}'
            matches = re.findall(pattern_alt, content, re.IGNORECASE)
        
        for match in matches:
            start, end, filename, extension = match
            self.tracklist.append({
                'start': self.parse_time(start),
                'end': self.parse_time(end),
                'filename': filename.strip() + '.' + extension
            })
        
        if not self.tracklist:
            raise ValueError("Không tìm thấy track nào trong file TXT.")
    
    def extract_claims_from_image(self, filepath):
        try:
            img = Image.open(filepath)
            source_name = Path(filepath).name
            self.extract_claims_from_pil_image(img, source_name)
        except Exception as e:
            print(f"Error: {e}")
    
    def extract_claims_from_pil_image(self, img, source_name):
        """
        ✅ v3.7: OCR với YOUTUBE PREPROCESSING + LOGGING
        """
        try:
            print(f"\n{'='*80}")
            print(f"🔍 Processing: {source_name}")
            print(f"{'='*80}")
            
            # ✅ THÊM: YouTube-specific preprocessing
            methods = [
                ("YouTube Specific", self.preprocess_youtube_screenshot),
                ("High Contrast", self.preprocess_method_1),
                ("Moderate", self.preprocess_method_2),
                ("Edge Enhance", self.preprocess_method_3)
            ]
            
            all_claims = []
            ocr_texts = []
            
            for method_name, method in methods:
                print(f"\n🔄 Trying method: {method_name}")
                
                img_processed = method(img)
                
                try:
                    # Config 1: Default (vie+eng+spa)
                    text1 = pytesseract.image_to_string(
                        img_processed, 
                        lang='vie+eng+spa',
                        config='--psm 6'
                    )
                    
                    # Config 2: Single line mode
                    text2 = pytesseract.image_to_string(
                        img_processed,
                        lang='eng',
                        config='--psm 7'
                    )
                    
                    # Config 3: Sparse text
                    text3 = pytesseract.image_to_string(
                        img_processed,
                        lang='eng+spa',
                        config='--psm 11'
                    )
                    
                    combined_text = f"{text1}\n{text2}\n{text3}"
                    ocr_texts.append((method_name, combined_text))
                    
                    print(f"   📝 OCR text length: {len(combined_text)} chars")
                    
                    # ✅ GỌI UNIFIED PARSER
                    claims = self.claim_parser.parse_claims(
                        raw_data=combined_text,
                        source_type="ocr",
                        source_name=source_name
                    )
                    
                    if claims:
                        print(f"   ✅ Found {len(claims)} claims!")
                        for claim in claims:
                            print(f"      • {claim['song']}: {self.claim_parser.format_time(claim['start'])} → {self.claim_parser.format_time(claim['end'])}")
                    else:
                        print(f"   ⚠️ No claims found")
                    
                    all_claims.extend(claims)
                    
                except Exception as e:
                    print(f"   ❌ OCR error: {e}")
                    continue
            
            # Debug: Nếu không tìm thấy claims, in ra sample text
            if not all_claims:
                print(f"\n{'⚠️'*40}")
                print(f"⚠️ NO CLAIMS FOUND FOR: {source_name}")
                print(f"{'⚠️'*40}")
                
                # In ra text từ method đầu tiên (YouTube specific)
                if ocr_texts:
                    method_name, text = ocr_texts[0]
                    print(f"\n📝 Sample OCR output from '{method_name}':")
                    print("-"*80)
                    print(text[:800])  # In 800 ký tự đầu
                    print("-"*80)
                    
                    # Thử normalize xem có gì không
                    normalized = self.claim_parser.normalize_text(text, "ocr")
                    print(f"\n✅ Normalized text:")
                    print("-"*80)
                    print(normalized[:500])
                    print("-"*80)
            
            # Merge similar claims
            self.merge_and_add_claims(all_claims)
            
            print(f"\n{'='*80}\n")
            
        except Exception as e:
            print(f"❌ Error processing image {source_name}: {e}")
            import traceback
            traceback.print_exc()

    def debug_ocr_output(self, img, source_name):
        """
        ✅ v3.7: DEBUG - Kiểm tra OCR output
        
        Chạy OCR và hiển thị kết quả để debug
        """
        print(f"\n{'='*80}")
        print(f"DEBUG OCR: {source_name}")
        print(f"{'='*80}")
        
        # Test với YouTube preprocessing
        img_processed = self.preprocess_youtube_screenshot(img)
        
        try:
            # OCR
            text = pytesseract.image_to_string(
                img_processed,
                lang='eng+spa',
                config='--psm 6'
            )
            
            print("\n📝 RAW OCR TEXT:")
            print("-"*80)
            print(text)
            print("-"*80)
            
            # Normalize
            normalized = self.claim_parser.normalize_text(text, "ocr")
            print("\n✅ NORMALIZED TEXT:")
            print("-"*80)
            print(normalized)
            print("-"*80)
            
            # Extract timestamps
            timestamps = self.claim_parser.extract_timestamps(normalized)
            print(f"\n🎯 EXTRACTED TIMESTAMPS: {len(timestamps)}")
            for idx, (start, end) in enumerate(timestamps, 1):
                print(f"  {idx}. {self.claim_parser.format_time(start)} → {self.claim_parser.format_time(end)}")
            
            print(f"\n{'='*80}\n")
            
        except Exception as e:
            print(f"❌ DEBUG ERROR: {e}")
            import traceback
            traceback.print_exc()

    def preprocess_youtube_screenshot(self, img):
        """
        ✅ v3.7: PREPROCESSING ĐẶC BIỆT cho YouTube screenshots
        
        Xử lý:
        - Text xanh (#3EA6FF) trên nền đen
        - Font nhỏ
        - Nhiễu từ UI YouTube
        
        Returns:
            Preprocessed image tối ưu cho OCR
        """
        # BƯỚC 1: Tăng kích thước để OCR đọc dễ hơn (scale 2x)
        width, height = img.size
        img = img.resize((width * 2, height * 2), Image.LANCZOS)
        
        # BƯỚC 2: Convert sang grayscale
        img_gray = img.convert('L')
        
        # BƯỚC 3: INVERT colors (text xanh thành trắng, nền đen thành đen)
        # YouTube: text sáng trên nền tối → Cần invert để OCR đọc tốt hơn
        from PIL import ImageOps
        img_inverted = ImageOps.invert(img_gray)
        
        # BƯỚC 4: Extreme contrast để làm rõ text
        img_contrast = ImageEnhance.Contrast(img_inverted).enhance(3.0)
        
        # BƯỚC 5: Brightness để text trắng hơn
        img_bright = ImageEnhance.Brightness(img_contrast).enhance(1.5)
        
        # BƯỚC 6: Sharpen để text rõ nét
        img_sharp = ImageEnhance.Sharpness(img_bright).enhance(2.5)
        
        # BƯỚC 7: Binary threshold - chỉ giữ đen/trắng
        threshold = 150
        img_binary = img_sharp.point(lambda x: 255 if x > threshold else 0, mode='1')
        
        # BƯỚC 8: Denoise - Remove small noise
        img_binary = img_binary.filter(ImageFilter.MedianFilter(size=3))
        
        return img_binary
    
    def preprocess_method_1(self, img):
        """Method 1: High contrast + Sharpen"""
        img_gray = img.convert('L')
        img_contrast = ImageEnhance.Contrast(img_gray).enhance(2.5)
        img_sharp = ImageEnhance.Sharpness(img_contrast).enhance(2.0)
        return img_sharp
    
    def preprocess_method_2(self, img):
        """Method 2: Moderate processing"""
        img_gray = img.convert('L')
        img_contrast = ImageEnhance.Contrast(img_gray).enhance(1.8)
        img_bright = ImageEnhance.Brightness(img_contrast).enhance(1.2)
        return img_bright
    
    def preprocess_method_3(self, img):
        """Method 3: With edge enhancement"""
        img_gray = img.convert('L')
        img_edge = img_gray.filter(ImageFilter.EDGE_ENHANCE_MORE)
        img_contrast = ImageEnhance.Contrast(img_edge).enhance(2.0)
        return img_contrast
    
    def merge_and_add_claims(self, all_claims):
        """
        ✅ v3.7: NÂNG CẤP - Merge với tolerance cao hơn cho OCR
        """
        if not all_claims:
            return
        
        sorted_claims = sorted(all_claims, key=lambda x: x['start'])
        merged = []
        
        for claim in sorted_claims:
            is_similar = False
            
            for existing in merged:
                # ✅ TĂNG TOLERANCE lên 5 giây (thay vì 3)
                # OCR có thể sai lệch vài giây
                start_diff = abs(claim['start'] - existing['start'])
                end_diff = abs(claim['end'] - existing['end'])
                
                if (start_diff <= 5 and end_diff <= 5 and
                    claim['source'] == existing['source']):
                    
                    # Giữ claim có confidence cao hơn
                    if claim['confidence'] > existing['confidence']:
                        merged.remove(existing)
                        merged.append(claim)
                    is_similar = True
                    break
            
            if not is_similar:
                merged.append(claim)
        
        self.claims.extend(merged)
        
        print(f"✅ Merged {len(all_claims)} → {len(merged)} claims")
    
    def remove_duplicate_claims(self):
        if not self.claims:
            return
        
        unique_claims = []
        sorted_claims = sorted(self.claims, key=lambda x: x['start'])
        
        for claim in sorted_claims:
            is_duplicate = False
            for existing in unique_claims:
                start_diff = abs(claim['start'] - existing['start'])
                end_diff = abs(claim['end'] - existing['end'])
                
                if (claim['source'] == existing['source'] and 
                    start_diff <= 5 and end_diff <= 5):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_claims.append(claim)
        
        self.claims = unique_claims


    # ============================================
    # ✅ THÊM 2 HÀM MỚI TẠI ĐÂY
    # ============================================

    def _deduplicate_claims_for_display(self, claims):
        """
        ✅ v3.7: Loại bỏ claims TRÙNG LẶP cho display
        
        Logic:
        - Cùng song name (normalize: loại bỏ accents, lowercase)
        - Cùng timestamps (tolerance 3 giây)
        → Chỉ giữ 1 claim có confidence cao nhất
        
        Args:
            claims: List of claim dictionaries
            
        Returns:
            List of unique claims
        """
        if not claims:
            return []
        
        unique_claims = []
        
        for claim in claims:
            is_duplicate = False
            
            for existing in unique_claims:
                # Check 1: Cùng song name (normalize)
                song1 = self._normalize_song_name(claim['song'])
                song2 = self._normalize_song_name(existing['song'])
                
                if song1 != song2:
                    continue
                
                # Check 2: Timestamps gần nhau (tolerance 3 giây)
                start_diff = abs(claim['start'] - existing['start'])
                end_diff = abs(claim['end'] - existing['end'])
                
                if start_diff <= 3 and end_diff <= 3:
                    is_duplicate = True
                    
                    # Giữ claim có confidence cao hơn
                    if claim['confidence'] > existing['confidence']:
                        unique_claims.remove(existing)
                        unique_claims.append(claim)
                    
                    break
            
            if not is_duplicate:
                unique_claims.append(claim)
        
        # Log kết quả
        if len(claims) != len(unique_claims):
            print(f"\n🔍 DEDUPLICATION FOR DISPLAY:")
            print(f"   Original: {len(claims)} claims")
            print(f"   Unique: {len(unique_claims)} claims")
            print(f"   Removed: {len(claims) - len(unique_claims)} duplicates\n")
        
        return unique_claims


    def _normalize_song_name(self, song_name):
        """
        ✅ v3.7: Normalize song name để so sánh
        
        Loại bỏ:
        - Accents (á → a, í → i, é → e, ...)
        - Lowercase
        - Extra spaces
        - Special characters
        
        Returns:
            Normalized string
        """
        import unicodedata
        
        # Remove accents (NFD = Canonical Decomposition)
        normalized = unicodedata.normalize('NFD', song_name)
        normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        
        # Lowercase + strip
        normalized = normalized.lower().strip()
        
        # Remove multiple spaces
        normalized = ' '.join(normalized.split())
        
        return normalized

    def _deduplicate_results_for_export(self, results):
        """
        ✅ v3.7: Loại bỏ trùng lặp trong results (claimed_tracks) cho export
        
        Args:
            results: List of {'track': ..., 'claim': ...}
            
        Returns:
            List of unique results
        """
        if not results:
            return []
        
        unique_results = []
        seen = set()
        
        for item in results:
            claim = item['claim']
            track = item['track']
            
            # Create unique key
            song_normalized = self._normalize_song_name(claim['song'])
            start_rounded = (claim['start'] // 3) * 3
            end_rounded = (claim['end'] // 3) * 3
            key = (track['filename'], song_normalized, start_rounded, end_rounded)
            
            if key not in seen:
                seen.add(key)
                unique_results.append(item)
        
        return unique_results
    
    # ============================================
    # ✅ UNIFIED VALIDATION - Cho cả OCR và Text
    # ============================================
    
    def validate_claims_smart(self):
        """
        ✅ v3.7: VALIDATION CHUNG cho cả OCR và Text
        Không phân biệt nguồn
        """
        if not self.tracklist or not self.claims:
            return
        
        max_tracklist_time = max(track['end'] for track in self.tracklist)
        valid_claims = []
        self.ambiguous_claims = []
        self.auto_accepted_claims = []
        
        for claim in self.claims:
            # Check 1: Nằm trong range hợp lý
            if claim['start'] > max_tracklist_time + 600:
                print(f"⚠️ SKIP: Claim ngoài tracklist - {claim['song'][:30]}")
                continue
            
            if claim['end'] > max_tracklist_time + 600:
                claim['end'] = min(claim['end'], max_tracklist_time + 300)
            
            # ✅ VALIDATION ĐỒNG NHẤT
            is_ambiguous = False
            ambiguous_reasons = []
            
            # 1. Confidence check (áp dụng cho cả OCR và Text)
            if claim['confidence'] < 50:
                is_ambiguous = True
                ambiguous_reasons.append(f"Low confidence: {claim['confidence']:.1f}%")
            
            # 2. Duration check (áp dụng cho TẤT CẢ)
            duration = claim['end'] - claim['start']
            if duration < 10:
                is_ambiguous = True
                ambiguous_reasons.append(f"Duration too short: {duration}s")
            elif duration > 3600:
                is_ambiguous = True
                ambiguous_reasons.append(f"Duration too long: {duration}s")
            
            # 3. Tracklist matching (áp dụng cho TẤT CẢ)
            has_match = False
            for track in self.tracklist:
                if self.check_claim_overlap(
                    track['start'], track['end'],
                    claim['start'], claim['end']
                ):
                    has_match = True
                    break
            
            if not has_match:
                is_ambiguous = True
                ambiguous_reasons.append("No matching file in tracklist")
            
            # Phân loại
            if is_ambiguous:
                claim['ambiguous_reason'] = '; '.join(ambiguous_reasons)
                self.ambiguous_claims.append(claim)
                print(f"⚠️ AMBIGUOUS [{claim.get('source_type', '?').upper()}]: {claim['song'][:30]} - {'; '.join(ambiguous_reasons)}")
            else:
                self.auto_accepted_claims.append(claim)
                print(f"✅ AUTO-ACCEPTED [{claim.get('source_type', '?').upper()}]: {claim['song'][:30]}")
            
            valid_claims.append(claim)
        
        self.claims = valid_claims
        
        print(f"\n📊 SUMMARY:")
        print(f"✅ Auto-accepted: {len(self.auto_accepted_claims)} claims")
        print(f"⚠️ Need review: {len(self.ambiguous_claims)} claims")
        
        self.update_review_tab()
    
    def update_review_tab(self):
        """
        ✅ v3.7: Update Review Tab với Status Bar
        """
        # ============================================
        # BƯỚC 1: Clear existing items
        # ============================================
        for item in self.review_tree.get_children():
            self.review_tree.delete(item)
        
        # ============================================
        # BƯỚC 2: Populate treeview với ambiguous claims
        # ============================================
        for idx, claim in enumerate(self.ambiguous_claims, 1):
            time_range = f"{self.claim_parser.format_time_clean(claim['start'])} – {self.claim_parser.format_time_clean(claim['end'])}"
            confidence = f"{claim['confidence']:.1f}%"
            reason = claim.get('ambiguous_reason', 'Unknown')
            
            # Tìm potential matches trong tracklist
            matched_files_str = "Không tìm thấy"
            potential_matches = []
            for track in self.tracklist:
                # Check overlap hoặc tên gần giống
                if abs(track['start'] - claim['start']) < 300 or abs(track['end'] - claim['end']) < 300:
                    potential_matches.append(track['filename'])
            
            if potential_matches:
                matched_files_str = potential_matches[0][:40]
                if len(potential_matches) > 1:
                    matched_files_str += f" (+{len(potential_matches)-1})"
            
            # Insert vào treeview
            self.review_tree.insert('', 'end', values=(
                idx, 
                claim['song'][:35], 
                time_range, 
                confidence, 
                reason, 
                matched_files_str
            ))
        
        # ============================================
        # BƯỚC 3: Update tab title với số lượng
        # ============================================
        remaining = len(self.ambiguous_claims)
        self.notebook.tab(1, text=f"Review Claims ({remaining})")
        
        # ============================================
        # ✅ BƯỚC 4: UPDATE STATUS BAR
        # ============================================
        if hasattr(self, 'review_status_label'):
            accepted = len(self.auto_accepted_claims)
            total_claims = accepted + remaining
            
            if remaining == 0:
                # ✅ Hoàn thành review
                self.review_status_label.config(
                    text=f"✅ Hoàn thành! Đã xử lý {accepted}/{total_claims} claims.",
                    foreground='green'
                )
                
                if hasattr(self, 'review_progress_label'):
                    self.review_progress_label.config(
                        text="💡 Quay lại tab chính và nhấn 'KIỂM TRA CLAIM' để xem kết quả",
                        foreground='blue'
                    )
            
            elif remaining == total_claims:
                # ⚠️ Chưa xử lý gì
                self.review_status_label.config(
                    text=f"⚠️ Cần xử lý {remaining} claims",
                    foreground='orange'
                )
                
                if hasattr(self, 'review_progress_label'):
                    self.review_progress_label.config(
                        text="👉 Bắt đầu bằng cách chọn claim và nhấn ✅/❌/✏️",
                        foreground='gray'
                    )
            
            else:
                # 🔄 Đang xử lý
                progress_percent = (accepted / total_claims) * 100 if total_claims > 0 else 0
                
                self.review_status_label.config(
                    text=f"🔄 Đang xử lý: {remaining} còn lại | ✅ Đã chấp nhận: {accepted}",
                    foreground='orange'
                )
                
                if hasattr(self, 'review_progress_label'):
                    self.review_progress_label.config(
                        text=f"📊 Tiến độ: {progress_percent:.0f}% ({accepted}/{total_claims})",
                        foreground='blue'
                    )
    
    def parse_time(self, time_str):
        parts = time_str.split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    
    def check_claim_overlap(self, track_start, track_end, claim_start, claim_end):
        tolerance = 10
        start_in_range = (claim_start >= track_start - tolerance and 
                         claim_start <= track_end + tolerance)
        end_in_range = (claim_end >= track_start - tolerance and 
                       claim_end <= track_end + tolerance)
        return start_in_range and end_in_range
    
    def process_claims(self):
        """
        ✅ v3.7: LOGIC MỚI - Review → Clean → Process
        
        Flow:
        1. Lần đầu: Validate → Nếu có ambiguous → Chuyển Review Tab
        2. Lần sau: Kiểm tra đã review xong chưa
           - Xong: Process + Display
           - Chưa: Cảnh báo quay lại review
        """
        if not self.tracklist:
            messagebox.showerror("Lỗi", "Vui lòng tải file TXT trước!")
            return
        
        if not self.claims:
            messagebox.showerror("Lỗi", "Vui lòng tải ảnh claim hoặc nhập text claim!")
            return
        
        # ============================================
        # BƯỚC 1: KIỂM TRA - Đã validate lần đầu chưa?
        # ============================================
        # Nếu chưa có auto_accepted_claims → Chưa validate
        if not hasattr(self, '_validated') or not self._validated:
            print("\n🔍 FIRST RUN - Validating claims...")
            
            self.validate_claims_smart()
            self._validated = True  # Đánh dấu đã validate
            
            if not self.claims:
                messagebox.showwarning("Cảnh báo", "Không có claim hợp lệ!")
                self._validated = False
                return
            
            # Có ambiguous claims → Cần review
            if self.ambiguous_claims:
                response = messagebox.askquestion(
                    "Kết Quả Validate",
                    f"✅ Đã tự động chấp nhận: {len(self.auto_accepted_claims)} claims\n"
                    f"⚠️ Cần review: {len(self.ambiguous_claims)} claims\n\n"
                    f"Bạn muốn:\n"
                    f"• YES: Review các claims có vấn đề (Khuyến nghị)\n"
                    f"• NO: Bỏ qua và chỉ dùng {len(self.auto_accepted_claims)} claims đã chấp nhận"
                )
                
                if response == 'yes':
                    # Chuyển sang Review Tab để user dọn dẹp
                    self.notebook.select(1)
                    messagebox.showinfo(
                        "Hướng dẫn",
                        "📋 HƯỚNG DẪN REVIEW:\n\n"
                        "1. ✅ Chấp nhận: Claim đúng, giữ lại\n"
                        "2. ❌ Loại bỏ: Claim sai/nhầm, xóa hẳn\n"
                        "3. ✏️ Chỉnh sửa: Sửa tên/timestamp rồi chấp nhận\n\n"
                        "4. ✅ Sau khi dọn dẹp xong:\n"
                        "   → Quay lại tab 'Kiểm Tra Claims'\n"
                        "   → Nhấn 'KIỂM TRA CLAIM' lại\n"
                        "   → Kết quả sẽ bao gồm claims đã review"
                    )
                    return
                else:
                    # User chọn NO → Bỏ qua ambiguous
                    if self.ambiguous_claims:
                        skipped = len(self.ambiguous_claims)
                        messagebox.showinfo(
                            "Thông báo",
                            f"⚠️ Đã BỎ QUA {skipped} claims cần review\n\n"
                            f"Kết quả sẽ CHỈ bao gồm:\n"
                            f"✅ {len(self.auto_accepted_claims)} claims đã tự động chấp nhận"
                        )
                        # Xóa ambiguous claims khỏi self.claims
                        for amb_claim in self.ambiguous_claims:
                            if amb_claim in self.claims:
                                self.claims.remove(amb_claim)
                        self.ambiguous_claims = []
                    
                    # Tiếp tục process với auto_accepted_claims
                    print(f"✅ Processing with {len(self.auto_accepted_claims)} auto-accepted claims")
        
        # ============================================
        # BƯỚC 2: KIỂM TRA - Còn ambiguous chưa xử lý?
        # ============================================
        else:
            print("\n🔄 SECOND RUN - Checking review status...")
            
            if self.ambiguous_claims:
                # Còn claims chưa review
                response = messagebox.askyesnocancel(
                    "⚠️ Còn Claims Chưa Review",
                    f"Còn {len(self.ambiguous_claims)} claims chưa được xử lý!\n\n"
                    f"Bạn muốn:\n"
                    f"• YES: Quay lại Review Tab để tiếp tục dọn dẹp\n"
                    f"• NO: Bỏ qua và chỉ dùng {len(self.auto_accepted_claims)} claims đã chấp nhận\n"
                    f"• CANCEL: Hủy"
                )
                
                if response is None:  # Cancel
                    return
                elif response:  # YES → Quay lại review
                    self.notebook.select(1)
                    return
                else:  # NO → Bỏ qua ambiguous
                    skipped = len(self.ambiguous_claims)
                    messagebox.showinfo(
                        "Thông báo",
                        f"⚠️ Đã BỎ QUA {skipped} claims chưa review\n\n"
                        f"Kết quả sẽ CHỈ bao gồm:\n"
                        f"✅ {len(self.auto_accepted_claims)} claims đã chấp nhận"
                    )
                    # Xóa ambiguous claims
                    for amb_claim in self.ambiguous_claims:
                        if amb_claim in self.claims:
                            self.claims.remove(amb_claim)
                    self.ambiguous_claims = []
            else:
                # Đã review xong tất cả
                print("✅ All claims reviewed! Processing...")
        
        # ============================================
        # BƯỚC 3: PROCESS + DISPLAY KẾT QUẢ
        # ============================================
        # Chỉ dùng auto_accepted_claims (đã bao gồm claims reviewed)
        claims_to_process = self.auto_accepted_claims
        
        if not claims_to_process:
            messagebox.showwarning("Cảnh báo", "Không có claim nào được chấp nhận!")
            return
        
        print(f"\n📊 PROCESSING {len(claims_to_process)} claims...")
        
        # Match claims với tracklist
        self.results = []
        claimed_tracks = []
        
        for claim in claims_to_process:
            for track in self.tracklist:
                if self.check_claim_overlap(track['start'], track['end'], 
                                           claim['start'], claim['end']):
                    claimed_tracks.append({'track': track, 'claim': claim})
        
        # Display kết quả
        self.display_results(claimed_tracks)
        
        # Thông báo thành công
        unique_files = len(set(item['track']['filename'] for item in claimed_tracks))
        messagebox.showinfo(
            "✅ Hoàn thành",
            f"📊 KẾT QUẢ KIỂM TRA:\n\n"
            f"✅ Tổng claims đã xử lý: {len(claims_to_process)}\n"
            f"⚠️ File bị claim: {unique_files}/{len(self.tracklist)}\n"
            f"📁 Tổng lần claim: {len(claimed_tracks)}\n\n"
            f"Chi tiết xem bên dưới!"
        )

    def process_claims_without_validate(self):
        """
        ✅ v3.7: Process claims KHÔNG validate lại
        
        Dùng khi:
        - User đã review xong claims trong Review Tab
        - Chỉ cần display kết quả, không cần validate lại
        """
        if not self.tracklist:
            messagebox.showerror("Lỗi", "Vui lòng tải file TXT trước!")
            return
        
        if not self.claims:
            messagebox.showerror("Lỗi", "Không có claims để xử lý!")
            return
        
        # ✅ CHỈ LẤY auto_accepted_claims để display
        claims_to_process = self.auto_accepted_claims
        
        if not claims_to_process:
            messagebox.showwarning("Cảnh báo", "Không có claim nào được chấp nhận!")
            return
        
        self.results = []
        claimed_tracks = []
        
        # Match claims với tracklist
        for claim in claims_to_process:
            for track in self.tracklist:
                if self.check_claim_overlap(track['start'], track['end'], 
                                           claim['start'], claim['end']):
                    claimed_tracks.append({'track': track, 'claim': claim})
        
        # Display kết quả
        self.display_results(claimed_tracks)
        
        messagebox.showinfo(
            "Hoàn thành",
            f"✅ Đã xử lý {len(claims_to_process)} claims!\n"
            f"⚠️ Tìm thấy {len(claimed_tracks)} file bị claim."
        )
    
    def get_base_song_name(self, filename):
        name = filename.replace('.wav', '')
        match = re.match(r'(\d+- [^(]+)', name)
        if match:
            return match.group(1).strip()
        return name
    
    # ============================================
    # ✅ UNIFIED DISPLAY - Format chuẩn cho cả OCR và Text
    # ============================================
    
    def display_results(self, claimed_tracks):
        """
        ✅ v3.7: Hiển thị kết quả với DEDUPLICATION
        """
        self.results_text.delete(1.0, tk.END)
        
        header = "="*140 + "\n"
        header += "YOUTUBE CLAIM CHECKER - KẾT QUẢ KIỂM TRA v3.7\n"
        header += "="*140 + "\n\n"
        self.results_text.insert(tk.END, header)
        
        # ✅ DEDUPLICATE claims trước khi xử lý
        unique_claims = self._deduplicate_claims_for_display(self.claims)
        
        # ============================================
        # ✅ SECTION 1: DANH SÁCH CLAIMS ĐÃ NHẬP
        # ============================================
        self.results_text.insert(tk.END, "="*140 + "\n")
        self.results_text.insert(tk.END, "📋 PHẦN 1: DANH SÁCH CLAIMS ĐÃ PHÁT HIỆN\n")
        self.results_text.insert(tk.END, "="*140 + "\n\n")
        
        # Thống kê tổng quan
        text_claims = [c for c in unique_claims if c.get('source_type') == 'text']
        ocr_claims = [c for c in unique_claims if c.get('source_type') == 'ocr']
        
        stats = f"📊 TỔNG QUAN:\n"
        stats += f"  • Tổng số claims: {len(unique_claims)}\n"
        stats += f"  • 📝 Từ text input: {len(text_claims)} claims\n"
        stats += f"  • 📷 Từ OCR (ảnh): {len(ocr_claims)} claims\n"
        stats += f"  • ✅ Auto-accepted: {len([c for c in unique_claims if c in self.auto_accepted_claims])} claims\n"
        stats += f"  • ⚠️ Need review: {len([c for c in unique_claims if c in self.ambiguous_claims])} claims\n"
        stats += f"  • 🎵 Số bài hát unique: {len(set(c['song'] for c in unique_claims))}\n\n"
        
        self.results_text.insert(tk.END, stats)
        
        # Hiển thị claims theo bài hát (format đẹp)
        self.results_text.insert(tk.END, "📝 CHI TIẾT CLAIMS THEO BÀI HÁT:\n")
        self.results_text.insert(tk.END, "-"*140 + "\n\n")
        
        formatted_claims = self.claim_parser.format_claims_by_song(unique_claims, numbered=True)
        self.results_text.insert(tk.END, formatted_claims)
        self.results_text.insert(tk.END, "\n\n")
        
        # ============================================
        # ✅ SECTION 2: KẾT QUẢ SO SÁNH VỚI TRACKLIST
        # ============================================
        self.results_text.insert(tk.END, "="*140 + "\n")
        self.results_text.insert(tk.END, "🎯 PHẦN 2: KẾT QUẢ SO SÁNH VỚI TRACKLIST\n")
        self.results_text.insert(tk.END, "="*140 + "\n\n")
        
        # ✅ Rebuild claimed_tracks với unique claims
        claimed_tracks_unique = []
        for claim in unique_claims:
            for track in self.tracklist:
                if self.check_claim_overlap(track['start'], track['end'], 
                                           claim['start'], claim['end']):
                    claimed_tracks_unique.append({'track': track, 'claim': claim})
        
        # Group by song
        songs = {}
        for item in claimed_tracks_unique:
            song = item['claim']['song']
            if song not in songs:
                songs[song] = []
            songs[song].append(item)
        
        total_claims = 0
        claimed_filenames = {}
        
        for song_name, items in songs.items():
            self.results_text.insert(tk.END, f"\n{'='*140}\n")
            self.results_text.insert(tk.END, f"BÀI HÁT: {song_name}\n")
            self.results_text.insert(tk.END, f"{'='*140}\n\n")
            
            for idx, item in enumerate(items, 1):
                track = item['track']
                claim = item['claim']
                
                if track['filename'] not in claimed_filenames:
                    claimed_filenames[track['filename']] = 0
                claimed_filenames[track['filename']] += 1
                
                status = "✅ AUTO" if claim in self.auto_accepted_claims else "⚠️ REVIEW"
                source_icon = "📝" if claim.get('source_type') == 'text' else "📷"
                
                result = f"Claim #{idx} {status} {source_icon}:\n"
                result += f"  ⚠️ FILE BỊ CLAIM: {track['filename']}\n"
                result += f"  📍 Thời gian file: {self.claim_parser.format_time(track['start'])} → {self.claim_parser.format_time(track['end'])}\n"
                result += f"  🎯 Claim phát hiện: {self.claim_parser.format_time(claim['start'])} → {self.claim_parser.format_time(claim['end'])}\n"
                result += f"  {source_icon} Nguồn: {claim['source']}\n"
                
                conf_icon = "✅" if claim['confidence'] >= 70 else "⚠️"
                result += f"  {conf_icon} Confidence: {claim['confidence']:.1f}%\n"
                
                file_duration = max(1, track['end'] - track['start'])
                claim_duration = max(0, claim['end'] - claim['start'])
                claim_percent = (claim_duration / file_duration * 100) if file_duration > 0 else 0
                
                result += f"  📊 Tỷ lệ claim: {claim_percent:.1f}% thời lượng file\n"
                result += f"  ✅ KHỚP: Claim nằm trong khoảng file\n\n"
                
                self.results_text.insert(tk.END, result)
                total_claims += 1
        
        # ============================================
        # ✅ SECTION 3: TỔNG KẾT CUỐI CÙNG
        # ============================================
        unique_filenames_tracklist = set(track['filename'] for track in self.tracklist)
        unique_claimed = set(claimed_filenames.keys())
        not_claimed_filenames = unique_filenames_tracklist - unique_claimed
        
        summary = f"\n{'='*140}\n"
        summary += f"📊 PHẦN 3: TỔNG KẾT CUỐI CÙNG\n"
        summary += f"{'='*140}\n\n"

        summary += f"╔══ THỐNG KÊ CLAIMS ══\n"
        summary += f"║ Tổng claims phát hiện: {len(unique_claims)}\n"
        summary += f"║   📝 Claims từ text: {len(text_claims)}\n"
        summary += f"║   📷 Claims từ ảnh (OCR): {len(ocr_claims)}\n"
        summary += f"║ Claims auto-accepted: {len([c for c in unique_claims if c in self.auto_accepted_claims])}\n"
        summary += f"║ Claims cần review: {len([c for c in unique_claims if c in self.ambiguous_claims])}\n\n"

        summary += f"╔══ THỐNG KÊ TRACKLIST ══\n"
        summary += f"║ Tổng file trong tracklist: {len(unique_filenames_tracklist)}\n"
        summary += f"║ Tổng lần bị claim: {total_claims}\n"
        summary += f"║ File UNIQUE bị claim: {len(unique_claimed)}\n"
        summary += f"║ File KHÔNG bị claim: {len(not_claimed_filenames)}\n"
        summary += f"║ Tỷ lệ bị claim: {len(unique_claimed)}/{len(unique_filenames_tracklist)} "
        summary += f"({len(unique_claimed)/len(unique_filenames_tracklist)*100:.1f}%)\n"
        summary += f"{'='*140}\n\n"
        
        summary += f"{'='*140}\n"
        summary += f"⚠️ DANH SÁCH FILE BỊ CLAIM ({len(unique_claimed)} file)\n"
        summary += f"{'='*140}\n"
        
        claimed_by_song = {}
        for filename, count in claimed_filenames.items():
            base_name = self.get_base_song_name(filename)
            if base_name not in claimed_by_song:
                claimed_by_song[base_name] = []
            claimed_by_song[base_name].append((filename, count))
        
        for song_id, files in sorted(claimed_by_song.items()):
            summary += f"\n{song_id}:\n"
            for filename, count in sorted(files):
                summary += f"  ⚠️ {filename} ({count} lần)\n"
        
        summary += f"\n{'='*140}\n"
        summary += f"✅ DANH SÁCH FILE KHÔNG BỊ CLAIM ({len(not_claimed_filenames)} file)\n"
        summary += f"{'='*140}\n"
        
        not_claimed_by_song = {}
        for filename in sorted(not_claimed_filenames):
            base_name = self.get_base_song_name(filename)
            if base_name not in not_claimed_by_song:
                not_claimed_by_song[base_name] = []
            not_claimed_by_song[base_name].append(filename)
        
        for song_id, files in sorted(not_claimed_by_song.items()):
            summary += f"\n{song_id}:\n"
            for filename in sorted(files):
                summary += f"  ✅ {filename}\n"
        
        summary += f"\n{'='*140}\n"
        
        self.results_text.insert(tk.END, summary)
        
        # ✅ Cập nhật self.results với unique claimed_tracks
        self.results = claimed_tracks_unique
    
    def export_results(self):
        if not self.results:
            messagebox.showwarning("Cảnh báo", "Chưa có kết quả!")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        
        if filepath:
            content = self.results_text.get(1.0, tk.END)
            with open(filepath, 'w', encoding='utf-8-sig') as f:
                f.write(content)
            messagebox.showinfo("Thành công", f"Đã xuất: {filepath}")
    
    def export_csv(self):
        if not self.results:
            messagebox.showwarning("Cảnh báo", "Chưa có kết quả!")
            return
        
        # ✅ THÊM DÒNG NÀY
        unique_results = self._deduplicate_results_for_export(self.results)
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )
        
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                    f.write("File,Start,End,Claim_Start,Claim_End,Source,Song,Confidence,Percent,Status,Input_Method\n")
                    
                    # ✅ ĐỔI self.results → unique_results
                    for item in unique_results:
                        track = item['track']
                        claim = item['claim']
                        
                        file_duration = max(1, track['end'] - track['start'])
                        claim_duration = max(0, claim['end'] - claim['start'])
                        claim_percent = (claim_duration / file_duration * 100) if file_duration > 0 else 0
                        
                        status = "AUTO" if claim in self.auto_accepted_claims else "REVIEW"
                        input_method = "Text" if claim.get('source_type') == 'text' else "OCR"
                        
                        f.write(f'"{track["filename"]}",')
                        f.write(f'"{self.claim_parser.format_time(track["start"])}",')
                        f.write(f'"{self.claim_parser.format_time(track["end"])}",')
                        f.write(f'"{self.claim_parser.format_time(claim["start"])}",')
                        f.write(f'"{self.claim_parser.format_time(claim["end"])}",')
                        f.write(f'"{claim["source"]}",')
                        f.write(f'"{claim["song"]}",')
                        f.write(f'"{claim["confidence"]:.1f}",')
                        f.write(f'"{claim_percent:.1f}",')
                        f.write(f'"{status}",')
                        f.write(f'"{input_method}"\n')
                
                messagebox.showinfo("Thành công", f"Đã xuất CSV: {filepath}")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Lỗi xuất CSV:\n{str(e)}")
    
    def export_detailed(self):
        if not self.claims:
            messagebox.showwarning("Cảnh báo", "Chưa có dữ liệu!")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        
        if filepath:
            with open(filepath, 'w', encoding='utf-8-sig') as f:
                f.write("="*140 + "\n")
                f.write("BÁO CÁO CHI TIẾT - v3.7\n")
                f.write("="*140 + "\n\n")
                
                f.write("1. CLAIMS TỰ ĐỘNG CHẤP NHẬN\n")
                f.write("-"*140 + "\n\n")
                
                for idx, claim in enumerate(self.auto_accepted_claims, 1):
                    method = "📝 Text" if claim.get('source_type') == 'text' else "📷 OCR"
                    f.write(f"#{idx} ({method}):\n")
                    f.write(f"  Bài: {claim['song']}\n")
                    f.write(f"  Time: {self.claim_parser.format_time_clean(claim['start'])} — {self.claim_parser.format_time_clean(claim['end'])}\n")
                    f.write(f"  Confidence: {claim['confidence']:.1f}%\n\n")
                
                if self.ambiguous_claims:
                    f.write("\n2. CLAIMS CẦN REVIEW\n")
                    f.write("-"*140 + "\n\n")
                    
                    for idx, claim in enumerate(self.ambiguous_claims, 1):
                        method = "📝 Text" if claim.get('source_type') == 'text' else "📷 OCR"
                        f.write(f"#{idx} ({method}):\n")
                        f.write(f"  Bài: {claim['song']}\n")
                        f.write(f"  Time: {self.claim_parser.format_time_clean(claim['start'])} — {self.claim_parser.format_time_clean(claim['end'])}\n")
                        f.write(f"  Lý do: {claim.get('ambiguous_reason', 'Unknown')}\n\n")
                
                text_claims = len([c for c in self.claims if c.get('source_type') == 'text'])
                ocr_claims = len([c for c in self.claims if c.get('source_type') == 'ocr'])
                
                f.write("\n3. THỐNG KÊ\n")
                f.write(f"Tổng: {len(self.claims)}\n")
                f.write(f"Auto: {len(self.auto_accepted_claims)}\n")
                f.write(f"Review: {len(self.ambiguous_claims)}\n")
                f.write(f"Text: {text_claims}\n")
                f.write(f"OCR: {ocr_claims}\n")
                
            messagebox.showinfo("Thành công", f"Đã xuất: {filepath}")
    
    def accept_claim(self):
        """
        ✅ v3.7: Chấp nhận claim từ Review Tab
        """
        selection = self.review_tree.selection()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn claim trước!")
            return
        
        item = self.review_tree.item(selection[0])
        claim_id = int(item['values'][0]) - 1
        
        if claim_id >= len(self.ambiguous_claims):
            messagebox.showerror("Lỗi", "Claim không tồn tại!")
            return
        
        claim = self.ambiguous_claims[claim_id]
        
        # Chuyển sang auto_accepted
        self.auto_accepted_claims.append(claim)
        self.ambiguous_claims.remove(claim)
        
        # ✅ UPDATE UI - Status bar sẽ tự động cập nhật
        self.update_review_tab()
        
        # Thông báo
        remaining = len(self.ambiguous_claims)
        if remaining == 0:
            messagebox.showinfo(
                "✅ Hoàn thành Review",
                f"Đã chấp nhận claim!\n\n"
                f"✅ TẤT CẢ claims đã được xử lý!\n"
                f"📊 Tổng: {len(self.auto_accepted_claims)} claims\n\n"
                f"💡 Quay lại tab 'Kiểm Tra Claims' và nhấn\n"
                f"   'KIỂM TRA CLAIM' để xem kết quả"
            )
        else:
            # ✅ KHÔNG HIỆN POPUP NỮA - Chỉ log
            print(f"✅ Accepted claim. Remaining: {remaining}")
    
    def reject_claim(self):
        """
        ✅ v3.7: Loại bỏ claim từ Review Tab
        """
        selection = self.review_tree.selection()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn claim trước!")
            return
        
        item = self.review_tree.item(selection[0])
        claim_id = int(item['values'][0]) - 1
        
        if claim_id >= len(self.ambiguous_claims):
            messagebox.showerror("Lỗi", "Claim không tồn tại!")
            return
        
        claim = self.ambiguous_claims[claim_id]
        
        # Xác nhận
        response = messagebox.askyesno(
            "⚠️ Xác nhận loại bỏ",
            f"Bạn chắc chắn muốn LOẠI BỎ claim này?\n\n"
            f"📌 Bài: {claim['song'][:50]}\n"
            f"⏱️ Time: {self.claim_parser.format_time_clean(claim['start'])} → "
            f"{self.claim_parser.format_time_clean(claim['end'])}\n\n"
            f"❌ Claim sẽ bị XÓA HẲN khỏi dữ liệu!"
        )
        
        if not response:
            return
        
        # Xóa claim
        self.ambiguous_claims.remove(claim)
        if claim in self.claims:
            self.claims.remove(claim)
        
        # ✅ UPDATE UI
        self.update_review_tab()
        
        # Thông báo
        remaining = len(self.ambiguous_claims)
        if remaining == 0:
            messagebox.showinfo(
                "✅ Hoàn thành Review",
                f"Đã loại bỏ claim!\n\n"
                f"✅ TẤT CẢ claims đã được xử lý!\n"
                f"📊 Tổng: {len(self.auto_accepted_claims)} claims\n\n"
                f"💡 Quay lại tab 'Kiểm Tra Claims' và nhấn\n"
                f"   'KIỂM TRA CLAIM' để xem kết quả"
            )
        else:
            # ✅ KHÔNG HIỆN POPUP NỮA - Chỉ log
            print(f"❌ Rejected claim. Remaining: {remaining}")
    
    def edit_claim(self):
        """
        ✅ v3.7: Chỉnh sửa claim từ Review Tab
        
        Logic:
        1. Mở dialog chỉnh sửa
        2. Khi lưu:
           - Tạo claim mới với dữ liệu đã sửa
           - Xóa claim cũ khỏi ambiguous + self.claims
           - Thêm claim mới vào auto_accepted + self.claims
        3. Update UI
        """
        selection = self.review_tree.selection()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn claim!")
            return
        
        item = self.review_tree.item(selection[0])
        claim_id = int(item['values'][0]) - 1
        
        if claim_id >= len(self.ambiguous_claims):
            messagebox.showerror("Lỗi", "Claim không tồn tại!")
            return
        
        claim = self.ambiguous_claims[claim_id]
        
        # Tạo dialog chỉnh sửa
        edit_window = tk.Toplevel(self.root)
        edit_window.title("✏️ Chỉnh Sửa Claim")
        edit_window.geometry("600x300")
        edit_window.transient(self.root)
        edit_window.grab_set()
        
        # Title
        ttk.Label(
            edit_window, 
            text="✏️ CHỈNH SỬA CLAIM", 
            font=('Arial', 12, 'bold')
        ).grid(row=0, column=0, columnspan=2, pady=10)
        
        # Tên bài hát
        ttk.Label(edit_window, text="🎵 Tên bài hát:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        song_var = tk.StringVar(value=claim['song'])
        song_entry = ttk.Entry(edit_window, textvariable=song_var, width=50)
        song_entry.grid(row=1, column=1, padx=10, pady=5)
        
        # Start time
        ttk.Label(edit_window, text="⏱️ Start (giây):").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        start_var = tk.IntVar(value=claim['start'])
        start_entry = ttk.Entry(edit_window, textvariable=start_var, width=50)
        start_entry.grid(row=2, column=1, padx=10, pady=5)
        
        # End time
        ttk.Label(edit_window, text="⏱️ End (giây):").grid(row=3, column=0, sticky=tk.W, padx=10, pady=5)
        end_var = tk.IntVar(value=claim['end'])
        end_entry = ttk.Entry(edit_window, textvariable=end_var, width=50)
        end_entry.grid(row=3, column=1, padx=10, pady=5)
        
        # Hiển thị preview
        preview_label = ttk.Label(edit_window, text="", foreground="blue")
        preview_label.grid(row=4, column=0, columnspan=2, pady=5)
        
        def update_preview(*args):
            try:
                start = start_var.get()
                end = end_var.get()
                duration = end - start
                preview_label.config(
                    text=f"⏱️ Preview: {self.claim_parser.format_time_clean(start)} → "
                         f"{self.claim_parser.format_time_clean(end)} "
                         f"(Duration: {duration}s)"
                )
            except:
                preview_label.config(text="")
        
        start_var.trace('w', update_preview)
        end_var.trace('w', update_preview)
        update_preview()
        
        # Buttons frame
        btn_frame = ttk.Frame(edit_window)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=15)
        
        def save():
            try:
                new_song = song_var.get().strip()
                new_start = start_var.get()
                new_end = end_var.get()
                
                # Validate
                if not new_song:
                    messagebox.showerror("Lỗi", "Tên bài hát không được để trống!")
                    return
                
                if new_start >= new_end:
                    messagebox.showerror("Lỗi", "Start phải nhỏ hơn End!")
                    return
                
                if new_start < 0 or new_end < 0:
                    messagebox.showerror("Lỗi", "Timestamp không được âm!")
                    return
                
                # ✅ TẠO CLAIM MỚI
                new_claim = {
                    'song': new_song,
                    'start': new_start,
                    'end': new_end,
                    'duration': new_end - new_start,
                    'source': claim['source'],
                    'source_type': claim['source_type'],
                    'confidence': 100,  # Đã được user xác nhận
                    'song_confidence': 100
                }
                
                # ✅ XÓA CLAIM CŨ
                self.ambiguous_claims.remove(claim)
                if claim in self.claims:
                    self.claims.remove(claim)
                
                # ✅ THÊM CLAIM MỚI
                self.claims.append(new_claim)
                self.auto_accepted_claims.append(new_claim)
                
                # Update UI
                self.update_review_tab()
                edit_window.destroy()
                
                # Thông báo
                remaining = len(self.ambiguous_claims)
                if remaining == 0:
                    messagebox.showinfo(
                        "✅ Hoàn thành",
                        f"Đã cập nhật claim!\n\n"
                        f"✅ TẤT CẢ claims đã được xử lý!\n"
                        f"📊 Tổng: {len(self.auto_accepted_claims)} claims\n\n"
                        f"💡 Quay lại tab 'Kiểm Tra Claims' và nhấn\n"
                        f"   'KIỂM TRA CLAIM' để xem kết quả"
                    )
                else:
                    messagebox.showinfo(
                        "✅ Đã cập nhật",
                        f"Đã cập nhật claim!\n\n"
                        f"⚠️ Còn {remaining} claim(s) cần xử lý"
                    )
                
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể lưu:\n{str(e)}")
        
        def cancel():
            edit_window.destroy()
        
        ttk.Button(btn_frame, text="💾 Lưu & Chấp nhận", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="❌ Hủy", command=cancel).pack(side=tk.LEFT, padx=5)
        
        # Focus vào ô đầu tiên
        song_entry.focus()
    
    def accept_all_claims(self):
        """
        ✅ v3.7: Chấp nhận TẤT CẢ ambiguous claims
        
        Cảnh báo rõ ràng về các vấn đề trước khi chấp nhận
        """
        if not self.ambiguous_claims:
            messagebox.showinfo("Thông báo", "Không có claim nào cần review!")
            return
        
        # Tạo danh sách chi tiết các vấn đề
        issues_text = ""
        for idx, claim in enumerate(self.ambiguous_claims, 1):
            reason = claim.get('ambiguous_reason', 'Unknown')
            issues_text += f"\n{idx}. {claim['song'][:40]}\n"
            issues_text += f"   ⚠️ {reason}\n"
        
        # Xác nhận với cảnh báo chi tiết
        confirm = messagebox.askyesno(
            "⚠️ XÁC NHẬN CHẤP NHẬN TẤT CẢ",
            f"Bạn đang chấp nhận {len(self.ambiguous_claims)} claims có vấn đề:\n"
            f"{issues_text}\n\n"
            f"❌ CÁC CLAIMS NÀY CÓ THỂ SAI/NHẦM!\n\n"
            f"Chắc chắn chấp nhận tất cả?"
        )
        
        if not confirm:
            return
        
        # Chuyển tất cả sang auto_accepted
        self.auto_accepted_claims.extend(self.ambiguous_claims)
        self.ambiguous_claims = []
        
        # Update UI
        self.update_review_tab()
        
        # Thông báo
        messagebox.showinfo(
            "✅ Hoàn thành",
            f"Đã chấp nhận tất cả claims!\n\n"
            f"📊 Tổng: {len(self.auto_accepted_claims)} claims\n\n"
            f"💡 Quay lại tab 'Kiểm Tra Claims' và nhấn\n"
            f"   'KIỂM TRA CLAIM' để xem kết quả"
        )
    
    def reprocess_claims(self):
        """
        ✅ v3.7: KHÔNG CẦN NỮA - User không cần "xử lý lại"
        
        Flow mới:
        - User review xong → Quay tab chính → Nhấn "KIỂM TRA CLAIM"
        - Không cần nút "Xử Lý Lại" trong Review Tab
        """
        messagebox.showinfo(
            "ℹ️ Hướng dẫn",
            "✅ CÁCH XEM KẾT QUẢ:\n\n"
            "1. Xử lý xong các claims trong Review Tab\n"
            "2. Quay lại tab 'Kiểm Tra Claims'\n"
            "3. Nhấn nút 'KIỂM TRA CLAIM'\n"
            "4. Kết quả sẽ hiển thị claims đã review\n\n"
            "💡 Không cần nhấn 'Xử Lý Lại' nữa!"
        )

    def go_back_to_main_tab(self):
        """
        ✅ v3.7: Quay lại tab chính với status rõ ràng
        """
        remaining = len(self.ambiguous_claims)
        accepted = len(self.auto_accepted_claims)
        
        # Nếu còn claims chưa xử lý → Cảnh báo
        if remaining > 0:
            response = messagebox.askyesno(
                "⚠️ Còn Claims Chưa Xử Lý",
                f"Còn {remaining} claim(s) chưa được xử lý!\n\n"
                f"📊 Hiện tại:\n"
                f"  ✅ Đã chấp nhận: {accepted} claims\n"
                f"  ⚠️ Chưa xử lý: {remaining} claims\n\n"
                f"Bạn muốn:\n"
                f"• YES: Tiếp tục review (ở lại tab này)\n"
                f"• NO: Quay lại tab chính (claims chưa xử lý sẽ bị bỏ qua)"
            )
            
            if response:  # YES → Ở lại
                return
        
        # Chuyển về tab chính
        self.notebook.select(0)
        
        # Thông báo hướng dẫn
        if remaining == 0:
            messagebox.showinfo(
                "✅ Đã Xong Review",
                f"✅ Tất cả claims đã được xử lý!\n\n"
                f"📊 Tổng: {accepted} claims đã chấp nhận\n\n"
                f"💡 BƯỚC TIẾP THEO:\n"
                f"   1. Nhấn nút 'KIỂM TRA CLAIM'\n"
                f"   2. Xem kết quả so sánh với tracklist"
            )
        else:
            messagebox.showinfo(
                "ℹ️ Quay Lại",
                f"⚠️ Đã bỏ qua {remaining} claim(s) chưa xử lý\n\n"
                f"📊 Sẽ xử lý: {accepted} claims đã chấp nhận\n\n"
                f"💡 BƯỚC TIẾP THEO:\n"
                f"   1. Nhấn nút 'KIỂM TRA CLAIM'\n"
                f"   2. Kết quả sẽ chỉ bao gồm claims đã chấp nhận"
            )

# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    root = tk.Tk()
    app = ClaimCheckerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()