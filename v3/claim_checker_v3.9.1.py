import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import re
from datetime import timedelta
from pathlib import Path
import pytesseract
from PIL import Image, ImageGrab, ImageEnhance, ImageFilter
import os
import difflib
import json

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
        # BƯỚC 1: Loại bỏ ALL noise text
        unwanted_patterns = [
            r'Video sử dụng giai điệu',
            r'Các bên xác nhận',
            r'Loại nội dung',
        ]
        for pattern in unwanted_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # BƯỚC 2: Chuẩn hóa Unicode dashes
        text = text.replace('\u2014', '—')
        text = text.replace('\u2013', '—')
        text = text.replace('\u2012', '—')
        text = text.replace('–', '—')
        text = text.replace('-', '—')
        
        # BƯỚC 3: Chuẩn hóa whitespace
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = re.sub(r'[ \t]+', ' ', line).strip()
            cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)
        
        # BƯỚC 4: Clean up pipes thừa
        text = re.sub(r'\|\s*\|', '|', text)
        text = re.sub(r'^\s*\|\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*\|\s*$', '', text, flags=re.MULTILINE)
        
        # BƯỚC 5: Xử lý separator lines
        lines = text.split('\n')
        filtered_lines = []
        for line in lines:
            if re.match(r'^[=\-\s]{10,}$', line):
                continue
            filtered_lines.append(line)
        
        text = '\n'.join(filtered_lines)
        
        return text.strip()
        
    def extract_song_name(self, text, source_type="unknown"):
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
        timestamps = []
        
        # ✅ BƯỚC 0: XỬ LÝ TIMESTAMPS DÍNH LIỀN - Thêm SPACE thay vì em dash
        temp_text = text
        
        # Strategy: Thêm SPACE giữa các timestamps dính liền
        # Điều này giúp patterns gốc vẫn hoạt động
        
        # Pattern 1: H:MM:SS + digit → thêm space
        # VD: "1:57:45" + "2" (từ 2:01:57) → "1:57:45 2"
        temp_text = re.sub(
            r'(\d{1,2}:\d{2}:\d{2})(?=\d)',  # Lookahead: sau timestamp là digit
            r'\1 ',  # Thêm space
            temp_text
        )
        
        # Pattern 2: MM:SS + digit → thêm space
        temp_text = re.sub(
            r'(\d{1,2}:\d{2})(?=\d{1,2}:\d{2})',  # Lookahead: sau MM:SS là H:MM:SS
            r'\1 ',
            temp_text
        )
        
        # Chạy lại để catch các case phức tạp
        for _ in range(2):
            temp_text = re.sub(r'(\d{1,2}:\d{2}:\d{2})(?=\d)', r'\1 ', temp_text)
            temp_text = re.sub(r'(\d{1,2}:\d{2})(?=\d{1,2}:\d{2})', r'\1 ', temp_text)
        
        # ✅ BƯỚC 1: EXTRACT với các patterns GỐC
        # Chỉ dùng patterns CHÍNH XÁC nhất (có em dash rõ ràng)
        main_patterns = [
            # Pattern 1: H:MM:SS — H:MM:SS (standard)
            r'(\d{1,2}):(\d{2}):(\d{2})\s*[—–-]\s*(\d{1,2}):(\d{2}):(\d{2})',
            
            # Pattern 2: MM:SS — MM:SS (short)
            r'(?<!:)(\d{1,2}):(\d{2})\s*[—–-]\s*(\d{1,2}):(\d{2})(?!:)',
        ]
        
        for pattern in main_patterns:
            matches = re.findall(pattern, temp_text)
            
            for match in matches:
                try:
                    if len(match) == 6:  # H:MM:SS — H:MM:SS
                        start_h, start_m, start_s, end_h, end_m, end_s = map(int, match)
                        start_seconds = start_h * 3600 + start_m * 60 + start_s
                        end_seconds = end_h * 3600 + end_m * 60 + end_s
                    
                    elif len(match) == 4:  # MM:SS — MM:SS
                        start_m, start_s, end_m, end_s = map(int, match)
                        start_h = 0
                        end_h = 0
                        start_seconds = start_m * 60 + start_s
                        end_seconds = end_m * 60 + end_s
                    else:
                        continue
                    
                    # ✅ VALIDATION
                    if not self._is_valid_timestamp(start_seconds, end_seconds):
                        continue
                    
                    # ✅ KIỂM TRA: Duration phải >= 10 giây (loại bỏ timestamps quá ngắn)
                    if end_seconds - start_seconds < 10:
                        continue
                    
                    timestamps.append((start_seconds, end_seconds))
                    
                except (ValueError, IndexError):
                    continue
        
        # BƯỚC 2: Loại bỏ duplicates
        timestamps = list(set(timestamps))
        timestamps.sort(key=lambda x: x[0])
        
        # ✅ BƯỚC 3: Loại bỏ timestamps CHỒNG CHÉO (overlap)
        # Nếu 2 timestamps overlap > 80% → chỉ giữ 1
        filtered_timestamps = []
        
        for ts in timestamps:
            start, end = ts
            is_duplicate = False
            
            for existing in filtered_timestamps:
                ex_start, ex_end = existing
                
                # Tính overlap
                overlap_start = max(start, ex_start)
                overlap_end = min(end, ex_end)
                
                if overlap_start < overlap_end:
                    overlap_duration = overlap_end - overlap_start
                    ts_duration = end - start
                    ex_duration = ex_end - ex_start
                    
                    # Nếu overlap > 80% duration của timestamp ngắn hơn → duplicate
                    min_duration = min(ts_duration, ex_duration)
                    if overlap_duration / min_duration > 0.8:
                        is_duplicate = True
                        # Giữ timestamp dài hơn (chính xác hơn)
                        if ts_duration > ex_duration:
                            filtered_timestamps.remove(existing)
                            filtered_timestamps.append(ts)
                        break
            
            if not is_duplicate:
                filtered_timestamps.append(ts)
        
        # BƯỚC 4: Sort lại
        filtered_timestamps.sort(key=lambda x: x[0])
        
        return filtered_timestamps

    def _normalize_song_name_v2(self, song_name):
        """
        ✅ NORMALIZE TÊN BÀI - Cải thiện cho substring matching
        Version 2: Loại bỏ keywords, special chars, tối ưu cho so sánh
        """
        import unicodedata
        import re
        
        # 1. Remove accents
        normalized = unicodedata.normalize('NFD', song_name)
        normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        
        # 2. Lowercase
        normalized = normalized.lower().strip()
        
        # 3. Remove số đầu: "15- " → ""
        normalized = re.sub(r'^\d+-\s*', '', normalized)
        
        # 4. Remove parentheses: "(acoustic)" → ""
        normalized = re.sub(r'\([^)]*\)', '', normalized)
        normalized = re.sub(r'\[[^\]]*\]', '', normalized)
        
        # 5. Remove common keywords
        keywords = [
            'cover', 'acoustic', 'acustico', 'live', 'ao vivo', 'en vivo',
            'remix', 'feat', 'ft', 'featuring', 'con', 'with',
            'official', 'video', 'audio', 'lyric', 'letra'
        ]
        for kw in keywords:
            normalized = re.sub(rf'\b{kw}\b', '', normalized)
        
        # 6. Remove special chars (giữ space và hyphen)
        normalized = re.sub(r'[^\w\s-]', '', normalized)
        
        # 7. Remove multiple spaces/hyphens
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'-+', '-', normalized)
        normalized = normalized.strip('- ')
        
        return normalized

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
        return str(timedelta(seconds=seconds))

    @staticmethod
    def format_time_clean(seconds):
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
        self.root.title("YouTube Claim Checker v3.9.1")
        self.root.geometry("1400x1000")
        
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
        
        # ✅ THÊM: Load matching settings
        self.matching_settings = self.load_matching_settings()
        print(f"📊 Matching settings loaded: {self.matching_settings}")
        
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

    # ============================================
    # 🆕 HÀM MỚI 1: ĐẾM TẦN SUẤT CLAIM
    # ============================================
    def _count_claim_frequency(self, song_name):
        """
        ✅ Đếm số lần một bài nhạc xuất hiện trong danh sách claims
        
        Args:
            song_name: Tên bài cần đếm
        
        Returns:
            int: Số lần xuất hiện
        """
        normalized_target = self.claim_parser._normalize_song_name_v2(song_name)
        
        if not normalized_target:
            return 0
        
        count = 0
        for claim in self.claims:
            normalized_claim = self.claim_parser._normalize_song_name_v2(claim['song'])
            
            # Xét substring hoặc similarity cao
            if (normalized_target in normalized_claim or 
                normalized_claim in normalized_target):
                count += 1
        
        return count


    # ============================================
    # 🆕 HÀM MỚI 2: LOAD SETTINGS TỪ FILE
    # ============================================
    def load_matching_settings(self):
        """
        ✅ Load settings từ file JSON
        Nếu không có file → Tạo settings mặc định
        """
        settings_file = Path.cwd() / "matching_settings.json"
        
        # Default settings
        default_settings = {
            'name_similarity_auto_accept': 80,
            'name_similarity_need_review': 40,
            'name_similarity_reject': 0,
            'overlap_percent_auto_accept': 50,
            'overlap_percent_need_review': 30,
            'overlap_percent_reject': 20,
            'min_absolute_duration': 10,
            'frequency_rescue_threshold': 3,
            'frequency_rescue_min_overlap': 20,
            'ocr_confidence_threshold': 50,
        }
        
        try:
            if settings_file.exists():
                with open(settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    
                    # Merge với default (đề phòng thiếu key)
                    settings = default_settings.copy()
                    settings.update(loaded)
                    
                    print(f"✅ Loaded settings from {settings_file}")
                    return settings
            else:
                # Lần đầu tiên → Tạo file mặc định
                with open(settings_file, 'w', encoding='utf-8') as f:
                    json.dump(default_settings, f, indent=2, ensure_ascii=False)
                
                print(f"✅ Created default settings at {settings_file}")
                return default_settings
        
        except Exception as e:
            print(f"⚠️ Error loading settings: {e}")
            return default_settings

    # ============================================
    # 🆕 HÀM MỚI 3: SAVE SETTINGS VÀO FILE
    # ============================================
    def save_matching_settings(self, settings=None):
        """
        ✅ Save settings vào file JSON
        
        Args:
            settings: Dict settings cần save (None = dùng self.matching_settings)
        """
        if settings is None:
            settings = self.matching_settings
        
        settings_file = Path.cwd() / "matching_settings.json"
        
        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Saved settings to {settings_file}")
            return True
        
        except Exception as e:
            print(f"❌ Error saving settings: {e}")
            return False

    # ============================================
    # 🆕 HÀM MỚI 4: RESET SETTINGS VỀ MẶC ĐỊNH
    # ============================================
    def reset_matching_settings(self):
        """
        ✅ Reset settings về giá trị mặc định
        """
        default_settings = {
            'name_similarity_auto_accept': 80,
            'name_similarity_need_review': 40,
            'name_similarity_reject': 0,
            'overlap_percent_auto_accept': 50,
            'overlap_percent_need_review': 30,
            'overlap_percent_reject': 20,
            'min_absolute_duration': 10,
            'frequency_rescue_threshold': 3,
            'frequency_rescue_min_overlap': 20,
            'ocr_confidence_threshold': 50,
        }
        
        self.matching_settings = default_settings
        self.save_matching_settings()
        
        # Update UI nếu Settings Tab đang mở
        if hasattr(self, 'settings_vars'):
            for key, var in self.settings_vars.items():
                var.set(default_settings[key])
        
        print("✅ Reset settings to default values")
        return True

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        title_label = ttk.Label(main_frame, text="YOUTUBE CLAIM CHECKER v3.9.1", 
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
        
        # ✅ THÊM TAB DI CHUYỂN FILE
        self.move_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.move_tab, text="📁 Di Chuyển File")
        self.setup_move_tab()
        
        # ✅ THÊM TAB QUẢN LÝ THƯ MỤC
        self.cleanup_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.cleanup_tab, text="🗑️ Quản Lý Thư Mục")
        self.setup_cleanup_tab()
        
        # ✅ THÊM TAB SETTINGS
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text="⚙️ Settings")
        self.setup_settings_tab()
        
        # Đăng ký event handler cho tab change
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
    
    def setup_main_tab(self):
        """
        ✅ v3.8: CARD LAYOUT UI - Professional & Clear Workflow
        """
        # ============================================
        # HEADER - TITLE BAR
        # ============================================
        header_frame = ttk.Frame(self.main_tab)
        header_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(
            header_frame, 
            text="📋 WORKFLOW: Tracklist → Input Claims → Kiểm Tra → Xem Kết Quả",
            font=('Arial', 10, 'bold'),
            foreground='blue'
        ).pack()
        
        # ============================================
        # CARD CONTAINER
        # ============================================
        cards_frame = ttk.Frame(self.main_tab)
        cards_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # ============================================
        # CARD 1: INPUT
        # ============================================
        input_card = ttk.LabelFrame(cards_frame, text="📁 BƯỚC 1: INPUT DATA", padding="15")
        input_card.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), padx=5)
        
        # Tracklist
        ttk.Label(input_card, text="📄 Tracklist:", font=('Arial', 9, 'bold')).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 5)
        )
        self.txt_path = tk.StringVar()
        txt_entry = ttk.Entry(input_card, textvariable=self.txt_path, width=30, state='readonly')
        txt_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        ttk.Button(input_card, text="📁 Chọn TXT", command=self.load_txt, width=15).grid(
            row=2, column=0, pady=(0, 15)
        )
        
        # Input Mode Selection
        ttk.Label(input_card, text="📥 Phương thức input:", font=('Arial', 9, 'bold')).grid(
            row=3, column=0, sticky=tk.W, pady=(0, 5)
        )
        
        mode_frame = ttk.Frame(input_card)
        mode_frame.grid(row=4, column=0, sticky=tk.W)
        
        ttk.Radiobutton(
            mode_frame, 
            text="🖼️ Ảnh (OCR)", 
            variable=self.input_mode, 
            value="image",
            command=self.toggle_input_mode
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Radiobutton(
            mode_frame, 
            text="📝 Text", 
            variable=self.input_mode, 
            value="text",
            command=self.toggle_input_mode
        ).pack(side=tk.LEFT)
        
        # Status
        ttk.Separator(input_card, orient='horizontal').grid(
            row=5, column=0, sticky=(tk.W, tk.E), pady=10
        )
        
        ttk.Label(input_card, text="📊 Trạng thái:", font=('Arial', 9, 'bold')).grid(
            row=6, column=0, sticky=tk.W
        )
        self.img_count = tk.StringVar(value="⚪ Chưa có dữ liệu")
        ttk.Label(input_card, textvariable=self.img_count, foreground='gray').grid(
            row=7, column=0, sticky=tk.W
        )
        
        # ============================================
        # CARD 2: PROCESS
        # ============================================
        process_card = ttk.LabelFrame(cards_frame, text="🔍 BƯỚC 2: XỬ LÝ", padding="15")
        process_card.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N), padx=5)
        
        # Status indicators
        self.process_status_frame = ttk.Frame(process_card)
        self.process_status_frame.pack(fill=tk.BOTH, expand=True)
        
        self.status_tracklist = ttk.Label(
            self.process_status_frame, 
            text="⚪ Tracklist: Chưa load",
            font=('Arial', 9)
        )
        self.status_tracklist.pack(anchor=tk.W, pady=2)
        
        self.status_claims = ttk.Label(
            self.process_status_frame, 
            text="⚪ Claims: 0",
            font=('Arial', 9)
        )
        self.status_claims.pack(anchor=tk.W, pady=2)
        
        self.status_review = ttk.Label(
            self.process_status_frame, 
            text="⚪ Review: 0",
            font=('Arial', 9)
        )
        self.status_review.pack(anchor=tk.W, pady=2)
        
        ttk.Separator(process_card, orient='horizontal').pack(fill=tk.X, pady=15)
        
        # Main process button
        ttk.Button(
            process_card, 
            text="🔍 KIỂM TRA CLAIM", 
            command=self.process_claims,
            style='Accent.TButton'
        ).pack(fill=tk.X, pady=5)
        
        ttk.Label(
            process_card,
            text="💡 Sẽ tự động validate\nvà chuyển Review nếu cần",
            font=('Arial', 8),
            foreground='gray',
            justify=tk.CENTER
        ).pack(pady=(5, 0))
        
        # ============================================
        # CARD 3: QUICK ACTIONS
        # ============================================
        actions_card = ttk.LabelFrame(cards_frame, text="🔄 QUICK ACTIONS", padding="15")
        actions_card.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N), padx=5)
        
        ttk.Button(
            actions_card, 
            text="🗑️ Xóa Text Input", 
            command=self.clear_text_input,
            width=20
        ).pack(fill=tk.X, pady=3)
        
        ttk.Button(
            actions_card, 
            text="🗑️ Xóa Claims", 
            command=self.clear_all_claims_smart,
            width=20
        ).pack(fill=tk.X, pady=3)
        
        ttk.Button(
            actions_card, 
            text="🗑️ Xóa Images", 
            command=self.clear_images,
            width=20
        ).pack(fill=tk.X, pady=3)
        
        ttk.Separator(actions_card, orient='horizontal').pack(fill=tk.X, pady=8)
        
        ttk.Button(
            actions_card, 
            text="🔄 RESET TOÀN BỘ", 
            command=self.reset_all_data,
            width=20
        ).pack(fill=tk.X, pady=3)
        
        ttk.Label(
            actions_card,
            text="⚠️ Xóa tất cả về\ntrạng thái ban đầu",
            font=('Arial', 8),
            foreground='red',
            justify=tk.CENTER
        ).pack(pady=(5, 0))
        
        # ============================================
        # MAIN CONTENT AREA
        # ============================================
        content_frame = ttk.Frame(self.main_tab)
        content_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        # Image input section
        self.image_frame = ttk.LabelFrame(content_frame, text="🖼️ Input từ Ảnh (OCR)", padding="10")
        self.image_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        img_btn_frame = ttk.Frame(self.image_frame)
        img_btn_frame.pack(fill=tk.X)
        
        ttk.Button(img_btn_frame, text="📁 Chọn File Ảnh", command=self.load_images).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(img_btn_frame, text="📋 Paste (Ctrl+V)", command=self.paste_image).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(img_btn_frame, text="🛠️ Debug OCR", command=self.debug_last_image).pack(
            side=tk.LEFT, padx=2
        )
        
        # Text input section
        self.text_frame = ttk.LabelFrame(content_frame, text="📝 Input từ Text", padding="10")
        self.text_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        self.text_frame.grid_remove()
        
        # Header with paste button
        text_header_frame = ttk.Frame(self.text_frame)
        text_header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        ttk.Label(text_header_frame, text="Paste text claim:", font=('Arial', 9, 'bold')).pack(
            side=tk.LEFT
        )
        ttk.Button(text_header_frame, text="📋 Paste", command=self.paste_text_claim).pack(
            side=tk.LEFT, padx=10
        )
        
        self.text_input = scrolledtext.ScrolledText(
            self.text_frame, 
            width=100, 
            height=8, 
            font=('Consolas', 9)
        )
        self.text_input.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        text_btn_frame = ttk.Frame(self.text_frame)
        text_btn_frame.grid(row=2, column=0, pady=5)
        
        ttk.Button(text_btn_frame, text="➕ Thêm Claims", command=self.add_text_claims).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(text_btn_frame, text="📄 Sắp Xếp", command=self.sort_text_input).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(text_btn_frame, text="📜 Xem Lịch Sử", command=self.view_text_history).pack(
            side=tk.LEFT, padx=2
        )
        
        ttk.Label(self.text_frame, text="Claims đã nhập:", font=('Arial', 9, 'bold')).grid(
            row=3, column=0, sticky=tk.W, pady=(10, 0)
        )
        
        self.text_claims_display = scrolledtext.ScrolledText(
            self.text_frame, 
            width=100, 
            height=10,
            font=('Consolas', 9), 
            wrap=tk.WORD,
            state='disabled'
        )
        self.text_claims_display.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # ============================================
        # RESULTS SECTION
        # ============================================
        results_frame = ttk.LabelFrame(self.main_tab, text="📊 KẾT QUẢ KIỂM TRA", padding="10")
        results_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.results_text = scrolledtext.ScrolledText(
            results_frame, 
            width=160, 
            height=25, 
            font=('Consolas', 9)
        )
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        export_frame = ttk.Frame(results_frame)
        export_frame.grid(row=1, column=0, pady=5)
        
        ttk.Button(export_frame, text="💾 Xuất TXT", command=self.export_results).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(export_frame, text="📊 Xuất CSV", command=self.export_csv).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(export_frame, text="📄 Xuất Chi Tiết", command=self.export_detailed).pack(
            side=tk.LEFT, padx=2
        )
        
        # ============================================
        # GRID CONFIGURATION
        # ============================================
        self.main_tab.columnconfigure(0, weight=1)
        self.main_tab.columnconfigure(1, weight=1)
        self.main_tab.columnconfigure(2, weight=1)
        self.main_tab.rowconfigure(2, weight=1)
        self.main_tab.rowconfigure(3, weight=2)
        
        cards_frame.columnconfigure(0, weight=1)
        cards_frame.columnconfigure(1, weight=1)
        cards_frame.columnconfigure(2, weight=1)
        
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)
        
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
            self.update_main_tab_status()
            
        except Exception as e:
            print("\n" + "="*80)
            print("❌ DEBUG: ERROR")
            print("="*80)
            import traceback
            traceback.print_exc()
            print("="*80 + "\n")
            
            messagebox.showerror("Lỗi", f"Không thể parse text:\n{str(e)}")
    
    def update_text_claims_display(self):
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

    def reset_all_data(self):
        """
        ✅ v3.8: RESET TOÀN BỘ - Xóa tất cả dữ liệu về trạng thái ban đầu
        
        Xóa:
        - Text input
        - Text claims display
        - OCR claims (nếu có)
        - Results
        - Review tab
        - Validation state
        """
        # Kiểm tra có dữ liệu không
        has_data = (
            self.text_input.get("1.0", tk.END).strip() or 
            self.claims or 
            self.results or
            self.pasted_images
        )
        
        if not has_data:
            messagebox.showinfo("Thông báo", "Không có dữ liệu để xóa!")
            return
        
        # Xác nhận
        confirm = messagebox.askyesno(
            "⚠️ XÁC NHẬN RESET",
            "🔄 SẼ XÓA TOÀN BỘ:\n\n"
            "  ❌ Text đã paste\n"
            "  ❌ Claims đã phát hiện (Text + OCR)\n"
            "  ❌ Ảnh đã load\n"
            "  ❌ Kết quả kiểm tra\n"
            "  ❌ Review claims\n\n"
            "⚠️ KHÔNG THỂ HOÀN TÁC!\n\n"
            "Chắc chắn reset?"
        )
        
        if not confirm:
            return
        
        try:
            # ============================================
            # BỘ 1: XÓA TEXT INPUT
            # ============================================
            self.text_input.delete("1.0", tk.END)
            
            # ============================================
            # BỘ 2: XÓA CLAIMS (TEXT + OCR)
            # ============================================
            self.claims = []
            self.ambiguous_claims = []
            self.auto_accepted_claims = []
            
            # ============================================
            # BỘ 3: XÓA IMAGES
            # ============================================
            self.pasted_images = []
            
            # ============================================
            # BỘ 4: XÓA RESULTS
            # ============================================
            self.results = []
            self.results_text.delete(1.0, tk.END)
            
            # ============================================
            # BỘ 5: RESET VALIDATION STATE
            # ============================================
            self._validated = False
            
            # ============================================
            # BỘ 6: UPDATE UI
            # ============================================
            # Update text claims display
            self.text_claims_display.config(state='normal')
            self.text_claims_display.delete("1.0", tk.END)
            self.text_claims_display.config(state='disabled')
            
            # Update counters
            self.img_count.set("⚪ Chưa có dữ liệu")
            
            # Update review tab
            self.update_review_tab()
            
            # Update move tab (nếu có)
            if hasattr(self, 'move_tab'):
                for item in self.move_tree.get_children():
                    self.move_tree.delete(item)
                if hasattr(self, 'move_status_label'):
                    self.move_status_label.config(text="")
            
            # ============================================
            # BỘ 7: THÔNG BÁO
            # ============================================
            messagebox.showinfo(
                "✅ Reset Hoàn Tất",
                "🔄 Đã reset toàn bộ về trạng thái ban đầu!\n\n"
                "📋 Tracklist vẫn được giữ nguyên.\n"
                "🎯 Sẵn sàng cho lần kiểm tra mới!"
            )
            
            print("\n" + "="*80)
            print("🔄 RESET ALL DATA - SUCCESS")
            print("="*80)
            print("✅ Text input: Cleared")
            print("✅ Claims: Cleared")
            print("✅ Images: Cleared")
            print("✅ Results: Cleared")
            print("✅ Review tab: Cleared")
            print("✅ Validation state: Reset")
            print("="*80 + "\n")
            self.update_main_tab_status()
            
            # ============================================
            # BỘ 8: UPDATE STATUS (nếu có UI mới)
            # ============================================
            if hasattr(self, 'update_main_tab_status'):
                self.update_main_tab_status()
            
        except Exception as e:
            messagebox.showerror("Lỗi Reset", f"Không thể reset:\n{str(e)}")
            print(f"❌ Reset error: {e}")
            import traceback
            traceback.print_exc()

    def update_main_tab_status(self):
        """
        ✅ v3.8: Cập nhật status indicators trên Card 2
        """
        # Tracklist status
        if self.tracklist:
            self.status_tracklist.config(
                text=f"✅ Tracklist: {len(self.tracklist)} bài",
                foreground='green'
            )
        else:
            self.status_tracklist.config(
                text="⚪ Tracklist: Chưa load",
                foreground='gray'
            )
        
        # Claims status
        total_claims = len(self.claims)
        if total_claims > 0:
            text_claims = len([c for c in self.claims if c.get('source_type') == 'text'])
            ocr_claims = len([c for c in self.claims if c.get('source_type') == 'ocr'])
            self.status_claims.config(
                text=f"✅ Claims: {total_claims} (📝 {text_claims} | 🖼️ {ocr_claims})",
                foreground='green'
            )
        else:
            self.status_claims.config(
                text="⚪ Claims: 0",
                foreground='gray'
            )
        
        # Review status
        review_count = len(self.ambiguous_claims)
        if review_count > 0:
            self.status_review.config(
                text=f"⚠️ Review: {review_count} cần xử lý",
                foreground='orange'
            )
        else:
            if total_claims > 0:
                self.status_review.config(
                    text="✅ Review: Hoàn tất",
                    foreground='green'
                )
            else:
                self.status_review.config(
                    text="⚪ Review: 0",
                    foreground='gray'
                )

    def clear_all_claims_smart(self):
        """
        ✅ v3.8: Xóa claims thông minh - hỏi user muốn xóa gì
        """
        if not self.claims:
            messagebox.showinfo("Thông báo", "Không có claims để xóa!")
            return
        
        text_claims = len([c for c in self.claims if c.get('source_type') == 'text'])
        ocr_claims = len([c for c in self.claims if c.get('source_type') == 'ocr'])
        
        # Tạo dialog chọn
        dialog = tk.Toplevel(self.root)
        dialog.title("🗑️ Xóa Claims")
        dialog.geometry("350x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(
            dialog, 
            text="🗑️ XÓA CLAIMS", 
            font=('Arial', 12, 'bold')
        ).pack(pady=10)
        
        ttk.Label(
            dialog,
            text=f"📝 Text claims: {text_claims}\n🖼️ OCR claims: {ocr_claims}\n📊 Tổng: {len(self.claims)}",
            justify=tk.CENTER
        ).pack(pady=10)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        
        def delete_text_only():
            self.claims = [c for c in self.claims if c.get('source_type') != 'text']
            self.auto_accepted_claims = [c for c in self.auto_accepted_claims if c.get('source_type') != 'text']
            self.ambiguous_claims = [c for c in self.ambiguous_claims if c.get('source_type') != 'text']
            if not self.claims:
                self._validated = False
            self.update_text_claims_display()
            self.update_main_tab_status()
            dialog.destroy()
            messagebox.showinfo("Đã xóa", f"✅ Đã xóa {text_claims} text claims")
        
        def delete_ocr_only():
            self.claims = [c for c in self.claims if c.get('source_type') != 'ocr']
            self.auto_accepted_claims = [c for c in self.auto_accepted_claims if c.get('source_type') != 'ocr']
            self.ambiguous_claims = [c for c in self.ambiguous_claims if c.get('source_type') != 'ocr']
            self.pasted_images = []
            if not self.claims:
                self._validated = False
            self.update_image_count()
            self.update_main_tab_status()
            dialog.destroy()
            messagebox.showinfo("Đã xóa", f"✅ Đã xóa {ocr_claims} OCR claims")
        
        def delete_all():
            count = len(self.claims)
            self.claims = []
            self.auto_accepted_claims = []
            self.ambiguous_claims = []
            self.pasted_images = []
            self._validated = False
            self.update_text_claims_display()
            self.update_image_count()
            self.update_main_tab_status()
            dialog.destroy()
            messagebox.showinfo("Đã xóa", f"✅ Đã xóa {count} claims")
        
        if text_claims > 0:
            ttk.Button(btn_frame, text="📝 Xóa Text", command=delete_text_only, width=12).pack(
                side=tk.LEFT, padx=3
            )
        
        if ocr_claims > 0:
            ttk.Button(btn_frame, text="🖼️ Xóa OCR", command=delete_ocr_only, width=12).pack(
                side=tk.LEFT, padx=3
            )
        
        ttk.Button(btn_frame, text="🗑️ Xóa Tất Cả", command=delete_all, width=12).pack(
            side=tk.LEFT, padx=3
        )
        
        ttk.Button(dialog, text="❌ Hủy", command=dialog.destroy).pack(pady=5)
    
    def setup_review_tab(self):
        # ============================================
        # PHẦN 1: INFO FRAME - Hướng dẫn chi tiết
        # ============================================
        info_frame = ttk.LabelFrame(self.review_tab, text="📋 Hướng Dẫn Review Claims", padding="10")
        info_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        info_text = (
            "🎯 MỤC ĐÍCH: Tự động di chuyển các file bị claim sang thư mục khác\n\n"
            
            "📝 CÁCH SỬ DỤNG:\n"
            "  1. Chọn thư mục nguồn (chứa file gốc)\n"
            "  2. Chọn thư mục đích (nơi sẽ di chuyển file bị claim)\n"
            "  3. Chọn file cần di chuyển từ danh sách\n"
            "  4. Nhấn '👁️ Preview' để xem chi tiết\n"
            "  5. Nhấn '➡️ Di Chuyển' để thực hiện\n\n"
            
            "⚠️  LƯU Ý:\n"
            "  • Danh sách TỰ ĐỘNG cập nhật khi chuyển sang tab này\n"  # ✅ THÊM DÒNG NÀY
            "  • Chỉ hiển thị file BỊ CLAIM từ kết quả kiểm tra\n"
            "  • File sẽ được DI CHUYỂN (không phải copy)\n"
            "  • Tự động phân loại theo số lần bị claim\n"
            "  • Kiểm tra kỹ trước khi di chuyển (không thể undo!)"
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
        self.review_tree = ttk.Treeview(
            review_frame, 
            columns=columns, 
            show='headings', 
            height=15,
            selectmode='extended'
        )

        # ============================================
        # ✅ COLUMN HEADINGS với Sort Support
        # ============================================
        self.review_tree.heading('claim_id', text='ID', command=lambda: self._sort_review_column('claim_id', False))
        self.review_tree.heading('song', text='Tên Bài Hát', command=lambda: self._sort_review_column('song', False))
        self.review_tree.heading('time_range', text='Khoảng Thời Gian', command=lambda: self._sort_review_column('time_range', False))
        self.review_tree.heading('confidence', text='Confidence', command=lambda: self._sort_review_column('confidence', False))
        self.review_tree.heading('reason', text='Lý Do', command=lambda: self._sort_review_column('reason', False))
        self.review_tree.heading('matched_files', text='Files Có Thể Match', command=lambda: self._sort_review_column('matched_files', False))

        # ============================================
        # ✅ COLUMN WIDTHS - Tối ưu hóa
        # ============================================
        # Set initial widths (minimum)
        self.review_tree.column('claim_id', width=50, minwidth=50, stretch=False)  # Fixed width
        self.review_tree.column('song', width=250, minwidth=150, stretch=True)     # Auto-expand
        self.review_tree.column('time_range', width=180, minwidth=150, stretch=False)  # Fixed
        self.review_tree.column('confidence', width=100, minwidth=80, stretch=False)  # Fixed
        self.review_tree.column('reason', width=300, minwidth=200, stretch=True)   # Auto-expand
        self.review_tree.column('matched_files', width=250, minwidth=150, stretch=True)  # Auto-expand
        
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

        # ============================================
        # LABEL HƯỚNG DẪN
        # ============================================
        help_label = ttk.Label(
            action_frame,
            text="💡 Mẹo: Ctrl+Click để chọn nhiều claims | Shift+Click để chọn dãy claims liên tiếp",
            font=('Arial', 9),
            foreground='#0066CC'
        )
        help_label.pack(pady=(0, 10))

        # ============================================
        # HÀNG 1: CÁC THAO TÁC CHÍNH
        # ============================================
        main_actions_frame = ttk.Frame(action_frame)
        main_actions_frame.pack(fill=tk.X, pady=3)

        ttk.Button(
            main_actions_frame, 
            text="✅ Chấp Nhận", 
            command=self.smart_accept_claim,
            width=18
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            main_actions_frame, 
            text="❌ Loại Bỏ", 
            command=self.smart_reject_claim,
            width=18
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            main_actions_frame, 
            text="✏️ Chỉnh Sửa", 
            command=self.edit_claim,
            width=18
        ).pack(side=tk.LEFT, padx=5)

        # ============================================
        # HÀNG 2: THAO TÁC HÀNG LOẠT + ĐIỀU HƯỚNG
        # ============================================
        batch_actions_frame = ttk.Frame(action_frame)
        batch_actions_frame.pack(fill=tk.X, pady=3)

        ttk.Button(
            batch_actions_frame, 
            text="✅ Chấp Nhận Tất Cả", 
            command=self.accept_all_claims,
            width=28
        ).pack(side=tk.LEFT, padx=5)

        ttk.Label(
            action_frame,
            text="💡 Sau khi review xong, nhấn 'Chấp Nhận Tất Cả' để tự động hiển thị kết quả",
            font=('Arial', 8),
            foreground='blue'
        ).pack(pady=(10, 0))
        
        # ============================================
        # ✅ OPTIONAL: KEYBOARD SHORTCUTS
        # ============================================
        def on_key_press(event):
            """Xử lý phím tắt trong Review Tab"""
            # Enter hoặc Space = Chấp nhận
            if event.keysym in ('Return', 'space'):
                self.smart_accept_claim()
            # Delete = Loại bỏ
            elif event.keysym == 'Delete':
                self.smart_reject_claim()
            # F2 = Chỉnh sửa
            elif event.keysym == 'F2':
                self.edit_claim()
            # Ctrl+A = Chọn tất cả
            elif event.keysym == 'a' and (event.state & 0x4):  # Ctrl pressed
                for item in self.review_tree.get_children():
                    self.review_tree.selection_add(item)

        # Bind phím tắt cho treeview
        self.review_tree.bind('<Key>', on_key_press)

        # Thêm label hướng dẫn phím tắt
        shortcut_label = ttk.Label(
            review_frame,
            text="⌨️ Phím tắt: Enter/Space=Chấp nhận | Delete=Loại bỏ | F2=Chỉnh sửa | Ctrl+A=Chọn tất cả",
            font=('Arial', 8),
            foreground='gray'
        )
        shortcut_label.grid(row=3, column=0, pady=(5, 0), sticky=tk.W)
        
        # ============================================
        # PHẦN 5: GRID CONFIGURATION
        # ============================================
        self.review_tab.columnconfigure(0, weight=1)
        self.review_tab.rowconfigure(1, weight=1)
        review_frame.columnconfigure(0, weight=1)
        review_frame.rowconfigure(0, weight=1)

    def setup_move_tab(self):
        # ============================================
        # PHẦN 1: INFO FRAME - Hướng dẫn
        # ============================================
        info_frame = ttk.LabelFrame(self.move_tab, text="📁 Hướng Dẫn Di Chuyển File", padding="10")
        info_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        info_text = (
            "🎯 MỤC ĐÍCH: Tự động di chuyển các file bị claim sang thư mục khác\n\n"
            
            "📝 CÁCH SỬ DỤNG:\n"
            "  1. Chọn thư mục nguồn (chứa file gốc)\n"
            "  2. Chọn thư mục đích (nơi sẽ di chuyển file bị claim)\n"
            "  3. Chọn file cần di chuyển từ danh sách\n"
            "  4. Nhấn 'Di Chuyển' để thực hiện\n\n"
            
            "⚠️ LƯU Ý:\n"
            "  • Chỉ hiển thị file BỊ CLAIM từ kết quả kiểm tra\n"
            "  • File sẽ được DI CHUYỂN (không phải copy)\n"
            "  • Kiểm tra kỹ trước khi di chuyển (không thể undo!)"
        )
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT, font=('Arial', 9))
        info_label.pack(anchor=tk.W)
        
        # ============================================
        # PHẦN 2: FOLDER SELECTION
        # ============================================
        folder_frame = ttk.LabelFrame(self.move_tab, text="📂 Chọn Thư Mục", padding="10")
        folder_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # Source folder
        ttk.Label(folder_frame, text="📁 Thư mục nguồn:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.source_folder = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.source_folder, width=60).grid(row=0, column=1, padx=5)
        ttk.Button(folder_frame, text="Chọn", command=self.select_source_folder).grid(row=0, column=2)
        
        # Destination folder
        ttk.Label(folder_frame, text="📁 Thư mục đích:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.dest_folder = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.dest_folder, width=60).grid(row=1, column=1, padx=5)
        ttk.Button(folder_frame, text="Chọn", command=self.select_dest_folder).grid(row=1, column=2)
        
        # ============================================
        # PHẦN 3: FILE LIST với Checkboxes
        # ============================================
        list_frame = ttk.LabelFrame(self.move_tab, text="📋 Danh Sách File Bị Claim", padding="10")
        list_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Treeview với checkbox column
        columns = ('select', 'filename', 'claim_count', 'song_names', 'status')
        self.move_tree = ttk.Treeview(list_frame, columns=columns, show='tree headings', height=15)
        
        # Column headings
        self.move_tree.heading('#0', text='✓')
        self.move_tree.heading('select', text='')
        self.move_tree.heading('filename', text='Tên File')
        self.move_tree.heading('claim_count', text='Số Claim')
        self.move_tree.heading('song_names', text='Bài Hát')
        self.move_tree.heading('status', text='Trạng Thái')
        
        # Column widths
        self.move_tree.column('#0', width=30)
        self.move_tree.column('select', width=0)
        self.move_tree.column('filename', width=300)
        self.move_tree.column('claim_count', width=80)
        self.move_tree.column('song_names', width=300)
        self.move_tree.column('status', width=150)
        
        # Grid treeview
        self.move_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.move_tree.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.move_tree.configure(yscrollcommand=scrollbar.set)
        
        # Bind click để toggle checkbox
        self.move_tree.bind('<Button-1>', self.toggle_file_selection)
        
        # ============================================
        # PHẦN 4: ACTION BUTTONS
        # ============================================
        action_frame = ttk.Frame(list_frame)
        action_frame.grid(row=1, column=0, pady=10)
        
        # Hàng 1: Selection Controls
        row1_frame = ttk.Frame(action_frame)
        row1_frame.pack(pady=5)
        
        ttk.Button(
            row1_frame, 
            text="✅ Chọn Tất Cả", 
            command=self.select_all_files, 
            width=18
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            row1_frame, 
            text="⬜ Bỏ Chọn Tất Cả", 
            command=self.deselect_all_files, 
            width=18
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            row1_frame, 
            text="🎯 Chọn Theo Claim", 
            command=self.select_by_claim_count, 
            width=18
        ).pack(side=tk.LEFT, padx=5)
        
        # Hàng 2: Actions
        row2_frame = ttk.Frame(action_frame)
        row2_frame.pack(pady=5)
        
        ttk.Button(
            row2_frame, 
            text="👁️ Preview Di Chuyển", 
            command=self.preview_file_move, 
            width=28
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            row2_frame, 
            text="➡️ DI CHUYỂN", 
            command=self.move_selected_files, 
            width=28
        ).pack(side=tk.LEFT, padx=15)
        
        # ✅ THÊM LABEL HƯỚNG DẪN
        ttk.Label(
            action_frame,
            text="💡 Danh sách tự động cập nhật khi chuyển sang tab này",
            font=('Arial', 8),
            foreground='blue'
        ).pack(pady=(5, 0))
        
        # ============================================
        # PHẦN 5: STATUS BAR
        # ============================================
        status_frame = ttk.Frame(list_frame)
        status_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(10, 5))
        
        self.move_status_label = ttk.Label(
            status_frame, 
            text="", 
            font=('Arial', 10, 'bold'),
            foreground='blue'
        )
        self.move_status_label.pack(side=tk.LEFT, padx=5)
        
        # ============================================
        # PHẦN 6: GRID CONFIGURATION
        # ============================================
        self.move_tab.columnconfigure(0, weight=1)
        self.move_tab.rowconfigure(2, weight=1)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

    def _on_tab_changed(self, event):
        """
        ✅ V3.9.2: Tự động refresh khi chuyển tab
        
        Gọi khi user click vào tab khác
        - Move Tab → Auto refresh file list
        - Cleanup Tab → Auto refresh status
        """
        selected_tab = event.widget.select()
        tab_text = event.widget.tab(selected_tab, "text")
        
        print(f"\n📑 Tab changed to: {tab_text}")
        
        # ============================================
        # AUTO-REFRESH MOVE TAB
        # ============================================
        if "Di Chuyển" in tab_text or "📁" in tab_text:
            print("   → Auto-refreshing Move Tab...")
            
            # Chỉ refresh nếu đã có results
            if self.results and self.source_folder.get():
                try:
                    self.refresh_file_list()
                    print("   ✅ Move Tab refreshed")
                except Exception as e:
                    print(f"   ⚠️  Refresh failed: {e}")
        
        # ============================================
        # AUTO-REFRESH CLEANUP TAB
        # ============================================
        elif "Quản Lý" in tab_text or "🗑️" in tab_text:
            print("   → Auto-refreshing Cleanup Tab...")
            
            try:
                self.refresh_cleanup_status()
                print("   ✅ Cleanup Tab refreshed")
            except Exception as e:
                print(f"   ⚠️  Refresh failed: {e}")

    def setup_cleanup_tab(self):
        # ============================================
        # PHẦN 1: INFO FRAME - Hướng dẫn
        # ============================================
        info_frame = ttk.LabelFrame(self.cleanup_tab, text="🗑️ Quản Lý Thư Mục & Cache", padding="10")
        info_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        info_text = (
            "🎯 MỤC ĐÍCH: Quản lý và dọn dẹp các thư mục tạm, cache, lịch sử\n\n"
            
            "📂 CÁC THƯ MỤC:\n"
            "  • claim_history/: Lưu lịch sử text claims đã paste\n"
            "  • debug_images/: (Nếu có) Lưu ảnh debug OCR\n"
            "  • Các thư mục cache khác của app\n\n"
            
            "🔧 CHỨC NĂNG:\n"
            "  • Xem dung lượng từng thư mục\n"
            "  • Xóa file cũ (giữ lại N file mới nhất)\n"
            "  • Xóa toàn bộ thư mục\n"
            "  • Mở thư mục trong File Explorer\n\n"
            
            "⚠️ LƯU Ý:\n"
            "  • Xóa thư mục KHÔNG ảnh hưởng app\n"
            "  • Thư mục sẽ tự động tạo lại khi cần\n"
            "  • Không thể hoàn tác sau khi xóa!"
        )
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT, font=('Arial', 9))
        info_label.pack(anchor=tk.W)
        
        # ============================================
        # PHẦN 2: FOLDER STATUS
        # ============================================
        status_frame = ttk.LabelFrame(self.cleanup_tab, text="📊 Trạng Thái Thư Mục", padding="10")
        status_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Treeview hiển thị folders
        columns = ('folder', 'exists', 'file_count', 'size', 'oldest', 'newest')
        self.cleanup_tree = ttk.Treeview(status_frame, columns=columns, show='headings', height=8)
        
        # Column headings
        self.cleanup_tree.heading('folder', text='📁 Thư Mục')
        self.cleanup_tree.heading('exists', text='Tồn Tại')
        self.cleanup_tree.heading('file_count', text='Số File')
        self.cleanup_tree.heading('size', text='Dung Lượng')
        self.cleanup_tree.heading('oldest', text='File Cũ Nhất')
        self.cleanup_tree.heading('newest', text='File Mới Nhất')
        
        # Column widths
        self.cleanup_tree.column('folder', width=200)
        self.cleanup_tree.column('exists', width=80)
        self.cleanup_tree.column('file_count', width=80)
        self.cleanup_tree.column('size', width=120)
        self.cleanup_tree.column('oldest', width=150)
        self.cleanup_tree.column('newest', width=150)
        
        # Grid treeview
        self.cleanup_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.cleanup_tree.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.cleanup_tree.configure(yscrollcommand=scrollbar.set)
        
        # ============================================
        # PHẦN 3: ACTION BUTTONS
        # ============================================
        action_frame = ttk.Frame(status_frame)
        action_frame.grid(row=1, column=0, pady=10)
        
        ttk.Button(action_frame, text="🔄 Làm Mới", 
                  command=self.refresh_cleanup_status, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="📂 Mở Thư Mục", 
                  command=self.open_selected_folder, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="🗑️ Xóa File Cũ", 
                  command=self.cleanup_old_files, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="❌ Xóa Toàn Bộ", 
                  command=self.delete_selected_folder, width=18).pack(side=tk.LEFT, padx=5)
        
        # ============================================
        # PHẦN 4: DETAIL PANEL
        # ============================================
        detail_frame = ttk.LabelFrame(self.cleanup_tab, text="📋 Chi Tiết", padding="10")
        detail_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.cleanup_detail = scrolledtext.ScrolledText(
            detail_frame, 
            width=120, 
            height=12,
            font=('Consolas', 9),
            wrap=tk.WORD
        )
        self.cleanup_detail.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Bind selection
        self.cleanup_tree.bind('<<TreeviewSelect>>', self.show_folder_detail)
        
        # ============================================
        # PHẦN 5: GRID CONFIGURATION
        # ============================================
        self.cleanup_tab.columnconfigure(0, weight=1)
        self.cleanup_tab.rowconfigure(1, weight=1)
        self.cleanup_tab.rowconfigure(2, weight=1)
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        
        # Load initial data
        self.refresh_cleanup_status()

    # ============================================
    # 🆕 HÀM MỚI 5: SETUP SETTINGS TAB
    # ============================================
    def setup_settings_tab(self):
        """
        ✅ Tạo tab Settings để điều chỉnh matching parameters
        """
        # ============================================
        # PHẦN 1: INFO FRAME - Hướng dẫn
        # ============================================
        info_frame = ttk.LabelFrame(self.settings_tab, text="⚙️ Hướng Dẫn Settings", padding="10")
        info_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        info_text = (
            "🎯 MỤC ĐÍCH: Điều chỉnh thuật toán matching để phù hợp với từng trường hợp\n\n"
            
            "📊 CÁC THÔNG SỐ:\n"
            "  • Name Similarity: % tương đồng tên bài (0-100%)\n"
            "  • Overlap: % thời gian trùng khớp (0-100%)\n"
            "  • Absolute Duration: Thời lượng tối thiểu (giây)\n"
            "  • Frequency Rescue: Số lần claim để 'cứu' name thấp\n\n"
            
            "💡 PROFILES:\n"
            "  • Cẩn thận: Ít false positive, strict matching\n"
            "  • Chuẩn: Balanced (recommended)\n"
            "  • Thoải mái: Catch nhiều claim, có thể có false positive\n\n"
            
            "⚠️ LƯU Ý:\n"
            "  • Settings tự động lưu vào file 'matching_settings.json'\n"
            "  • Thay đổi sẽ áp dụng cho lần kiểm tra TIẾP THEO\n"
            "  • Nhấn 'Reset' để về mặc định"
        )
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT, font=('Arial', 9))
        info_label.pack(anchor=tk.W)
        
        # ============================================
        # PHẦN 2: PROFILES FRAME
        # ============================================
        profiles_frame = ttk.LabelFrame(self.settings_tab, text="🎨 Profiles Nhanh", padding="10")
        profiles_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        profiles = {
            'Cẩn thận': {
                'name_similarity_auto_accept': 85,
                'name_similarity_need_review': 50,
                'overlap_percent_auto_accept': 60,
                'overlap_percent_need_review': 40,
                'frequency_rescue_threshold': 5,
                'min_absolute_duration': 15,
            },
            'Chuẩn': {
                'name_similarity_auto_accept': 80,
                'name_similarity_need_review': 40,
                'overlap_percent_auto_accept': 50,
                'overlap_percent_need_review': 30,
                'frequency_rescue_threshold': 3,
                'min_absolute_duration': 10,
            },
            'Thoải mái': {
                'name_similarity_auto_accept': 70,
                'name_similarity_need_review': 30,
                'overlap_percent_auto_accept': 40,
                'overlap_percent_need_review': 20,
                'frequency_rescue_threshold': 2,
                'min_absolute_duration': 7,
            }
        }
        
        def apply_profile(profile_name):
            profile = profiles[profile_name]
            for key, value in profile.items():
                if key in self.settings_vars:
                    self.settings_vars[key].set(value)
            
            messagebox.showinfo("✅ Áp dụng Profile", f"Đã áp dụng profile '{profile_name}'!")
        
        btn_frame = ttk.Frame(profiles_frame)
        btn_frame.pack()
        
        ttk.Button(btn_frame, text="🛡️ Cẩn thận", 
                  command=lambda: apply_profile('Cẩn thận'), width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="⚖️ Chuẩn (Recommended)", 
                  command=lambda: apply_profile('Chuẩn'), width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🌊 Thoải mái", 
                  command=lambda: apply_profile('Thoải mái'), width=15).pack(side=tk.LEFT, padx=5)
        
        # ============================================
        # PHẦN 3: SETTINGS SLIDERS
        # ============================================
        settings_frame = ttk.LabelFrame(self.settings_tab, text="⚙️ Điều Chỉnh Chi Tiết", padding="10")
        settings_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Tạo canvas + scrollbar
        canvas = tk.Canvas(settings_frame, height=400)
        scrollbar = ttk.Scrollbar(settings_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Dict để lưu trữ các biến
        self.settings_vars = {}
        
        # Helper function để tạo slider
        def create_slider(parent, row, label, key, min_val, max_val, default_val, suffix="%"):
            ttk.Label(parent, text=label, font=('Arial', 9, 'bold')).grid(
                row=row, column=0, sticky=tk.W, pady=(10, 0)
            )
            
            var = tk.IntVar(value=self.matching_settings.get(key, default_val))
            self.settings_vars[key] = var
            
            slider = tk.Scale(
                parent, 
                from_=min_val, 
                to=max_val, 
                orient=tk.HORIZONTAL,
                variable=var,
                length=400,
                tickinterval=(max_val - min_val) // 5
            )
            slider.grid(row=row+1, column=0, sticky=(tk.W, tk.E), padx=10)
            
            value_label = ttk.Label(parent, text=f"{var.get()}{suffix}")
            value_label.grid(row=row+1, column=1, sticky=tk.W, padx=5)
            
            def update_label(*args):
                value_label.config(text=f"{var.get()}{suffix}")
            
            var.trace('w', update_label)
            
            return var
        
        # === TÊN BÀI ===
        ttk.Separator(scrollable_frame, orient='horizontal').grid(
            row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5
        )
        ttk.Label(scrollable_frame, text="📝 TÊN BÀI (NAME SIMILARITY)", 
                 font=('Arial', 10, 'bold')).grid(row=1, column=0, sticky=tk.W)
        
        create_slider(scrollable_frame, 2, "✅ Auto-Accept (%):", 
                     'name_similarity_auto_accept', 0, 100, 80)
        create_slider(scrollable_frame, 4, "⚠️ Need Review (%):", 
                     'name_similarity_need_review', 0, 100, 40)
        create_slider(scrollable_frame, 6, "❌ Reject (<%):", 
                     'name_similarity_reject', 0, 100, 0)
        
        # === THỜI GIAN ===
        ttk.Separator(scrollable_frame, orient='horizontal').grid(
            row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15
        )
        ttk.Label(scrollable_frame, text="⏱️ THỜI GIAN (OVERLAP)", 
                 font=('Arial', 10, 'bold')).grid(row=9, column=0, sticky=tk.W)
        
        create_slider(scrollable_frame, 10, "✅ Auto-Accept (%):", 
                     'overlap_percent_auto_accept', 0, 100, 50)
        create_slider(scrollable_frame, 12, "⚠️ Need Review (%):", 
                     'overlap_percent_need_review', 0, 100, 30)
        create_slider(scrollable_frame, 14, "❌ Reject (<%):", 
                     'overlap_percent_reject', 0, 100, 20)
        
        create_slider(scrollable_frame, 16, "⏱️ Tối thiểu (giây):", 
                     'min_absolute_duration', 0, 60, 10, suffix="s")
        
        # === TẦN SUẤT (FREQUENCY RESCUE) ===
        ttk.Separator(scrollable_frame, orient='horizontal').grid(
            row=18, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15
        )
        ttk.Label(scrollable_frame, text="🔢 TẦN SUẤT CLAIM (FREQUENCY RESCUE) 🆕", 
                 font=('Arial', 10, 'bold')).grid(row=19, column=0, sticky=tk.W)
        
        create_slider(scrollable_frame, 20, "🔄 Số lần tối thiểu:", 
                     'frequency_rescue_threshold', 1, 10, 3, suffix=" lần")
        create_slider(scrollable_frame, 22, "⏱️ Overlap tối thiểu (%):", 
                     'frequency_rescue_min_overlap', 0, 100, 20)
        
        # === OCR CONFIDENCE ===
        ttk.Separator(scrollable_frame, orient='horizontal').grid(
            row=24, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15
        )
        ttk.Label(scrollable_frame, text="📊 CONFIDENCE (OCR)", 
                 font=('Arial', 10, 'bold')).grid(row=25, column=0, sticky=tk.W)
        
        create_slider(scrollable_frame, 26, "⚠️ Tối thiểu (%):", 
                     'ocr_confidence_threshold', 0, 100, 50)
        
        # ============================================
        # PHẦN 4: ACTION BUTTONS
        # ============================================
        action_frame = ttk.Frame(self.settings_tab)
        action_frame.grid(row=3, column=0, columnspan=2, pady=15)
        
        def save_settings():
            """Lưu settings vào file JSON"""
            try:
                settings = {key: var.get() for key, var in self.settings_vars.items()}
                self.matching_settings = settings
                
                # Gọi hàm save từ ClaimCheckerApp
                if self.save_matching_settings(settings):
                    messagebox.showinfo("✅ Đã lưu", 
                        "Settings đã được lưu!\n\n"
                        "Sẽ áp dụng cho lần kiểm tra tiếp theo.")
                else:
                    messagebox.showerror("❌ Lỗi", "Không thể lưu settings!")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể lưu:\n{str(e)}")
        
        def reset_settings():
            """Reset về mặc định"""
            confirm = messagebox.askyesno(
                "⚠️ Xác nhận Reset",
                "Reset tất cả settings về mặc định?"
            )
            
            if confirm:
                if self.reset_matching_settings():
                    messagebox.showinfo("✅ Reset", "Đã reset về mặc định!")
        
        ttk.Button(action_frame, text="💾 Lưu Cài Đặt", 
                  command=save_settings, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="🔄 Mặc Định", 
                  command=reset_settings, width=18).pack(side=tk.LEFT, padx=5)
        
        # ============================================
        # PHẦN 5: GRID CONFIGURATION
        # ============================================
        self.settings_tab.columnconfigure(0, weight=1)
        self.settings_tab.rowconfigure(2, weight=1)

    def refresh_cleanup_status(self):
        """
        ✅ v3.8: Làm mới trạng thái các thư mục
        """
        # Clear existing items
        for item in self.cleanup_tree.get_children():
            self.cleanup_tree.delete(item)
        
        # Danh sách thư mục cần quản lý
        folders_to_check = [
            'claim_history',
            'debug_images',
            'temp',
            'cache',
            'logs'
        ]
        
        from datetime import datetime
        
        for folder_name in folders_to_check:
            folder_path = Path.cwd() / folder_name
            
            if folder_path.exists() and folder_path.is_dir():
                # Đếm file
                files = list(folder_path.glob('*.*'))
                file_count = len(files)
                
                # Tính dung lượng
                total_size = sum(f.stat().st_size for f in files if f.is_file())
                size_str = self.format_size(total_size)
                
                # Tìm file cũ nhất và mới nhất
                if files:
                    files_with_time = [(f, f.stat().st_mtime) for f in files if f.is_file()]
                    if files_with_time:
                        oldest_file = min(files_with_time, key=lambda x: x[1])
                        newest_file = max(files_with_time, key=lambda x: x[1])
                        
                        oldest_str = datetime.fromtimestamp(oldest_file[1]).strftime('%Y-%m-%d %H:%M')
                        newest_str = datetime.fromtimestamp(newest_file[1]).strftime('%Y-%m-%d %H:%M')
                    else:
                        oldest_str = "N/A"
                        newest_str = "N/A"
                else:
                    oldest_str = "N/A"
                    newest_str = "N/A"
                
                # Insert vào treeview
                self.cleanup_tree.insert('', 'end', values=(
                    folder_name,
                    '✅ Có',
                    file_count,
                    size_str,
                    oldest_str,
                    newest_str
                ), tags=('exists',))
            else:
                # Thư mục không tồn tại
                self.cleanup_tree.insert('', 'end', values=(
                    folder_name,
                    '❌ Không',
                    '0',
                    '0 B',
                    'N/A',
                    'N/A'
                ), tags=('not_exists',))
        
        # Configure tags
        self.cleanup_tree.tag_configure('exists', foreground='black')
        self.cleanup_tree.tag_configure('not_exists', foreground='gray')

    def format_size(self, size_bytes):
        """Format size in bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def show_folder_detail(self, event):
        """
        ✅ v3.8: Hiển thị chi tiết thư mục được chọn
        """
        selection = self.cleanup_tree.selection()
        if not selection:
            return
        
        item = self.cleanup_tree.item(selection[0])
        folder_name = item['values'][0]
        folder_path = Path.cwd() / folder_name
        
        # Clear detail
        self.cleanup_detail.config(state='normal')
        self.cleanup_detail.delete('1.0', tk.END)
        
        if not folder_path.exists():
            self.cleanup_detail.insert('1.0', f"❌ Thư mục '{folder_name}' không tồn tại")
            self.cleanup_detail.config(state='disabled')
            return
        
        # List files
        files = list(folder_path.glob('*.*'))
        
        output = f"📁 THƯ MỤC: {folder_name}\n"
        output += f"📍 Đường dẫn: {folder_path}\n"
        output += f"📊 Số file: {len(files)}\n"
        output += "=" * 80 + "\n\n"
        
        if files:
            output += "📋 DANH SÁCH FILE (20 file mới nhất):\n"
            output += "-" * 80 + "\n"
            
            # Sort by modified time (newest first)
            files_sorted = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)
            
            from datetime import datetime
            for idx, file in enumerate(files_sorted[:20], 1):
                size = file.stat().st_size
                mtime = datetime.fromtimestamp(file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                output += f"{idx}. {file.name}\n"
                output += f"   📏 Size: {self.format_size(size)}\n"
                output += f"   🕒 Modified: {mtime}\n\n"
            
            if len(files) > 20:
                output += f"... và {len(files) - 20} file khác\n"
        else:
            output += "⚠️ Thư mục trống\n"
        
        self.cleanup_detail.insert('1.0', output)
        self.cleanup_detail.config(state='disabled')

    def open_selected_folder(self):
        """
        ✅ v3.8: Mở thư mục được chọn trong File Explorer
        """
        selection = self.cleanup_tree.selection()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn thư mục!")
            return
        
        item = self.cleanup_tree.item(selection[0])
        folder_name = item['values'][0]
        folder_path = Path.cwd() / folder_name
        
        if not folder_path.exists():
            messagebox.showerror("Lỗi", f"Thư mục '{folder_name}' không tồn tại!")
            return
        
        # Mở folder
        import subprocess
        import platform
        
        system = platform.system()
        try:
            if system == "Windows":
                os.startfile(folder_path)
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", folder_path])
            else:  # Linux
                subprocess.Popen(["xdg-open", folder_path])
            
            messagebox.showinfo("Thành công", f"✅ Đã mở thư mục:\n{folder_path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở thư mục:\n{str(e)}")

    def cleanup_old_files(self):
        """
        ✅ v3.8: Xóa file cũ, giữ lại N file mới nhất
        """
        selection = self.cleanup_tree.selection()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn thư mục!")
            return
        
        item = self.cleanup_tree.item(selection[0])
        folder_name = item['values'][0]
        folder_path = Path.cwd() / folder_name
        
        if not folder_path.exists():
            messagebox.showerror("Lỗi", f"Thư mục '{folder_name}' không tồn tại!")
            return
        
        # Dialog hỏi giữ lại bao nhiêu file
        keep_dialog = tk.Toplevel(self.root)
        keep_dialog.title("🗑️ Xóa File Cũ")
        keep_dialog.geometry("400x200")
        keep_dialog.transient(self.root)
        keep_dialog.grab_set()
        
        ttk.Label(
            keep_dialog, 
            text="🗑️ XÓA FILE CŨ", 
            font=('Arial', 12, 'bold')
        ).pack(pady=10)
        
        ttk.Label(
            keep_dialog, 
            text=f"Thư mục: {folder_name}\nSố file hiện tại: {item['values'][2]}"
        ).pack(pady=5)
        
        frame = ttk.Frame(keep_dialog)
        frame.pack(pady=10)
        
        ttk.Label(frame, text="Giữ lại (file mới nhất):").pack(side=tk.LEFT, padx=5)
        keep_count = tk.IntVar(value=10)
        ttk.Spinbox(frame, from_=0, to=100, textvariable=keep_count, width=10).pack(side=tk.LEFT)
        
        def execute_cleanup():
            try:
                keep = keep_count.get()
                files = list(folder_path.glob('*.*'))
                
                if len(files) <= keep:
                    messagebox.showinfo("Thông báo", "Không có file nào cần xóa!")
                    keep_dialog.destroy()
                    return
                
                # Sort by modified time (newest first)
                files_sorted = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)
                
                # Files to delete
                files_to_delete = files_sorted[keep:]
                
                confirm = messagebox.askyesno(
                    "⚠️ Xác nhận xóa",
                    f"Sẽ xóa {len(files_to_delete)} file cũ\n"
                    f"Giữ lại {keep} file mới nhất\n\n"
                    f"Chắc chắn?"
                )
                
                if not confirm:
                    return
                
                # Delete files
                deleted = 0
                for file in files_to_delete:
                    try:
                        file.unlink()
                        deleted += 1
                    except Exception as e:
                        print(f"❌ Error deleting {file.name}: {e}")
                
                keep_dialog.destroy()
                self.refresh_cleanup_status()
                
                messagebox.showinfo(
                    "✅ Hoàn thành",
                    f"Đã xóa {deleted}/{len(files_to_delete)} file\n"
                    f"Còn lại {keep} file mới nhất"
                )
                
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể xóa file:\n{str(e)}")
        
        btn_frame = ttk.Frame(keep_dialog)
        btn_frame.pack(pady=15)
        
        ttk.Button(btn_frame, text="🗑️ Xóa", command=execute_cleanup).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="❌ Hủy", command=keep_dialog.destroy).pack(side=tk.LEFT, padx=5)

    def delete_selected_folder(self):
        """
        ✅ v3.8: Xóa toàn bộ thư mục
        """
        selection = self.cleanup_tree.selection()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn thư mục!")
            return
        
        item = self.cleanup_tree.item(selection[0])
        folder_name = item['values'][0]
        folder_path = Path.cwd() / folder_name
        
        if not folder_path.exists():
            messagebox.showinfo("Thông báo", f"Thư mục '{folder_name}' không tồn tại!")
            return
        
        # Confirm
        file_count = item['values'][2]
        size = item['values'][3]
        
        confirm = messagebox.askyesno(
            "⚠️ XÁC NHẬN XÓA TOÀN BỘ",
            f"Sẽ xóa TOÀN BỘ thư mục:\n\n"
            f"📁 {folder_name}\n"
            f"📊 {file_count} file\n"
            f"📏 {size}\n\n"
            f"⚠️ KHÔNG THỂ HOÀN TÁC!\n\n"
            f"Chắc chắn xóa?"
        )
        
        if not confirm:
            return
        
        try:
            import shutil
            shutil.rmtree(folder_path)
            
            self.refresh_cleanup_status()
            
            messagebox.showinfo(
                "✅ Đã xóa",
                f"Đã xóa thư mục:\n{folder_name}\n\n"
                f"Thư mục sẽ tự động tạo lại khi cần"
            )
            
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể xóa thư mục:\n{str(e)}")

    def select_source_folder(self):
        """Chọn thư mục nguồn"""
        folder = filedialog.askdirectory(title="Chọn thư mục chứa file gốc")
        if folder:
            self.source_folder.set(folder)
            self.refresh_file_list()

    def select_dest_folder(self):
        """Chọn thư mục đích"""
        folder = filedialog.askdirectory(title="Chọn thư mục đích")
        if folder:
            self.dest_folder.set(folder)

    def refresh_file_list(self):
        """
        ✅ Quét ĐỆ QUY thư mục nguồn
        """
        # Clear existing items
        for item in self.move_tree.get_children():
            self.move_tree.delete(item)
        
        if not self.results:
            self.move_status_label.config(
                text="⚠️ Chưa có kết quả kiểm tra! Vui lòng kiểm tra claim trước.",
                foreground='orange'
            )
            return
        
        if not self.source_folder.get():
            self.move_status_label.config(
                text="⚠️ Vui lòng chọn thư mục nguồn",
                foreground='orange'
            )
            return
        
        # Group files by filename
        claimed_files = {}
        for item in self.results:
            filename = item['track']['filename']
            song = item['claim']['song']
            
            if filename not in claimed_files:
                claimed_files[filename] = {
                    'count': 0,
                    'songs': set()
                }
            
            claimed_files[filename]['count'] += 1
            claimed_files[filename]['songs'].add(song[:40])
        
        # ✅ QUÉT ĐỆ QUY thư mục nguồn
        source_path = Path(self.source_folder.get())
        found_count = 0
        missing_count = 0
        file_locations = {}  # Lưu đường dẫn đầy đủ của file
        
        # Quét tất cả file trong source_path và subdirs
        for file_path in source_path.rglob('*'):
            if file_path.is_file():
                file_locations[file_path.name] = file_path
        
        # Populate treeview
        for filename, info in sorted(claimed_files.items()):
            if filename in file_locations:
                file_path = file_locations[filename]
                # Hiển thị relative path để user biết file ở đâu
                relative_path = file_path.relative_to(source_path)
                display_name = str(relative_path)
                
                status = f"✅ Tìm thấy ({relative_path.parent})"
                found_count += 1
                tag = 'found'
            else:
                display_name = filename
                status = "❌ Không tìm thấy"
                missing_count += 1
                tag = 'missing'
            
            songs_str = ", ".join(list(info['songs'])[:3])
            if len(info['songs']) > 3:
                songs_str += f" (+{len(info['songs'])-3})"
            
            # Insert với checkbox (☐)
            self.move_tree.insert('', 'end', text='☐', values=(
                'unchecked',
                display_name,
                info['count'],  # ✅ Số lần bị claim
                songs_str,
                status
            ), tags=(tag,))
        
        # Configure tags
        self.move_tree.tag_configure('found', foreground='black')
        self.move_tree.tag_configure('missing', foreground='gray')
        
        # Update status
        total = len(claimed_files)
        self.move_status_label.config(
            text=f"📊 Tổng: {total} file | ✅ Tìm thấy: {found_count} | ❌ Thiếu: {missing_count}",
            foreground='blue'
        )

    def toggle_file_selection(self, event):
        """Toggle checkbox khi click vào item"""
        region = self.move_tree.identify('region', event.x, event.y)
        if region != 'tree':
            return
        
        item = self.move_tree.identify_row(event.y)
        if not item:
            return
        
        # Toggle selection
        current_text = self.move_tree.item(item, 'text')
        current_values = self.move_tree.item(item, 'values')
        
        if current_text == '☐':
            self.move_tree.item(item, text='☑', values=('checked',) + current_values[1:])
        else:
            self.move_tree.item(item, text='☐', values=('unchecked',) + current_values[1:])

    def select_all_files(self):
        """Chọn tất cả file"""
        for item in self.move_tree.get_children():
            current_values = self.move_tree.item(item, 'values')
            # ✅ FIX: Index 4 là status (0=select, 1=filename, 2=count, 3=songs, 4=status)
            if current_values[4] == "✅ Tìm thấy":
                self.move_tree.item(item, text='☑', values=('checked',) + current_values[1:])

    def deselect_all_files(self):
        """Bỏ chọn tất cả file"""
        for item in self.move_tree.get_children():
            current_values = self.move_tree.item(item, 'values')
            self.move_tree.item(item, text='☐', values=('unchecked',) + current_values[1:])

    def select_by_claim_count(self):
        """
        ✅ FINAL: Chọn file theo số lần claim
        CẢI THIỆN: Cho phép chọn nhiều giá trị cùng lúc
        """
        # Dialog chọn số claim
        dialog = tk.Toplevel(self.root)
        dialog.title("🎯 Chọn Theo Số Claim")
        dialog.geometry("400x350")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(
            dialog, 
            text="🎯 CHỌN FILE THEO SỐ CLAIM", 
            font=('Arial', 12, 'bold')
        ).pack(pady=10)
        
        # Lấy danh sách claim counts có sẵn
        claim_counts_available = {}
        for item in self.move_tree.get_children():
            values = self.move_tree.item(item, 'values')
            if values[4].startswith("✅"):  # Chỉ file tìm thấy
                count = int(values[2])
                if count not in claim_counts_available:
                    claim_counts_available[count] = 0
                claim_counts_available[count] += 1
        
        if not claim_counts_available:
            ttk.Label(dialog, text="⚠️ Không có file nào được tìm thấy").pack(pady=10)
            ttk.Button(dialog, text="Đóng", command=dialog.destroy).pack(pady=10)
            return
        
        # ============================================
        # OPTION 1: Chọn 1 giá trị
        # ============================================
        ttk.Label(dialog, text="Chọn file có số claim:").pack(pady=5)
        
        count_var = tk.IntVar(value=min(claim_counts_available.keys()))
        
        # Tạo combobox với thông tin chi tiết
        combo_values = [
            f"{count} claim(s) - {claim_counts_available[count]} file(s)"
            for count in sorted(claim_counts_available.keys())
        ]
        
        combo = ttk.Combobox(dialog, values=combo_values, width=25, state='readonly')
        combo.current(0)
        combo.pack(pady=5)
        
        # ============================================
        # OPTION 2: Chọn range
        # ============================================
        ttk.Separator(dialog, orient='horizontal').pack(fill=tk.X, pady=15)
        ttk.Label(dialog, text="Hoặc chọn range:").pack(pady=5)
        
        range_frame = ttk.Frame(dialog)
        range_frame.pack(pady=5)
        
        ttk.Label(range_frame, text="Từ:").pack(side=tk.LEFT, padx=5)
        from_var = tk.IntVar(value=min(claim_counts_available.keys()))
        from_spin = ttk.Spinbox(
            range_frame, 
            from_=min(claim_counts_available.keys()), 
            to=max(claim_counts_available.keys()),
            textvariable=from_var,
            width=5
        )
        from_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(range_frame, text="Đến:").pack(side=tk.LEFT, padx=5)
        to_var = tk.IntVar(value=max(claim_counts_available.keys()))
        to_spin = ttk.Spinbox(
            range_frame,
            from_=min(claim_counts_available.keys()),
            to=max(claim_counts_available.keys()),
            textvariable=to_var,
            width=5
        )
        to_spin.pack(side=tk.LEFT, padx=5)
        
        # ============================================
        # Buttons
        # ============================================
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        
        def select_single():
            """Chọn 1 giá trị"""
            selected_text = combo.get()
            target_count = int(selected_text.split()[0])
            
            selected = 0
            for item in self.move_tree.get_children():
                values = self.move_tree.item(item, 'values')
                claim_count = int(values[2])
                
                if claim_count == target_count and values[4].startswith("✅"):
                    self.move_tree.item(item, text='☑', values=('checked',) + values[1:])
                    selected += 1
            
            dialog.destroy()
            messagebox.showinfo("Thành công", f"✅ Đã chọn {selected} file có {target_count} claim(s)")
        
        def select_range():
            """Chọn theo range"""
            from_count = from_var.get()
            to_count = to_var.get()
            
            if from_count > to_count:
                messagebox.showerror("Lỗi", "Giá trị 'Từ' phải nhỏ hơn 'Đến'!")
                return
            
            selected = 0
            for item in self.move_tree.get_children():
                values = self.move_tree.item(item, 'values')
                claim_count = int(values[2])
                
                if from_count <= claim_count <= to_count and values[4].startswith("✅"):
                    self.move_tree.item(item, text='☑', values=('checked',) + values[1:])
                    selected += 1
            
            dialog.destroy()
            messagebox.showinfo("Thành công", f"✅ Đã chọn {selected} file có {from_count}-{to_count} claim(s)")
        
        ttk.Button(btn_frame, text="🎯 Chọn Đơn", command=select_single, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📊 Chọn Range", command=select_range, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="❌ Hủy", command=dialog.destroy, width=15).pack(side=tk.LEFT, padx=5)

    def preview_file_move(self):
        """
        ✅ V3.9.2: PREVIEW chi tiết trước khi di chuyển
        
        Hiển thị:
        - Danh sách file sẽ di chuyển
        - Folder đích
        - Phân loại theo claim count
        """
        # Kiểm tra
        if not self.source_folder.get():
            messagebox.showerror("Lỗi", "Vui lòng chọn thư mục nguồn!")
            return
        
        if not self.dest_folder.get():
            messagebox.showerror("Lỗi", "Vui lòng chọn thư mục đích!")
            return
        
        # Thu thập file đã chọn
        selected_files = {}  # {filename: claim_count}
        
        for item in self.move_tree.get_children():
            if self.move_tree.item(item, 'text') == '☑':
                values = self.move_tree.item(item, 'values')
                display_name = values[1]
                claim_count = int(values[2])
                
                filename = Path(display_name).name
                selected_files[filename] = claim_count
        
        if not selected_files:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất 1 file!")
            return
        
        # Phân nhóm theo claim count
        files_by_count = {}
        for filename, count in selected_files.items():
            if count not in files_by_count:
                files_by_count[count] = []
            files_by_count[count].append(filename)
        
        # Tạo preview text
        preview = "="*70 + "\n"
        preview += "👁️  PREVIEW DI CHUYỂN FILE\n"
        preview += "="*70 + "\n\n"
        
        preview += f"📂 TỪ: {self.source_folder.get()}\n"
        preview += f"📂 ĐẾN: {self.dest_folder.get()}\n\n"
        
        preview += f"📊 TỔNG: {len(selected_files)} file(s)\n\n"
        preview += "="*70 + "\n"
        preview += "📋 PHÂN LOẠI THEO SỐ LẦN CLAIM:\n"
        preview += "="*70 + "\n\n"
        
        for count in sorted(files_by_count.keys()):
            folder_name = f"{count}_claim" if count == 1 else f"{count}_claims"
            file_list = files_by_count[count]
            
            preview += f"📁 {folder_name}/  →  {len(file_list)} file(s)\n"
            preview += "-"*70 + "\n"
            
            for idx, filename in enumerate(sorted(file_list)[:5], 1):
                preview += f"   {idx}. {filename[:55]}\n"
            
            if len(file_list) > 5:
                preview += f"   ... và {len(file_list) - 5} file khác\n"
            
            preview += "\n"
        
        preview += "="*70 + "\n"
        preview += "⚠️  LƯU Ý:\n"
        preview += "  • File sẽ được DI CHUYỂN (không phải copy)\n"
        preview += "  • Thư mục con tự động tạo nếu chưa có\n"
        preview += "  • Nếu file trùng tên sẽ hỏi ghi đè\n"
        preview += "="*70 + "\n"
        
        # Hiển thị trong dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("👁️  Preview Di Chuyển")
        dialog.geometry("800x600")
        dialog.transient(self.root)
        
        # Text widget
        text_widget = scrolledtext.ScrolledText(
            dialog, 
            width=90, 
            height=30,
            font=('Consolas', 9),
            wrap=tk.WORD
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert('1.0', preview)
        text_widget.config(state='disabled')
        
        # Button frame
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        ttk.Button(
            btn_frame, 
            text="✅ OK - Tiếp Tục Di Chuyển",
            command=lambda: [dialog.destroy(), self.move_selected_files()]
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame, 
            text="❌ Hủy",
            command=dialog.destroy
        ).pack(side=tk.LEFT, padx=5)

    def move_selected_files(self):
        """
        ✅ FINAL: Di chuyển file VÀ phân loại theo số lần claim
        - TỰ ĐỘNG TẠO: 1_claim/, 2_claims/, 3_claims/...
        - QUÉT ĐỆ QUY: Tìm file trong tất cả subfolder của source
        - PREVIEW CHI TIẾT: Hiển thị rõ ràng file sẽ vào folder nào
        """
        # ============================================
        # BƯỚC 1: VALIDATION
        # ============================================
        if not self.source_folder.get():
            messagebox.showerror("Lỗi", "Vui lòng chọn thư mục nguồn!")
            return
        
        if not self.dest_folder.get():
            messagebox.showerror("Lỗi", "Vui lòng chọn thư mục đích!")
            return
        
        # ============================================
        # BƯỚC 2: THU THẬP FILE ĐÃ CHỌN + CLAIM COUNT
        # ============================================
        selected_files = {}  # {filename: {'display_name': str, 'claim_count': int}}
        
        for item in self.move_tree.get_children():
            if self.move_tree.item(item, 'text') == '☑':
                values = self.move_tree.item(item, 'values')
                display_name = values[1]  # Có thể là "subfolder/file.wav"
                claim_count = int(values[2])
                
                # Extract filename (bỏ đường dẫn relative nếu có)
                filename = Path(display_name).name
                selected_files[filename] = {
                    'display_name': display_name,
                    'claim_count': claim_count
                }
        
        if not selected_files:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất 1 file!")
            return
        
        # ============================================
        # BƯỚC 3: PHÂN NHÓM THEO CLAIM COUNT
        # ============================================
        files_by_claim_count = {}
        for filename, info in selected_files.items():
            count = info['claim_count']
            if count not in files_by_claim_count:
                files_by_claim_count[count] = []
            files_by_claim_count[count].append(filename)
        
        # ============================================
        # BƯỚC 4: XÂY DỰNG PREVIEW CHI TIẾT
        # ============================================
        preview_text = "📊 DỰ KIẾN PHÂN LOẠI:\n"
        preview_text += "=" * 70 + "\n\n"
        
        for count in sorted(files_by_claim_count.keys()):
            file_list = files_by_claim_count[count]
            folder_name = f"{count}_claim" if count == 1 else f"{count}_claims"
            
            # Header cho mỗi nhóm
            preview_text += f"📁 {folder_name}/  →  {len(file_list)} file(s)\n"
            preview_text += "-" * 70 + "\n"
            
            # Hiển thị tối đa 5 file đầu làm ví dụ
            for idx, filename in enumerate(file_list[:5], 1):
                preview_text += f"   {idx}. {filename[:55]}\n"
                if len(filename) > 55:
                    preview_text += f"      ...{filename[-20:]}\n"
            
            # Nếu còn nhiều file hơn
            if len(file_list) > 5:
                preview_text += f"   ... và {len(file_list) - 5} file khác\n"
            
            preview_text += "\n"
        
        preview_text += "=" * 70 + "\n"
        preview_text += f"📊 TỔNG: {len(selected_files)} file → {len(files_by_claim_count)} folder(s)\n"
        
        # ============================================
        # BƯỚC 5: CONFIRM DIALOG VỚI PREVIEW
        # ============================================
        confirm = messagebox.askyesno(
            "⚠️ XÁC NHẬN DI CHUYỂN",
            f"Sẽ di chuyển {len(selected_files)} file(s):\n\n"
            f"📂 TỪ: {self.source_folder.get()}\n"
            f"📂 ĐẾN: {self.dest_folder.get()}\n\n"
            f"{preview_text}\n"
            f"✅ Thư mục con sẽ TỰ ĐỘNG được tạo!\n"
            f"✅ File sẽ được phân loại theo số lần bị claim\n\n"
            f"⚠️ CHÚ Ý:\n"
            f"  • File sẽ BỊ DI CHUYỂN (không phải copy)\n"
            f"  • KHÔNG THỂ HOÀN TÁC!\n"
            f"  • Nếu file trùng tên sẽ hỏi ghi đè\n\n"
            f"Chắc chắn tiếp tục?"
        )
        
        if not confirm:
            return
        
        # ============================================
        # BƯỚC 6: CHUẨN BỊ DI CHUYỂN
        # ============================================
        import shutil
        source_path = Path(self.source_folder.get())
        dest_path = Path(self.dest_folder.get())
        
        # Quét đệ quy để tìm file trong source (bao gồm cả subfolder)
        print(f"\n🔍 Đang quét thư mục: {source_path}")
        file_locations = {}
        for file_path in source_path.rglob('*'):
            if file_path.is_file():
                file_locations[file_path.name] = file_path
        
        print(f"✅ Tìm thấy {len(file_locations)} file(s) trong source")
        
        success_count = 0
        failed_files = []
        moved_by_folder = {}  # Track số file đã move vào mỗi folder
        skipped_count = 0
        
        # ============================================
        # BƯỚC 7: DI CHUYỂN THEO TỪNG NHÓM CLAIM COUNT
        # ============================================
        for claim_count in sorted(files_by_claim_count.keys()):
            filenames = files_by_claim_count[claim_count]
            
            # ============================================
            # Tạo thư mục con
            # ============================================
            subfolder_name = f"{claim_count}_claim" if claim_count == 1 else f"{claim_count}_claims"
            subfolder_path = dest_path / subfolder_name
            
            try:
                subfolder_path.mkdir(parents=True, exist_ok=True)
                print(f"\n📁 Created/verified folder: {subfolder_path}")
                moved_by_folder[subfolder_name] = 0
            except Exception as e:
                error_msg = f"Không thể tạo thư mục:\n{subfolder_path}\n\nLỗi: {str(e)}"
                messagebox.showerror("Lỗi Tạo Thư Mục", error_msg)
                failed_files.append(f"[FOLDER ERROR] {subfolder_name}: {str(e)}")
                continue
            
            # ============================================
            # Di chuyển từng file vào folder này
            # ============================================
            for filename in filenames:
                try:
                    # Tìm file trong source (quét đệ quy)
                    if filename not in file_locations:
                        failed_files.append(f"{filename}: Không tìm thấy trong source")
                        print(f"❌ Not found: {filename}")
                        continue
                    
                    src = file_locations[filename]
                    dst = subfolder_path / filename
                    
                    # Check if destination exists
                    if dst.exists():
                        response = messagebox.askyesnocancel(
                            "⚠️ File Đã Tồn Tại",
                            f"File đã tồn tại:\n"
                            f"📄 {dst.name}\n\n"
                            f"Trong folder:\n"
                            f"📁 {subfolder_name}/\n\n"
                            f"Đường dẫn đầy đủ:\n"
                            f"{dst}\n\n"
                            f"Chọn hành động:\n"
                            f"  • YES: Ghi đè (xóa file cũ)\n"
                            f"  • NO: Bỏ qua file này\n"
                            f"  • CANCEL: Dừng toàn bộ quá trình"
                        )
                        
                        if response is None:  # Cancel - dừng toàn bộ
                            messagebox.showinfo(
                                "Đã Dừng",
                                f"⚠️ Đã dừng quá trình di chuyển!\n\n"
                                f"📊 Thống kê:\n"
                                f"  ✅ Đã di chuyển: {success_count} file(s)\n"
                                f"  ⏭️ Bỏ qua: {skipped_count} file(s)\n"
                                f"  ❌ Lỗi: {len(failed_files)} file(s)\n"
                            )
                            self.refresh_file_list()
                            return
                        
                        elif not response:  # No - Skip file này
                            skipped_count += 1
                            print(f"⏭️ Skipped (exists): {filename}")
                            continue
                        
                        # Yes - Sẽ ghi đè (shutil.move tự động ghi đè)
                    
                    # ============================================
                    # MOVE FILE
                    # ============================================
                    print(f"📦 Moving: {src} → {dst}")
                    shutil.move(str(src), str(dst))
                    success_count += 1
                    moved_by_folder[subfolder_name] += 1
                    
                    print(f"✅ Success: {filename} → {subfolder_name}/")
                    
                    # ============================================
                    # Update treeview status
                    # ============================================
                    for item in self.move_tree.get_children():
                        item_values = self.move_tree.item(item, 'values')
                        item_filename = Path(item_values[1]).name
                        
                        if item_filename == filename:
                            self.move_tree.item(item, values=(
                                item_values[0],
                                item_values[1],
                                item_values[2],
                                item_values[3],
                                f"✅ → {subfolder_name}/"
                            ))
                            # Bỏ checkbox
                            self.move_tree.item(item, text='☐')
                            break
                    
                except PermissionError as e:
                    error_msg = f"{filename}: Không có quyền truy cập - {str(e)}"
                    failed_files.append(error_msg)
                    print(f"❌ Permission Error: {error_msg}")
                    
                except Exception as e:
                    error_msg = f"{filename}: {str(e)}"
                    failed_files.append(error_msg)
                    print(f"❌ Error: {error_msg}")
        
        # ============================================
        # BƯỚC 8: BÁO CÁO KẾT QUẢ CHI TIẾT
        # ============================================
        report = "=" * 70 + "\n"
        report += "✅ HOÀN THÀNH DI CHUYỂN FILE\n"
        report += "=" * 70 + "\n\n"
        
        report += f"📊 TỔNG QUAN:\n"
        report += f"  • Đã chọn: {len(selected_files)} file(s)\n"
        report += f"  • ✅ Di chuyển thành công: {success_count} file(s)\n"
        
        if skipped_count > 0:
            report += f"  • ⏭️ Đã bỏ qua: {skipped_count} file(s)\n"
        
        if failed_files:
            report += f"  • ❌ Thất bại: {len(failed_files)} file(s)\n"
        
        report += f"\n{'=' * 70}\n"
        report += f"📁 PHÂN LOẠI THEO FOLDER:\n"
        report += f"{'=' * 70}\n\n"
        
        for folder_name in sorted(moved_by_folder.keys(), key=lambda x: int(x.split('_')[0])):
            count = moved_by_folder[folder_name]
            report += f"  📁 {folder_name}/: {count} file(s)\n"
        
        # Hiển thị lỗi nếu có
        if failed_files:
            report += f"\n{'=' * 70}\n"
            report += f"❌ CHI TIẾT LỖI ({len(failed_files)} file):\n"
            report += f"{'=' * 70}\n\n"
            
            # Hiển thị tối đa 10 lỗi đầu
            for idx, error in enumerate(failed_files[:10], 1):
                report += f"{idx}. {error}\n"
            
            if len(failed_files) > 10:
                report += f"\n... và {len(failed_files) - 10} lỗi khác\n"
        
        report += f"\n{'=' * 70}\n"
        
        # ============================================
        # Hiển thị kết quả
        # ============================================
        messagebox.showinfo("✅ Hoàn Thành", report)
        
        # Log to console
        print("\n" + report)
        
        # ============================================
        # BƯỚC 9: REFRESH DANH SÁCH
        # ============================================
        self.refresh_file_list()

    def setup_review_context_menu(self):
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
                self.update_main_tab_status()
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể tải file!\n\n{str(e)}")
    
    def load_images(self):
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
            self.update_main_tab_status()
    
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
        ✅ FIX: Chuẩn hóa cấu trúc - LUÔN lưu dạng wrapper
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
            matched_track = None  # ✅ THÊM: Track tìm được
            
            # 1. Confidence check
            if claim['confidence'] < 50:
                is_ambiguous = True
                ambiguous_reasons.append(f"Low confidence: {claim['confidence']:.1f}%")
            
            # 2. Duration check
            duration = claim['end'] - claim['start']
            if duration < 10:
                is_ambiguous = True
                ambiguous_reasons.append(f"Duration too short: {duration}s")
            elif duration > 3600:
                is_ambiguous = True
                ambiguous_reasons.append(f"Duration too long: {duration}s")
            
            # 3. Tracklist matching - ✅ LƯU TRACK TÌM ĐƯỢC
            has_match = False
            for track in self.tracklist:
                if self.check_claim_overlap(
                    track['start'], track['end'],
                    claim['start'], claim['end']
                ):
                    has_match = True
                    matched_track = track  # ✅ LƯU track
                    break
            
            if not has_match:
                is_ambiguous = True
                ambiguous_reasons.append("No matching file in tracklist")
            
            # ✅ FIX: Phân loại - LƯU DẠNG WRAPPER NHẤT QUÁN
            if is_ambiguous:
                claim['ambiguous_reason'] = '; '.join(ambiguous_reasons)
                
                # ✅ LƯU WRAPPER
                self.ambiguous_claims.append({
                    'claim': claim,
                    'track': matched_track,  # Có thể None
                    'match_info': {
                        'reasons': ambiguous_reasons,
                        'name_similarity': 0,
                        'overlap_percent': 0,
                        'is_substring': False,
                        'is_time_contained': False
                    }
                })
                print(f"⚠️ AMBIGUOUS [{claim.get('source_type', '?').upper()}]: {claim['song'][:30]} - {'; '.join(ambiguous_reasons)}")
            else:
                # ✅ LƯU WRAPPER
                self.auto_accepted_claims.append({
                    'claim': claim,
                    'track': matched_track,
                    'match_info': {
                        'reasons': ['Auto-accepted'],
                        'name_similarity': 100,
                        'overlap_percent': 100,
                        'is_substring': True,
                        'is_time_contained': True
                    }
                })
                print(f"✅ AUTO-ACCEPTED [{claim.get('source_type', '?').upper()}]: {claim['song'][:30]}")
            
            valid_claims.append(claim)
        
        self.claims = valid_claims
        
        print(f"\n📊 SUMMARY:")
        print(f"✅ Auto-accepted: {len(self.auto_accepted_claims)} claims")
        print(f"⚠️ Need review: {len(self.ambiguous_claims)} claims")
        
        self.update_review_tab()
 
    def update_review_tab(self):
        """
        ✅ FIX: Xử lý đúng wrapper structure
        """
        # ============================================
        # BƯỚC 1: Clear existing items
        # ============================================
        for item in self.review_tree.get_children():
            self.review_tree.delete(item)
        
        # ============================================
        # BƯỚC 2: Populate treeview với ambiguous claims
        # ============================================
        for idx, wrapper in enumerate(self.ambiguous_claims, 1):
            # ✅ FIX: Lấy claim từ wrapper
            claim = wrapper['claim']
            track = wrapper.get('track')
            match_info = wrapper.get('match_info', {})
            
            time_range = f"{self.claim_parser.format_time_clean(claim['start'])} – {self.claim_parser.format_time_clean(claim['end'])}"
            confidence = f"{claim['confidence']:.1f}%"
            
            # Lấy reasons
            reasons = match_info.get('reasons', [])
            reason = '; '.join(reasons) if reasons else claim.get('ambiguous_reason', 'Unknown')
            
            # Tìm potential matches trong tracklist
            matched_files_str = "Không tìm thấy"
            if track:
                matched_files_str = track['filename'][:40]
            else:
                potential_matches = []
                for t in self.tracklist:
                    if abs(t['start'] - claim['start']) < 300 or abs(t['end'] - claim['end']) < 300:
                        potential_matches.append(t['filename'])
                
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
            # ✅ THÊM DÒNG NÀY - Auto-resize columns
            # ============================================
            if hasattr(self, '_auto_resize_review_columns'):
                self._auto_resize_review_columns()
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

    def update_review_tab_v2(self):
        """
        ✅ CẬP NHẬT REVIEW TAB - Hiển thị match info chi tiết
        Version 2: Bao gồm thông tin name similarity, overlap, substring
        """
        # ============================================
        # BƯỚC 1: Clear existing items
        # ============================================
        for item in self.review_tree.get_children():
            self.review_tree.delete(item)
        
        # ============================================
        # BƯỚC 2: Populate treeview với ambiguous claims
        # ============================================
        for idx, item in enumerate(self.ambiguous_claims, 1):
            claim = item['claim']
            track = item.get('track')
            match_info = item.get('match_info', {})
            
            # Format time range
            time_range = (f"{self.claim_parser.format_time_clean(claim['start'])} — "
                         f"{self.claim_parser.format_time_clean(claim['end'])}")
            
            # Format match detail
            if match_info:
                name_sim = match_info.get('name_similarity', 0)
                overlap = match_info.get('overlap_percent', 0)
                is_substring = match_info.get('is_substring', False)
                
                if is_substring:
                    match_detail = f"✅ Substring | Name: {name_sim:.1f}% | Overlap: {overlap:.1f}%"
                else:
                    match_detail = f"Name: {name_sim:.1f}% | Overlap: {overlap:.1f}%"
            else:
                match_detail = "N/A"
            
            # Format reasons
            reasons = match_info.get('reasons', [])
            reasons_str = ' | '.join(reasons) if reasons else "Cần xác nhận"
            
            # Get matched filename
            matched_file = track['filename'][:50] if track else "Không tìm thấy"
            
            # Insert vào treeview
            self.review_tree.insert('', 'end', values=(
                idx,
                claim['song'][:40],
                time_range,
                match_detail,
                reasons_str,
                matched_file
            ))
            # ============================================
            # ✅ THÊM DÒNG NÀY - Auto-resize columns
            # ============================================
            if hasattr(self, '_auto_resize_review_columns'):
                self._auto_resize_review_columns()
        # ============================================
        # BƯỚC 3: Update tab title
        # ============================================
        remaining = len(self.ambiguous_claims)
        self.notebook.tab(1, text=f"Review Claims ({remaining})")
        
        # ============================================
        # BƯỚC 4: Update status bar
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
                    text=f"⚠️  Cần xử lý {remaining} claims",
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

    def _sort_review_column(self, col, reverse):
        """
        ✅ Sort treeview theo column
        
        Args:
            col: Column name
            reverse: Sort direction (True = descending)
        """
        try:
            # Lấy data từ treeview
            data = [(self.review_tree.set(child, col), child) for child in self.review_tree.get_children('')]
            
            # Sort
            # Xử lý số cho claim_id và confidence
            if col in ('claim_id', 'confidence'):
                try:
                    data.sort(key=lambda x: float(x[0].replace('%', '').replace('ID', '').strip()), reverse=reverse)
                except:
                    data.sort(reverse=reverse)
            else:
                data.sort(reverse=reverse)
            
            # Reorder items
            for index, (val, child) in enumerate(data):
                self.review_tree.move(child, '', index)
            
            # Reverse sort next time
            self.review_tree.heading(col, command=lambda: self._sort_review_column(col, not reverse))
            
        except Exception as e:
            print(f"⚠️  Sort error: {e}")

    def _auto_resize_review_columns(self):
        """
        ✅ Tự động resize columns dựa vào nội dung thực tế
        
        Gọi sau khi populate data vào treeview
        """
        try:
            # Font để tính width
            import tkinter.font as tkfont
            font = tkfont.Font(family="TkDefaultFont", size=9)
            
            # Iterate qua từng column (trừ ID - fixed width)
            for col in ('song', 'time_range', 'reason', 'matched_files'):
                # Lấy max width của header
                heading_width = font.measure(self.review_tree.heading(col, 'text'))
                
                # Lấy max width của data
                max_width = heading_width
                
                for item in self.review_tree.get_children():
                    item_text = self.review_tree.set(item, col)
                    text_width = font.measure(item_text)
                    
                    if text_width > max_width:
                        max_width = text_width
                
                # Set width với padding
                new_width = min(max_width + 20, 500)  # Max 500px
                
                # Áp dụng (chỉ nếu lớn hơn minwidth)
                current_minwidth = self.review_tree.column(col, 'minwidth')
                if new_width > current_minwidth:
                    self.review_tree.column(col, width=new_width)
            
            print("✅ Auto-resized review columns")
            
        except Exception as e:
            print(f"⚠️  Auto-resize error: {e}")

    def display_results_v2(self, claimed_tracks):
        """
        ✅ HIỂN THỊ KẾT QUẢ - Version 3.9.1 FIXED
        
        Cải tiến:
        - Tính đúng % overlap cho từng file
        - Hiển thị threshold type
        - Cảnh báo claim ngắn/dài
        - Group theo song với segments
        - ✅ FIX: Luôn gán self.results để export được
        """
        self.results_text.delete(1.0, tk.END)
        
        # ============================================
        # HEADER
        # ============================================
        header = "="*140 + "\n"
        header += "YOUTUBE CLAIM CHECKER - KẾT QUẢ KIỂM TRA v3.9.1\n"
        header += "="*140 + "\n\n"
        self.results_text.insert(tk.END, header)
        
        # ============================================
        # ✅ DEDUPLICATE claims trước khi xử lý
        # ============================================
        unique_claims = self._deduplicate_claims_for_display(self.claims)
        
        # ============================================
        # SECTION 1: DANH SÁCH CLAIMS ĐÃ NHẬP
        # ============================================
        self.results_text.insert(tk.END, "="*140 + "\n")
        self.results_text.insert(tk.END, "📋 PHẦN 1: DANH SÁCH CLAIMS ĐÃ PHÁT HIỆN\n")
        self.results_text.insert(tk.END, "="*140 + "\n\n")
        
        # Thống kê tổng quan
        text_claims = [c for c in unique_claims if c.get('source_type') == 'text']
        ocr_claims = [c for c in unique_claims if c.get('source_type') == 'ocr']
        
        # Count accepted vs rejected
        accepted_claim_objs = [item['claim'] for item in self.auto_accepted_claims]
        accepted_count = len([c for c in unique_claims if c in accepted_claim_objs])
        rejected_count = len(self.rejected_claims) if hasattr(self, 'rejected_claims') else 0
        
        stats = f"📊 TỔNG QUAN:\n"
        stats += f"  • Tổng số claims: {len(unique_claims)}\n"
        stats += f"  • 📝 Từ text input: {len(text_claims)} claims\n"
        stats += f"  • 📷 Từ OCR (ảnh): {len(ocr_claims)} claims\n"
        stats += f"  • ✅ Auto-accepted: {accepted_count} claims\n"
        stats += f"  • ⚠️  Need review: {len(self.ambiguous_claims)} claims\n"
        
        if rejected_count > 0:
            stats += f"  • ❌ Auto-rejected: {rejected_count} claims (không hiển thị)\n"
        
        stats += f"  • 🎵 Số bài hát unique: {len(set(c['song'] for c in unique_claims))}\n\n"
        
        self.results_text.insert(tk.END, stats)
        
        # Hiển thị claims theo bài hát (format đẹp)
        self.results_text.insert(tk.END, "📝 CHI TIẾT CLAIMS THEO BÀI HÁT:\n")
        self.results_text.insert(tk.END, "-"*140 + "\n\n")
        
        formatted_claims = self.claim_parser.format_claims_by_song(unique_claims, numbered=True)
        self.results_text.insert(tk.END, formatted_claims)
        self.results_text.insert(tk.END, "\n\n")
        
        # ============================================
        # SECTION 2: KẾT QUẢ SO SÁNH VỚI TRACKLIST
        # ============================================
        self.results_text.insert(tk.END, "="*140 + "\n")
        self.results_text.insert(tk.END, "🎯 PHẦN 2: KẾT QUẢ SO SÁNH VỚI TRACKLIST\n")
        self.results_text.insert(tk.END, "="*140 + "\n\n")
        
        # ============================================
        # ✅ KIỂM TRA: Có claimed_tracks không?
        # ============================================
        if not claimed_tracks:
            self.results_text.insert(tk.END, "⚠️  KHÔNG CÓ FILE NÀO BỊ CLAIM!\n\n")
            self.results_text.insert(tk.END, "Lý do có thể:\n")
            self.results_text.insert(tk.END, "  • Tất cả claims đã bị loại bỏ trong review\n")
            self.results_text.insert(tk.END, "  • Claims không khớp với tracklist\n")
            self.results_text.insert(tk.END, "  • Timestamps không nằm trong khoảng file\n\n")
            
            # ✅ GÁN self.results = [] để export không lỗi
            self.results = []
            return
        
        # ============================================
        # Deduplicate claimed_tracks
        # ============================================
        unique_results = self._deduplicate_results_for_export(claimed_tracks)
        
        # ✅ GÁN self.results NGAY TẠI ĐÂY
        self.results = unique_results
        
        # Group by song
        songs = {}
        for item in unique_results:
            song = item['claim']['song']
            if song not in songs:
                songs[song] = []
            songs[song].append(item)
        
        total_claims = 0
        claimed_filenames = {}
        
        for song_name, items in sorted(songs.items()):
            # ============================================
            # Check if this is a LONG CLAIM (multiple files)
            # ============================================
            if len(items) > 1:
                # Kiểm tra xem có phải cùng 1 claim dài không
                first_claim = items[0]['claim']
                is_same_claim = all(
                    item['claim']['start'] == first_claim['start'] and 
                    item['claim']['end'] == first_claim['end'] 
                    for item in items
                )
                
                if is_same_claim:
                    # ✅ LONG CLAIM - Hiển thị đặc biệt
                    claim_duration = first_claim['end'] - first_claim['start']
                    
                    self.results_text.insert(tk.END, f"\n{'='*140}\n")
                    self.results_text.insert(tk.END, f"BÀI HÁT: {song_name}\n")
                    self.results_text.insert(tk.END, f"⚠️  CLAIM DÀI: {self.claim_parser.format_time_clean(first_claim['start'])} → ")
                    self.results_text.insert(tk.END, f"{self.claim_parser.format_time_clean(first_claim['end'])} ")
                    self.results_text.insert(tk.END, f"(Duration: {self.claim_parser.format_time(claim_duration)})\n")
                    
                    # Cảnh báo claim ngắn
                    if claim_duration <= 60:
                        if claim_duration < 10:
                            self.results_text.insert(tk.END, f"⚠️  CLAIM RẤT NGẮN: Chỉ {claim_duration}s - Cần kiểm tra kỹ!\n")
                        else:
                            self.results_text.insert(tk.END, f"ℹ️  CLAIM NGẮN: {claim_duration}s\n")
                    
                    self.results_text.insert(tk.END, f"📊 CHỒNG LẤN {len(items)} FILE(S):\n")
                    self.results_text.insert(tk.END, f"{'='*140}\n\n")
                    
                    for idx, item in enumerate(items, 1):
                        track = item['track']
                        claim = item['claim']
                        match_info = item.get('match_info', {})
                        
                        # Count claimed files
                        if track['filename'] not in claimed_filenames:
                            claimed_filenames[track['filename']] = 0
                        claimed_filenames[track['filename']] += 1
                        
                        # Status icon
                        status = "✅ AUTO" if claim in accepted_claim_objs else "⚠️  REVIEW"
                        source_icon = "📝" if claim.get('source_type') == 'text' else "📷"
                        
                        # Tính overlap chính xác
                        overlap_start = max(track['start'], claim['start'])
                        overlap_end = min(track['end'], claim['end'])
                        overlap_duration = max(0, overlap_end - overlap_start)
                        
                        file_duration = max(1, track['end'] - track['start'])
                        file_overlap_percent = (overlap_duration / file_duration * 100) if file_duration > 0 else 0
                        
                        result = f"  Segment #{idx} {status} {source_icon}:\n"
                        result += f"    ⚠️  FILE: {track['filename']}\n"
                        result += f"    📍 File time: {self.claim_parser.format_time_clean(track['start'])} → {self.claim_parser.format_time_clean(track['end'])}\n"
                        result += f"    🎯 Overlap: {self.claim_parser.format_time_clean(overlap_start)} → {self.claim_parser.format_time_clean(overlap_end)}\n"
                        result += f"    📊 Overlap: {overlap_duration}s ({file_overlap_percent:.1f}% của file)\n"
                        
                        # Match info
                        if match_info:
                            name_sim = match_info.get('name_similarity', 0)
                            threshold = match_info.get('threshold_type', 'UNKNOWN')
                            result += f"    🎯 Match: Name {name_sim:.1f}% | Threshold: {threshold}\n"
                        
                        result += "\n"
                        
                        self.results_text.insert(tk.END, result)
                        total_claims += 1
                    
                    continue
            
            # ============================================
            # NORMAL CLAIMS (1 file per claim hoặc khác timestamps)
            # ============================================
            self.results_text.insert(tk.END, f"\n{'='*140}\n")
            self.results_text.insert(tk.END, f"BÀI HÁT: {song_name}\n")
            self.results_text.insert(tk.END, f"{'='*140}\n\n")
            
            for idx, item in enumerate(items, 1):
                track = item['track']
                claim = item['claim']
                match_info = item.get('match_info', {})
                
                if track['filename'] not in claimed_filenames:
                    claimed_filenames[track['filename']] = 0
                claimed_filenames[track['filename']] += 1
                
                status = "✅ AUTO" if claim in accepted_claim_objs else "⚠️  REVIEW"
                source_icon = "📝" if claim.get('source_type') == 'text' else "📷"
                
                # Tính overlap
                overlap_start = max(track['start'], claim['start'])
                overlap_end = min(track['end'], claim['end'])
                overlap_duration = max(0, overlap_end - overlap_start)
                
                file_duration = max(1, track['end'] - track['start'])
                file_overlap_percent = (overlap_duration / file_duration * 100) if file_duration > 0 else 0
                
                result = f"Claim #{idx} {status} {source_icon}:\n"
                result += f"  ⚠️  FILE BỊ CLAIM: {track['filename']}\n"
                result += f"  📍 Thời gian file: {self.claim_parser.format_time_clean(track['start'])} → {self.claim_parser.format_time_clean(track['end'])}\n"
                result += f"  🎯 Claim phát hiện: {self.claim_parser.format_time_clean(claim['start'])} → {self.claim_parser.format_time_clean(claim['end'])}\n"
                result += f"  📊 Overlap: {overlap_duration}s ({file_overlap_percent:.1f}% của file)\n"
                
                # Match info chi tiết
                if match_info:
                    name_sim = match_info.get('name_similarity', 0)
                    threshold = match_info.get('threshold_type', 'UNKNOWN')
                    reasons = match_info.get('reasons', [])
                    
                    result += f"  🎯 Match score: Name {name_sim:.1f}% | Threshold: {threshold}\n"
                    if reasons:
                        result += f"  ℹ️  Lý do: {' | '.join(reasons)}\n"
                
                result += f"  {source_icon} Nguồn: {claim['source']}\n\n"
                
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
        
        summary += f"╔══ THỐNG KÊ CLAIMS ══╗\n"
        summary += f"║ Tổng claims phát hiện: {len(unique_claims)}\n"
        summary += f"║   📝 Claims từ text: {len(text_claims)}\n"
        summary += f"║   📷 Claims từ ảnh (OCR): {len(ocr_claims)}\n"
        summary += f"║ Claims auto-accepted: {accepted_count}\n"
        summary += f"║ Claims cần review: {len(self.ambiguous_claims)}\n\n"
        
        summary += f"╔══ THỐNG KÊ TRACKLIST ══╗\n"
        summary += f"║ Tổng file trong tracklist: {len(unique_filenames_tracklist)}\n"
        summary += f"║ Tổng lần bị claim: {total_claims}\n"
        summary += f"║ File UNIQUE bị claim: {len(unique_claimed)}\n"
        summary += f"║ File KHÔNG bị claim: {len(not_claimed_filenames)}\n"
        summary += f"║ Tỷ lệ bị claim: {len(unique_claimed)}/{len(unique_filenames_tracklist)} "
        summary += f"({len(unique_claimed)/len(unique_filenames_tracklist)*100:.1f}%)\n"
        summary += f"{'='*140}\n\n"
        
        summary += f"{'='*140}\n"
        summary += f"⚠️  DANH SÁCH FILE BỊ CLAIM ({len(unique_claimed)} file)\n"
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
                summary += f"  ⚠️  {filename} ({count} lần)\n"
        
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
        
        # ✅ LOG: Xác nhận đã gán self.results
        print(f"\n✅ display_results_v2() completed:")
        print(f"   • self.results assigned: {len(self.results)} items")
        print(f"   • Unique claimed files: {len(unique_claimed)}")
        print(f"   • Total claim instances: {total_claims}\n")

    def parse_time(self, time_str):
        parts = time_str.split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    
    def check_claim_overlap(self, track_start, track_end, claim_start, claim_end):
        tolerance = 10
        
        # Tính khoảng overlap
        overlap_start = max(track_start - tolerance, claim_start)
        overlap_end = min(track_end + tolerance, claim_end)
        
        # Nếu có overlap
        if overlap_start < overlap_end:
            overlap_duration = overlap_end - overlap_start
            claim_duration = claim_end - claim_start
            
            # Match nếu overlap >= 50% claim duration
            # (Tránh match với file chỉ overlap vài giây)
            if overlap_duration >= claim_duration * 0.5:
                return True
        
        return False

    def find_best_match(self, claim, tracklist):
        """
        ✅ THUẬT TOÁN MỚI V3 - 3 CẤP ĐỘ MATCHING + RESCUE MECHANISMS
        
        CẤP 1: AUTO-ACCEPT - Tên có trong file + Thời gian nằm trong file
        CẤP 2: NEED REVIEW - Gần đúng nhưng cần xác nhận
        CẤP 3: REJECT - Sai rõ ràng
        
        🆕 RESCUE MECHANISMS:
        - Frequency Rescue: Claim nhiều lần → Xem lại dù name thấp
        - Absolute Duration: Đủ giây → Xem lại dù % overlap thấp
        
        Returns:
            {
                'track': track_dict,
                'match_level': 'AUTO_ACCEPT' | 'NEED_REVIEW' | 'REJECT',
                'overlap_percent': float,
                'name_similarity': float,
                'is_substring': bool,
                'is_time_contained': bool,
                'reasons': [list of reasons],
                'claim_frequency': int  # 🆕 Số lần claim
            }
            hoặc None nếu không có candidate nào
        """
        from difflib import SequenceMatcher
        
        # Load settings
        settings = self.matching_settings
        
        # Normalize tên claim
        claim_name_normalized = self.claim_parser._normalize_song_name_v2(claim['song'])
        
        if not claim_name_normalized:
            print(f"⚠️ Empty claim name after normalize: '{claim['song']}'")
            return None
        
        # ============================================
        # 🆕 BƯỚC 0: ĐẾM TẦN SUẤT CLAIM
        # ============================================
        claim_frequency = self._count_claim_frequency(claim['song'])
        print(f"📊 Claim frequency for '{claim['song'][:40]}': {claim_frequency} times")
        
        candidates = []
        
        for track in tracklist:
            # ============================================
            # BƯỚC 1: TÍNH OVERLAP thời gian
            # ============================================
            overlap_start = max(track['start'], claim['start'])
            overlap_end = min(track['end'], claim['end'])
            
            if overlap_start >= overlap_end:
                continue  # Không overlap → skip
            
            overlap_duration = overlap_end - overlap_start
            claim_duration = claim['end'] - claim['start']
            overlap_percent = (overlap_duration / claim_duration * 100) if claim_duration > 0 else 0
            
            # ============================================
            # BƯỚC 2: Normalize tên file
            # ============================================
            track_name_raw = track['filename']
            track_name_raw = re.sub(r'^\d+-\s*', '', track_name_raw)
            track_name_raw = re.sub(r'\.(wav|mp3|m4a|flac)$', '', track_name_raw, flags=re.IGNORECASE)
            track_name_raw = re.sub(r'\s*\(\d+\)\s*', '', track_name_raw)
            track_name_normalized = self.claim_parser._normalize_song_name_v2(track_name_raw)
            
            if not track_name_normalized:
                continue
            
            # ============================================
            # BƯỚC 3: TÍNH NAME SIMILARITY
            # ============================================
            name_similarity = SequenceMatcher(None, claim_name_normalized, track_name_normalized).ratio() * 100
            
            # ============================================
            # BƯỚC 4: CHECK SUBSTRING
            # ============================================
            is_substring = claim_name_normalized in track_name_normalized
            
            # ============================================
            # BƯỚC 5: CHECK TIME CONTAINMENT
            # ============================================
            is_time_contained = (
                claim['start'] >= track['start'] - 5 and 
                claim['end'] <= track['end'] + 5
            )
            
            candidates.append({
                'track': track,
                'overlap_percent': overlap_percent,
                'overlap_duration': overlap_duration,  # 🆕 Thêm absolute duration
                'name_similarity': name_similarity,
                'is_substring': is_substring,
                'is_time_contained': is_time_contained,
                'claim_name': claim_name_normalized,
                'track_name': track_name_normalized
            })
        
        if not candidates:
            return None
        
        # ============================================
        # BƯỚC 6: SORT - Ưu tiên overlap cao nhất
        # ============================================
        candidates.sort(key=lambda x: (x['overlap_percent'], x['name_similarity']), reverse=True)
        best = candidates[0]
        
        reasons = []
        
        # ============================================
        # BƯỚC 7: PHÂN LOẠI - 3 CẤP ĐỘ + RESCUE
        # ============================================
        
        # ============================================
        # CẤP 1: AUTO-ACCEPT ✅
        # ============================================
        if ((best['is_substring'] or best['name_similarity'] >= settings['name_similarity_auto_accept']) and 
            best['is_time_contained'] and 
            best['overlap_percent'] >= settings['overlap_percent_auto_accept']):
            
            if best['is_substring']:
                reasons.append(f"✅ Tên claim '{best['claim_name']}' có trong file")
            else:
                reasons.append(f"✅ Tên tương đồng cao: {best['name_similarity']:.1f}%")
            
            reasons.append(f"✅ Thời gian claim nằm trong khoảng file")
            reasons.append(f"✅ Overlap: {best['overlap_percent']:.1f}%")
            
            if claim_frequency > 1:
                reasons.append(f"📊 Claimed {claim_frequency} times")
            
            print(f"\n✅ AUTO-ACCEPT:")
            print(f"   Claim: '{claim['song'][:40]}'")
            print(f"   File:  '{best['track']['filename'][:50]}'")
            print(f"   Reasons: {' | '.join(reasons)}")
            
            return {
                'track': best['track'],
                'match_level': 'AUTO_ACCEPT',
                'overlap_percent': best['overlap_percent'],
                'overlap_duration': best['overlap_duration'],
                'name_similarity': best['name_similarity'],
                'is_substring': best['is_substring'],
                'is_time_contained': best['is_time_contained'],
                'reasons': reasons,
                'claim_frequency': claim_frequency
            }
        
        # ============================================
        # 🆕 RESCUE MECHANISM 1: FREQUENCY-BASED
        # ============================================
        if (claim_frequency >= settings['frequency_rescue_threshold'] and
            best['overlap_percent'] >= settings['frequency_rescue_min_overlap'] and
            best['name_similarity'] >= settings['name_similarity_need_review']):
            
            reasons.append(f"🔄 FREQUENCY RESCUE: Claimed {claim_frequency} times")
            reasons.append(f"⚠️ Name similarity low: {best['name_similarity']:.1f}%")
            reasons.append(f"✅ Overlap acceptable: {best['overlap_percent']:.1f}%")
            reasons.append(f"💡 Possible file name mismatch - Manual review needed")
            
            print(f"\n🔄 FREQUENCY RESCUE → NEED REVIEW:")
            print(f"   Claim: '{claim['song'][:40]}'")
            print(f"   File:  '{best['track']['filename'][:50]}'")
            print(f"   Frequency: {claim_frequency} times")
            print(f"   Reasons: {' | '.join(reasons)}")
            
            return {
                'track': best['track'],
                'match_level': 'NEED_REVIEW',
                'overlap_percent': best['overlap_percent'],
                'overlap_duration': best['overlap_duration'],
                'name_similarity': best['name_similarity'],
                'is_substring': best['is_substring'],
                'is_time_contained': best['is_time_contained'],
                'reasons': reasons,
                'claim_frequency': claim_frequency
            }
        
        # ============================================
        # 🆕 RESCUE MECHANISM 2: ABSOLUTE DURATION
        # ============================================
        if (best['overlap_duration'] >= settings['min_absolute_duration'] and
            best['name_similarity'] >= settings['name_similarity_need_review']):
            
            reasons.append(f"🔄 DURATION RESCUE: {best['overlap_duration']:.0f}s absolute overlap")
            reasons.append(f"⚠️ Low % overlap: {best['overlap_percent']:.1f}% (long file)")
            reasons.append(f"✅ Name similarity: {best['name_similarity']:.1f}%")
            reasons.append(f"💡 Short claim in long file - Manual review needed")
            
            if claim_frequency > 1:
                reasons.append(f"📊 Claimed {claim_frequency} times")
            
            print(f"\n🔄 DURATION RESCUE → NEED REVIEW:")
            print(f"   Claim: '{claim['song'][:40]}'")
            print(f"   File:  '{best['track']['filename'][:50]}'")
            print(f"   Duration: {best['overlap_duration']:.0f}s")
            print(f"   Reasons: {' | '.join(reasons)}")
            
            return {
                'track': best['track'],
                'match_level': 'NEED_REVIEW',
                'overlap_percent': best['overlap_percent'],
                'overlap_duration': best['overlap_duration'],
                'name_similarity': best['name_similarity'],
                'is_substring': best['is_substring'],
                'is_time_contained': best['is_time_contained'],
                'reasons': reasons,
                'claim_frequency': claim_frequency
            }
        
        # ============================================
        # CẤP 3: AUTO-REJECT ❌
        # ============================================
        reject_threshold_name = settings['name_similarity_reject']
        reject_threshold_overlap = settings.get('overlap_percent_reject', 20)  # Mặc định 20%
        
        if (best['name_similarity'] < reject_threshold_name or 
            (best['overlap_percent'] < reject_threshold_overlap and 
             best['overlap_duration'] < settings['min_absolute_duration'])):
            
            if best['name_similarity'] < reject_threshold_name:
                reasons.append(f"❌ Tên quá khác biệt: {best['name_similarity']:.1f}%")
                reasons.append(f"   Claim: '{best['claim_name']}'")
                reasons.append(f"   File:  '{best['track_name']}'")
            
            if best['overlap_percent'] < reject_threshold_overlap:
                reasons.append(f"❌ Overlap quá thấp: {best['overlap_percent']:.1f}% ({best['overlap_duration']:.0f}s)")
            
            if claim_frequency > 1:
                reasons.append(f"📊 BUT claimed {claim_frequency} times (still rejected)")
            
            print(f"\n❌ AUTO-REJECT:")
            print(f"   Claim: '{claim['song'][:40]}'")
            print(f"   File:  '{best['track']['filename'][:50]}'")
            print(f"   Reasons: {' | '.join(reasons)}")
            
            return {
                'track': best['track'],
                'match_level': 'REJECT',
                'overlap_percent': best['overlap_percent'],
                'overlap_duration': best['overlap_duration'],
                'name_similarity': best['name_similarity'],
                'is_substring': best['is_substring'],
                'is_time_contained': best['is_time_contained'],
                'reasons': reasons,
                'claim_frequency': claim_frequency
            }
        
        # ============================================
        # CẤP 2: NEED REVIEW ⚠️ (Fallback)
        # ============================================
        
        # Case 2A: Tên gần đúng + Thời gian khá
        if (best['name_similarity'] >= settings['name_similarity_need_review'] and 
            best['overlap_percent'] >= settings['overlap_percent_need_review']):
            reasons.append(f"⚠️ Tên gần đúng: {best['name_similarity']:.1f}%")
            reasons.append(f"⚠️ Overlap khá: {best['overlap_percent']:.1f}%")
            
            if not best['is_time_contained']:
                reasons.append(f"⚠️ Thời gian không nằm hoàn toàn trong file")
            
            if not best['is_substring']:
                reasons.append(f"⚠️ Tên không phải substring chính xác")
        
        # Case 2B: Tên hơi khác + Thời gian chuẩn
        elif (best['name_similarity'] >= settings['name_similarity_need_review'] and 
              best['overlap_percent'] >= settings['overlap_percent_auto_accept']):
            reasons.append(f"⚠️ Tên hơi khác: {best['name_similarity']:.1f}%")
            reasons.append(f"✅ Overlap cao: {best['overlap_percent']:.1f}%")
            
            if best['is_time_contained']:
                reasons.append(f"✅ Thời gian nằm trong file")
        
        # Case 2C: Fallback - không rõ ràng
        else:
            reasons.append(f"⚠️ Không chắc chắn")
            reasons.append(f"   Name: {best['name_similarity']:.1f}%")
            reasons.append(f"   Overlap: {best['overlap_percent']:.1f}%")
        
        if claim_frequency > 1:
            reasons.append(f"📊 Claimed {claim_frequency} times")
        
        print(f"\n⚠️ NEED REVIEW:")
        print(f"   Claim: '{claim['song'][:40]}'")
        print(f"   File:  '{best['track']['filename'][:50]}'")
        print(f"   Reasons: {' | '.join(reasons)}")
        
        return {
            'track': best['track'],
            'match_level': 'NEED_REVIEW',
            'overlap_percent': best['overlap_percent'],
            'overlap_duration': best['overlap_duration'],
            'name_similarity': best['name_similarity'],
            'is_substring': best['is_substring'],
            'is_time_contained': best['is_time_contained'],
            'reasons': reasons,
            'claim_frequency': claim_frequency
        }

    def find_all_matching_tracks(self, claim, tracklist):
        """
        🆕 TÌM TẤT CẢ FILES OVERLAP VỚI CLAIM - V2 IMPROVED
        
        Xử lý đặc biệt:
        - Claim dài (>60s): Standard threshold
        - Claim ngắn (10-60s): Flexible threshold
        - Claim rất ngắn (<10s): Relaxed threshold
        
        Trả về:
            List of {
                'track': track_dict,
                'overlap_start': int,
                'overlap_end': int,
                'overlap_duration': int,
                'overlap_percent': float (% so với file),
                'claim_segment_percent': float (% so với claim),
                'is_significant': bool (có đáng kể không?)
            }
        """
        matches = []
        claim_duration = claim['end'] - claim['start']
        
        # ============================================
        # BƯỚC 1: XÁC ĐỊNH THRESHOLD DỰA TRÊN CLAIM DURATION
        # ============================================
        if claim_duration > 60:
            # Claim dài: Standard threshold
            min_overlap_percent = 50  # 50% file
            min_overlap_seconds = 5   # Hoặc ít nhất 5 giây
            threshold_type = "STANDARD"
            
        elif claim_duration >= 10:
            # Claim ngắn (10-60s): Flexible threshold
            min_overlap_percent = 25  # Giảm xuống 25% file
            min_overlap_seconds = 3   # Hoặc 3 giây
            threshold_type = "FLEXIBLE"
            
        else:
            # Claim rất ngắn (<10s): Relaxed threshold
            min_overlap_percent = 10  # Chỉ cần 10% file
            min_overlap_seconds = 2   # Hoặc 2 giây
            threshold_type = "RELAXED"
        
        print(f"\n🔍 SEARCHING MATCHES for claim: {claim['song'][:40]}")
        print(f"   Duration: {claim_duration}s → Threshold: {threshold_type}")
        print(f"   Min: {min_overlap_percent}% file OR {min_overlap_seconds}s")
        
        # ============================================
        # BƯỚC 2: TÌM TẤT CẢ FILES OVERLAP
        # ============================================
        for track in tracklist:
            # Tính overlap
            overlap_start = max(track['start'], claim['start'])
            overlap_end = min(track['end'], claim['end'])
            
            if overlap_start >= overlap_end:
                continue  # Không overlap
            
            overlap_duration = overlap_end - overlap_start
            file_duration = track['end'] - track['start']
            
            # % overlap so với FILE
            overlap_percent = (overlap_duration / file_duration * 100) if file_duration > 0 else 0
            
            # % segment này so với TOÀN BỘ CLAIM
            claim_segment_percent = (overlap_duration / claim_duration * 100) if claim_duration > 0 else 0
            
            # ============================================
            # BƯỚC 3: ĐÁNH GIÁ ĐỘ QUAN TRỌNG
            # ============================================
            
            # Check 1: Overlap >= threshold % của FILE
            meets_percent = overlap_percent >= min_overlap_percent
            
            # Check 2: Overlap >= threshold seconds tuyệt đối
            meets_seconds = overlap_duration >= min_overlap_seconds
            
            # Check 3: Overlap >= 30% của CLAIM (quan trọng với claim ngắn)
            meets_claim_percent = claim_segment_percent >= 30
            
            # ✅ LOGIC QUYẾT ĐỊNH:
            # - Claim dài: Cần overlap_percent HOẶC overlap_seconds
            # - Claim ngắn: Cần overlap_percent HOẶC overlap_seconds HOẶC 30% claim
            
            if threshold_type == "STANDARD":
                is_significant = meets_percent or meets_seconds
            else:
                is_significant = meets_percent or meets_seconds or meets_claim_percent
            
            # ============================================
            # BƯỚC 4: LƯU MATCH NẾU SIGNIFICANT
            # ============================================
            if is_significant:
                match_info = {
                    'track': track,
                    'overlap_start': overlap_start,
                    'overlap_end': overlap_end,
                    'overlap_duration': overlap_duration,
                    'overlap_percent': overlap_percent,
                    'claim_segment_percent': claim_segment_percent,
                    'is_significant': True,
                    'threshold_type': threshold_type
                }
                matches.append(match_info)
                
                print(f"   ✅ MATCH: {track['filename'][:40]}")
                print(f"      Overlap: {overlap_duration}s ({overlap_percent:.1f}% file, {claim_segment_percent:.1f}% claim)")
            
            else:
                # Log skipped files (để debug)
                if overlap_duration > 0:
                    print(f"   ⏭️  SKIP: {track['filename'][:40]}")
                    print(f"      Overlap: {overlap_duration}s ({overlap_percent:.1f}% file, {claim_segment_percent:.1f}% claim)")
                    print(f"      Reason: Too small (< {min_overlap_percent}% AND < {min_overlap_seconds}s)")
        
        # ============================================
        # BƯỚC 5: SPECIAL CASE - NẾU KHÔNG TÌM THẤY GÌ
        # ============================================
        if not matches and claim_duration <= 30:
            # Claim ngắn mà không tìm thấy gì → Thử relaxed hơn
            print(f"\n   ⚠️  NO MATCHES with {threshold_type} threshold!")
            print(f"   🔄 RETRY with ULTRA-RELAXED threshold (any overlap ≥ 1s)...")
            
            for track in tracklist:
                overlap_start = max(track['start'], claim['start'])
                overlap_end = min(track['end'], claim['end'])
                
                if overlap_start >= overlap_end:
                    continue
                
                overlap_duration = overlap_end - overlap_start
                
                if overlap_duration >= 1:  # Chỉ cần ≥ 1 giây!
                    file_duration = track['end'] - track['start']
                    overlap_percent = (overlap_duration / file_duration * 100) if file_duration > 0 else 0
                    claim_segment_percent = (overlap_duration / claim_duration * 100) if claim_duration > 0 else 0
                    
                    matches.append({
                        'track': track,
                        'overlap_start': overlap_start,
                        'overlap_end': overlap_end,
                        'overlap_duration': overlap_duration,
                        'overlap_percent': overlap_percent,
                        'claim_segment_percent': claim_segment_percent,
                        'is_significant': False,  # Đánh dấu là "weak match"
                        'threshold_type': 'ULTRA_RELAXED'
                    })
                    
                    print(f"   ⚠️  WEAK MATCH: {track['filename'][:40]} ({overlap_duration}s)")
        
        # ============================================
        # BƯỚC 6: SORT VÀ RETURN
        # ============================================
        matches.sort(key=lambda x: x['overlap_start'])
        
        print(f"   📊 TOTAL MATCHES: {len(matches)}\n")
        
        return matches

    def _calculate_name_similarity(self, claim_song, track_filename):
        """
        ✅ TÍNH SIMILARITY GIỮA CLAIM VÀ TRACK
        
        Args:
            claim_song: Tên bài trong claim
            track_filename: Tên file trong tracklist
        
        Returns:
            float: Similarity score (0-100)
        """
        from difflib import SequenceMatcher
        
        # Normalize claim name
        claim_normalized = self.claim_parser._normalize_song_name_v2(claim_song)
        
        # Normalize track name (remove extension, prefix number)
        track_name = track_filename
        track_name = re.sub(r'^\d+-\s*', '', track_name)  # Remove "15- " prefix
        track_name = re.sub(r'\.(wav|mp3|m4a|flac)$', '', track_name, flags=re.IGNORECASE)
        track_name = re.sub(r'\s*\(\d+\)\s*', '', track_name)  # Remove "(1)" suffix
        track_normalized = self.claim_parser._normalize_song_name_v2(track_name)
        
        if not claim_normalized or not track_normalized:
            return 0
        
        # Calculate similarity using SequenceMatcher
        similarity = SequenceMatcher(None, claim_normalized, track_normalized).ratio() * 100
        
        return similarity


    def _check_substring(self, claim_song, track_filename):
        """
        ✅ KIỂM TRA CLAIM CÓ PHẢI SUBSTRING CỦA TRACK KHÔNG
        
        Args:
            claim_song: Tên bài trong claim
            track_filename: Tên file trong tracklist
        
        Returns:
            bool: True nếu claim là substring của track
        """
        # Normalize both
        claim_normalized = self.claim_parser._normalize_song_name_v2(claim_song)
        
        track_name = track_filename
        track_name = re.sub(r'^\d+-\s*', '', track_name)
        track_name = re.sub(r'\.(wav|mp3|m4a|flac)$', '', track_name, flags=re.IGNORECASE)
        track_name = re.sub(r'\s*\(\d+\)\s*', '', track_name)
        track_normalized = self.claim_parser._normalize_song_name_v2(track_name)
        
        if not claim_normalized or not track_normalized:
            return False
        
        # Check if claim is substring of track
        return claim_normalized in track_normalized

    def process_claims(self):
        """
        ✅ Xử Lý CLAIMS - WORKFLOW Mới V3.9.1 - FIXED VERSION
        
        Flow:
        1. Validate tracklist + claims
        2. Classify claims → AUTO_ACCEPT / NEED_REVIEW / REJECT (lần đầu)
        3. Hiển thị review tab nếu cần
        4. Build results và display (LUÔN LUÔN - cả 2 lần chạy)
        
        ✅ FIX V3.9.1:
        - Lần 2 chạy: Vẫn build và display results từ auto_accepted_claims
        - Đảm bảo có data cho Move Tab
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
        if not hasattr(self, '_validated') or not self._validated:
            print("\n" + "="*80)
            print("🔍 FIRST RUN - Classifying claims with NEW algorithm V3.9.1...")
            print("="*80 + "\n")
            
            # ============================================
            # BƯỚC 2: CLASSIFY CLAIMS - 3 CẤP ĐỘ
            # ============================================
            auto_accepted = []
            need_review = []
            auto_rejected = []
            
            for claim in self.claims:
                claim_duration = claim['end'] - claim['start']
                
                print(f"\n{'─'*80}")
                print(f"🎵 Processing claim: {claim['song'][:50]}")
                print(f"   Duration: {claim_duration}s ({self.claim_parser.format_time(claim_duration)})")
                print(f"   Time: {self.claim_parser.format_time(claim['start'])} → {self.claim_parser.format_time(claim['end'])}")
                print(f"{'─'*80}")
                
                # 🆕 TÌMẤT CẢ FILES MATCH
                all_matches = self.find_all_matching_tracks(claim, self.tracklist)
                
                if not all_matches:
                    # Không tìm thấy file nào
                    print(f"❌ NO MATCHES FOUND for '{claim['song'][:40]}'")
                    auto_rejected.append({
                        'claim': claim,
                        'track': None,
                        'reason': "Không tìm thấy file match nào trong tracklist"
                    })
                    continue
                
                # ============================================
                # CLASSIFY từng file match
                # ============================================
                for idx, match in enumerate(all_matches, 1):
                    print(f"\n   📂 Evaluating match #{idx}/{len(all_matches)}: {match['track']['filename'][:50]}")
                    
                    # Tính name similarity
                    name_similarity = self._calculate_name_similarity(
                        claim['song'], 
                        match['track']['filename']
                    )
                    
                    is_substring = self._check_substring(
                        claim['song'],
                        match['track']['filename']
                    )
                    
                    print(f"      Name similarity: {name_similarity:.1f}%")
                    print(f"      Is substring: {is_substring}")
                    print(f"      Overlap: {match['overlap_duration']}s ({match['overlap_percent']:.1f}% file, {match['claim_segment_percent']:.1f}% claim)")
                    
                    # Lấy threshold type
                    threshold_type = match.get('threshold_type', 'STANDARD')
                    is_significant = match.get('is_significant', True)
                    
                    print(f"      Threshold: {threshold_type}")
                    
                    # ============================================
                    # PHÂN LOẠI Dựa TRÊN THRESHOLD TYPE
                    # ============================================
                    
                    # === CASE 1: STANDARD MATCHES (claim dài > 60s) ===
                    if threshold_type == "STANDARD":
                        if is_substring and match['overlap_percent'] >= 50:
                            # AUTO-ACCEPT
                            print(f"      ✅ Decision: AUTO-ACCEPT (substring + high overlap)")
                            auto_accepted.append({
                                'claim': claim,
                                'track': match['track'],
                                'match_info': {
                                    'overlap_percent': match['overlap_percent'],
                                    'overlap_duration': match['overlap_duration'],
                                    'claim_segment_percent': match['claim_segment_percent'],
                                    'name_similarity': name_similarity,
                                    'is_substring': is_substring,
                                    'threshold_type': threshold_type,
                                    'reasons': [
                                        f"✅ Overlap {match['overlap_percent']:.1f}% của file",
                                        f"📊 Chiếm {match['claim_segment_percent']:.1f}% claim",
                                        f"✅ Tên match"
                                    ],
                                    'match_level': 'AUTO_ACCEPT'
                                }
                            })
                        
                        elif match['overlap_percent'] >= 30 or match['overlap_duration'] >= 10:
                            # NEED REVIEW
                            print(f"      ⚠️ Decision: NEED REVIEW (moderate overlap)")
                            need_review.append({
                                'claim': claim,
                                'track': match['track'],
                                'match_info': {
                                    'overlap_percent': match['overlap_percent'],
                                    'overlap_duration': match['overlap_duration'],
                                    'claim_segment_percent': match['claim_segment_percent'],
                                    'name_similarity': name_similarity,
                                    'is_substring': is_substring,
                                    'threshold_type': threshold_type,
                                    'reasons': [
                                        f"⚠️ Overlap {match['overlap_percent']:.1f}%",
                                        f"📊 Chiếm {match['claim_segment_percent']:.1f}% claim",
                                        f"ℹ️ Name similarity: {name_similarity:.1f}%"
                                    ],
                                    'match_level': 'NEED_REVIEW'
                                }
                            })
                        
                        else:
                            # REJECT
                            print(f"      ❌ Decision: REJECT (overlap too low)")
                            auto_rejected.append({
                                'claim': claim,
                                'track': match['track'],
                                'match_info': {
                                    'overlap_percent': match['overlap_percent'],
                                    'overlap_duration': match['overlap_duration'],
                                    'threshold_type': threshold_type,
                                    'reasons': [
                                        f"❌ Overlap quá thấp: {match['overlap_percent']:.1f}%",
                                        f"❌ Chỉ {match['overlap_duration']}s"
                                    ],
                                    'match_level': 'REJECT'
                                }
                            })
                    
                    # === CASE 2: FLEXIBLE MATCHES (claim ngắn 10-60s) ===
                    elif threshold_type == "FLEXIBLE":
                        if is_substring and match['overlap_percent'] >= 25:
                            # AUTO-ACCEPT
                            print(f"      ✅ Decision: AUTO-ACCEPT (short claim + good match)")
                            auto_accepted.append({
                                'claim': claim,
                                'track': match['track'],
                                'match_info': {
                                    'overlap_percent': match['overlap_percent'],
                                    'overlap_duration': match['overlap_duration'],
                                    'claim_segment_percent': match['claim_segment_percent'],
                                    'name_similarity': name_similarity,
                                    'is_substring': is_substring,
                                    'threshold_type': threshold_type,
                                    'reasons': [
                                        f"ℹ️ Claim ngắn ({claim_duration}s)",
                                        f"✅ Overlap {match['overlap_duration']}s ({match['overlap_percent']:.1f}% file)",
                                        f"📊 Chiếm {match['claim_segment_percent']:.1f}% claim",
                                        f"✅ Tên match"
                                    ],
                                    'match_level': 'AUTO_ACCEPT'
                                }
                            })
                        
                        else:
                            # NEED REVIEW (luôn review với claim ngắn)
                            print(f"      ⚠️ Decision: NEED REVIEW (short claim - manual check needed)")
                            need_review.append({
                                'claim': claim,
                                'track': match['track'],
                                'match_info': {
                                    'overlap_percent': match['overlap_percent'],
                                    'overlap_duration': match['overlap_duration'],
                                    'claim_segment_percent': match['claim_segment_percent'],
                                    'name_similarity': name_similarity,
                                    'is_substring': is_substring,
                                    'threshold_type': threshold_type,
                                    'reasons': [
                                        f"⚠️ Claim ngắn ({claim_duration}s)",
                                        f"⚠️ Overlap {match['overlap_duration']}s ({match['claim_segment_percent']:.1f}% claim)",
                                        f"ℹ️ Name similarity: {name_similarity:.1f}%",
                                        f"❗ Cần xác nhận thủ công"
                                    ],
                                    'match_level': 'NEED_REVIEW'
                                }
                            })
                    
                    # === CASE 3: RELAXED/ULTRA_RELAXED (claim rất ngắn <10s) ===
                    else:
                        # Luôn NEED REVIEW với claim rất ngắn
                        print(f"      ⚠️ Decision: NEED REVIEW (very short claim - MUST manual check)")
                        need_review.append({
                            'claim': claim,
                            'track': match['track'],
                            'match_info': {
                                'overlap_percent': match['overlap_percent'],
                                'overlap_duration': match['overlap_duration'],
                                'claim_segment_percent': match['claim_segment_percent'],
                                'name_similarity': name_similarity,
                                'is_substring': is_substring,
                                'threshold_type': threshold_type,
                                'reasons': [
                                    f"⚠️ Claim rất ngắn ({claim_duration}s)",
                                    f"⚠️ Overlap {match['overlap_duration']}s",
                                    f"ℹ️ Name similarity: {name_similarity:.1f}%",
                                    f"❗ BẮT BUỘC review thủ công"
                                ],
                                'match_level': 'NEED_REVIEW'
                            }
                        })
            
            # ============================================
            # BƯỚC 3: LƯU KẾT QUẢ
            # ============================================
            self.auto_accepted_claims = auto_accepted
            self.ambiguous_claims = need_review
            
            # ✅ THÊM: Lưu rejected để log (không hiển thị trong kết quả)
            if not hasattr(self, 'rejected_claims'):
                self.rejected_claims = []
            self.rejected_claims = auto_rejected
            
            self._validated = True
            
            # ============================================
            # BƯỚC 4: LOG KẾT QUẢ
            # ============================================
            print(f"\n{'='*80}")
            print(f"📊 CLASSIFICATION RESULTS:")
            print(f"   ✅ Auto-accepted: {len(auto_accepted)} claims")
            print(f"   ⚠️  Need review: {len(need_review)} claims")
            print(f"   ❌ Auto-rejected: {len(auto_rejected)} claims")
            print(f"{'='*80}\n")
            
            # Log rejected claims
            if auto_rejected:
                print(f"\n{'❌'*40}")
                print(f"❌ AUTO-REJECTED CLAIMS ({len(auto_rejected)}):")
                print(f"{'❌'*40}\n")
                
                for idx, item in enumerate(auto_rejected, 1):
                    claim = item['claim']
                    
                    if item.get('match_info'):
                        match_info = item['match_info']
                        reason = ' | '.join(match_info.get('reasons', []))
                        file_name = match_info['track']['filename'] if match_info.get('track') else "N/A"
                    else:
                        reason = item.get('reason', 'Unknown')
                        file_name = "N/A"
                    
                    print(f"{idx}. Claim: '{claim['song'][:50]}'")
                    print(f"   ⏱️  Time: {self.claim_parser.format_time_clean(claim['start'])} → "
                          f"{self.claim_parser.format_time_clean(claim['end'])}")
                    print(f"   📂 Best match: {file_name[:60]}")
                    print(f"   ❌ Reason: {reason}\n")
            
            # ============================================
            # BƯỚC 5: Xử Lý NEED_REVIEW
            # ============================================
            if need_review:
                # Update review tab
                self.update_review_tab_v2()
                
                response = messagebox.askyesno(
                    "⚠️  Có Claims Cần Review",
                    f"📊 KẾT QUẢ PHÂN LOẠI:\n\n"
                    f"✅ Tự động chấp nhận: {len(auto_accepted)} claims\n"
                    f"⚠️  Cần review: {len(need_review)} claims\n"
                    f"❌ Tự động loại bỏ: {len(auto_rejected)} claims\n\n"
                    f"💡 HƯỚNG DẪN:\n"
                    f"• Claims ĐÃ LOẠI BỎ sẽ KHÔNG hiển thị trong kết quả\n"
                    f"• Claims CẦN REVIEW có thể đúng/sai - cần xác nhận\n\n"
                    f"Bạn muốn review {len(need_review)} claims không chắc chắn?\n\n"
                    f"• YES: Mở Review Tab để xác nhận từng claim\n"
                    f"• NO: Chỉ dùng {len(auto_accepted)} claims đã chấp nhận"
                )
                
                if response:
                    # Chuyển sang Review Tab
                    self.notebook.select(1)
                    
                    messagebox.showinfo(
                        "📋 Hướng Dẫn Review",
                        "🔍 TRONG REVIEW TAB:\n\n"
                        "1. ✅ Chấp nhận: Claim đúng → Đưa vào kết quả\n"
                        "2. ❌ Loại bỏ: Claim sai → Không đưa vào kết quả\n"
                        "3. ✏️  Chỉnh sửa: Sửa tên/time rồi chấp nhận\n\n"
                        "4. Sau khi xong → Quay lại tab 'Kiểm Tra Claims'\n"
                        "5. Nhấn 'KIỂM TRA CLAIM' lại để xem kết quả"
                    )
                    return
                else:
                    # User chọn NO → Bỏ qua ambiguous
                    messagebox.showinfo(
                        "ℹ️  Bỏ Qua Review",
                        f"⚠️  ĐÃ BỎ QUA {len(need_review)} claims cần review\n\n"
                        f"📊 Kết quả sẽ CHỈ bao gồm:\n"
                        f"✅ {len(auto_accepted)} claims đã tự động chấp nhận\n\n"
                        f"❌ {len(auto_rejected)} claims đã loại bỏ\n"
                        f"   → Không hiển thị trong kết quả"
                    )
                    
                    # Xóa ambiguous claims khỏi danh sách
                    for amb in self.ambiguous_claims:
                        if amb['claim'] in self.claims:
                            self.claims.remove(amb['claim'])
                    
                    self.ambiguous_claims = []
            
            else:
                # Không có claims cần review
                if not auto_accepted:
                    messagebox.showwarning(
                        "⚠️  Không Có Claims",
                        f"❌ Tất cả {len(auto_rejected)} claims đã bị loại bỏ!\n\n"
                        f"Lý do phổ biến:\n"
                        f"• Tên bài khác biệt quá nhiều\n"
                        f"• Thời gian không khớp với tracklist\n\n"
                        f"💡 Kiểm tra lại:\n"
                        f"• OCR có đọc đúng tên bài không?\n"
                        f"• Timestamps có chính xác không?"
                    )
                    self._validated = False
                    return
        
        # ============================================
        # BƯỚC 6: KIỂM TRA LẦN 2+ - Có còn ambiguous?
        # ============================================
        else:
            print("\n" + "="*80)
            print("🔄 SECOND RUN - Checking review status...")
            print("="*80 + "\n")
            
            if self.ambiguous_claims:
                response = messagebox.askyesnocancel(
                    "⚠️  Còn Claims Chưa Review",
                    f"Còn {len(self.ambiguous_claims)} claim(s) chưa được xử lý!\n\n"
                    f"📊 Hiện tại:\n"
                    f"  ✅ Đã chấp nhận: {len(self.auto_accepted_claims)} claims\n"
                    f"  ⚠️  Chưa xử lý: {len(self.ambiguous_claims)} claims\n\n"
                    f"Bạn muốn:\n"
                    f"• YES: Quay lại Review Tab để tiếp tục\n"
                    f"• NO: Bỏ qua và chỉ dùng claims đã chấp nhận\n"
                    f"• CANCEL: Hủy"
                )
                
                if response is None:  # Cancel
                    return
                elif response:  # YES
                    self.notebook.select(1)
                    return
                else:  # NO
                    messagebox.showinfo(
                        "ℹ️  Bỏ Qua",
                        f"⚠️  ĐÃ BỎ QUA {len(self.ambiguous_claims)} claims chưa review\n\n"
                        f"📊 Kết quả sẽ CHỈ bao gồm:\n"
                        f"✅ {len(self.auto_accepted_claims)} claims đã chấp nhận"
                    )
                    
                    # Xóa ambiguous
                    for amb in self.ambiguous_claims:
                        if amb['claim'] in self.claims:
                            self.claims.remove(amb['claim'])
                    
                    self.ambiguous_claims = []
        
        # ============================================
        # ✅ BƯỚC 7: BUILD & DISPLAY RESULTS (LUÔN LUÔN)
        # ============================================
        claims_to_process = self.auto_accepted_claims
        
        if not claims_to_process:
            messagebox.showwarning("⚠️  Không Có Claims", "Không có claim nào được chấp nhận!")
            return
        
        print(f"\n{'='*80}")
        print(f"📊 PROCESSING {len(claims_to_process)} ACCEPTED CLAIMS...")
        print(f"{'='*80}\n")
        
        # ✅ BUILD claimed_tracks từ wrappers
        claimed_tracks = []
        
        for wrapper in claims_to_process:
            claimed_tracks.append({
                'track': wrapper['track'],
                'claim': wrapper['claim'],
                'match_info': wrapper.get('match_info', {}),
                'overlap_percent': wrapper.get('match_info', {}).get('overlap_percent', 0),
                'name_similarity': wrapper.get('match_info', {}).get('name_similarity', 0),
                'match_score': wrapper.get('match_info', {}).get('overlap_percent', 0)
            })
        
        # ✅ DISPLAY RESULTS
        self.display_results_v2(claimed_tracks)
        
        # ✅ THÔNG BÁO
        unique_files = len(set(item['track']['filename'] for item in claimed_tracks))
        
        summary = f"✅ HOÀN THÀNH KIỂM TRA!\n\n"
        summary += f"📊 KẾT QUẢ:\n"
        summary += f"  ✅ Tổng claims đã xử lý: {len(claims_to_process)}\n"
        summary += f"  ⚠️  File bị claim: {unique_files}/{len(self.tracklist)}\n"
        summary += f"  📍 Tổng lần claim: {len(claimed_tracks)}\n"
        
        if hasattr(self, 'rejected_claims') and self.rejected_claims:
            summary += f"\n  ❌ Đã loại bỏ: {len(self.rejected_claims)} claims\n"
            summary += f"     (không hiển thị trong kết quả)\n"
        
        summary += f"\n💡 Chi tiết xem bên dưới!"
        
        messagebox.showinfo("✅ Hoàn Thành", summary)

    def process_claims_without_validate(self):
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
        self.results_text.delete(1.0, tk.END)
        
        header = "="*140 + "\n"
        header += "YOUTUBE CLAIM CHECKER - KẾT QUẢ KIỂM TRA v3.9.1\n"
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
                
                # ✅ THÊM: Hiển thị match score (nếu có)
                if 'name_similarity' in item and 'match_score' in item:
                    name_sim = item['name_similarity']
                    match_score = item['match_score']
                    result += f"  🎯 Match score: {match_score:.1f} (Name: {name_sim:.1f}% | Overlap: {item['overlap_percent']:.1f}%)\n"
                
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
        # ✅ Update Move Tab nếu đã có kết quả
        if hasattr(self, 'move_tab'):
            self.refresh_file_list()
            
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
                f.write("BÁO CÁO CHI TIẾT - v3.9.1\n")
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
        ✅ FIX: Xử lý đúng wrapper structure
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
        
        # ✅ FIX: Lấy wrapper, không phải claim trực tiếp
        wrapper = self.ambiguous_claims[claim_id]
        
        # Chuyển sang auto_accepted
        self.auto_accepted_claims.append(wrapper)  # ✅ Chuyển cả wrapper
        self.ambiguous_claims.remove(wrapper)
        
        # ✅ UPDATE UI
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
            print(f"✅ Accepted claim. Remaining: {remaining}")

    def reject_claim(self):
        """
        ✅ FIX: Xử lý đúng wrapper structure
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
        
        # ✅ FIX: Lấy wrapper
        wrapper = self.ambiguous_claims[claim_id]
        claim = wrapper['claim']
        
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
        
        # ✅ FIX: Xóa wrapper và claim
        self.ambiguous_claims.remove(wrapper)
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
            print(f"❌ Rejected claim. Remaining: {remaining}")

    def reject_claim(self):
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

    def accept_all_claims(self):
        """
        ✅ V3.9.2: Chấp nhận tất cả + TỰ ĐỘNG DISPLAY KẾT QUẢ
        
        Flow mới:
        1. Confirm với user
        2. Chuyển tất cả sang auto_accepted
        3. TỰ ĐỘNG build & display results
        4. TỰ ĐỘNG chuyển về tab chính
        5. KHÔNG CẦN nhấn "Kiểm Tra Claim" nữa
        """
        if not self.ambiguous_claims:
            messagebox.showinfo("Thông báo", "Không có claim nào cần review!")
            return
        
        # ============================================
        # BƯỚC 1: TẠO PREVIEW CHI TIẾT
        # ============================================
        issues_text = ""
        for idx, wrapper in enumerate(self.ambiguous_claims[:10], 1):  # Max 10
            claim = wrapper['claim']
            match_info = wrapper.get('match_info', {})
            reasons = match_info.get('reasons', ['Unknown'])
            
            issues_text += f"\n{idx}. {claim['song'][:40]}\n"
            issues_text += f"   ⚠️ {'; '.join(reasons)}\n"
        
        if len(self.ambiguous_claims) > 10:
            issues_text += f"\n... và {len(self.ambiguous_claims) - 10} claims khác\n"
        
        # ============================================
        # BƯỚC 2: CONFIRM VỚI CẢNH BÁO
        # ============================================
        confirm = messagebox.askyesno(
            "✅ XÁC NHẬN CHẤP NHẬN TẤT CẢ",
            f"Bạn đang chấp nhận {len(self.ambiguous_claims)} claims có vấn đề:\n"
            f"{issues_text}\n\n"
            f"❌ CÁC CLAIMS NÀY CÓ THỂ SAI/NHẦM!\n\n"
            f"Sau khi chấp nhận:\n"
            f"✅ Tự động hiển thị kết quả\n"
            f"✅ Tự động chuyển về tab chính\n"
            f"✅ Sẵn sàng xuất file hoặc di chuyển\n\n"
            f"Chắc chắn chấp nhận tất cả?"
        )
        
        if not confirm:
            return
        
        # ============================================
        # BƯỚC 3: CHUYỂN TẤT CẢ WRAPPERS
        # ============================================
        accepted_count = len(self.ambiguous_claims)
        self.auto_accepted_claims.extend(self.ambiguous_claims)
        self.ambiguous_claims = []
        
        # Update review tab (để tab title = 0)
        self.update_review_tab()
        
        # ============================================
        # BƯỚC 4: TỰ ĐỘNG BUILD & DISPLAY RESULTS
        # ============================================
        print(f"\n{'='*80}")
        print(f"✅ AUTO-ACCEPTING {accepted_count} CLAIMS...")
        print(f"📊 Building results automatically...")
        print(f"{'='*80}\n")
        
        # Build claimed_tracks
        claimed_tracks = []
        for wrapper in self.auto_accepted_claims:
            claimed_tracks.append({
                'track': wrapper['track'],
                'claim': wrapper['claim'],
                'match_info': wrapper.get('match_info', {}),
                'overlap_percent': wrapper.get('match_info', {}).get('overlap_percent', 0),
                'name_similarity': wrapper.get('match_info', {}).get('name_similarity', 0),
                'match_score': wrapper.get('match_info', {}).get('overlap_percent', 0)
            })
        
        # Display results
        self.display_results_v2(claimed_tracks)
        
        # ============================================
        # BƯỚC 5: TỰ ĐỘNG CHUYỂN VỀ TAB CHÍNH
        # ============================================
        self.notebook.select(0)
        
        # ============================================
        # BƯỚC 6: THÔNG BÁO KẾT QUẢ
        # ============================================
        unique_files = len(set(item['track']['filename'] for item in claimed_tracks))
        
        messagebox.showinfo(
            "✅ Hoàn Thành",
            f"✅ ĐÃ CHẤP NHẬN TẤT CẢ!\n\n"
            f"📊 KẾT QUẢ:\n"
            f"  ✅ Tổng claims: {len(self.auto_accepted_claims)}\n"
            f"  ⚠️  File bị claim: {unique_files}/{len(self.tracklist)}\n"
            f"  📍 Tổng lần claim: {len(claimed_tracks)}\n\n"
            f"💡 BẠN CÓ THỂ:\n"
            f"  • Xem kết quả chi tiết bên dưới\n"
            f"  • Nhấn '💾 Xuất TXT/CSV'\n"
            f"  • Chuyển sang tab 'Di Chuyển File'"
        )
        
        print(f"\n✅ accept_all_claims() completed successfully\n")

    def accept_selected_claims(self):
        """
        ✅ NEW: Chấp nhận nhiều claims đã chọn
        """
        selections = self.review_tree.selection()
        if not selections:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất 1 claim!")
            return
        
        # Lấy indices
        indices = []
        claim_previews = []
        for sel in selections:
            item = self.review_tree.item(sel)
            claim_id = int(item['values'][0]) - 1
            indices.append(claim_id)
            
            # Preview cho confirm dialog
            song_name = item['values'][1]
            time_range = item['values'][2]
            claim_previews.append(f"  • {song_name} ({time_range})")
        
        # Xác nhận
        preview_text = "\n".join(claim_previews[:10])  # Max 10 dòng
        if len(claim_previews) > 10:
            preview_text += f"\n  ... và {len(claim_previews)-10} claims khác"
        
        confirm = messagebox.askyesno(
            "✅ Xác nhận chấp nhận",
            f"Chấp nhận {len(selections)} claim(s)?\n\n"
            f"{preview_text}\n\n"
            f"Claims sẽ được đưa vào kết quả kiểm tra."
        )
        
        if not confirm:
            return
        
        # ✅ Chuyển wrappers sang auto_accepted
        # Sort giảm dần để remove không bị lỗi index
        indices.sort(reverse=True)
        
        moved_count = 0
        for idx in indices:
            if idx < len(self.ambiguous_claims):
                wrapper = self.ambiguous_claims[idx]
                self.auto_accepted_claims.append(wrapper)
                self.ambiguous_claims.remove(wrapper)
                moved_count += 1
        
        # Update UI
        self.update_review_tab()
        
        # Thông báo
        remaining = len(self.ambiguous_claims)
        if remaining == 0:
            messagebox.showinfo(
                "✅ Hoàn thành Review",
                f"Đã chấp nhận {moved_count} claim(s)!\n\n"
                f"✅ TẤT CẢ claims đã được xử lý!\n"
                f"📊 Tổng: {len(self.auto_accepted_claims)} claims\n\n"
                f"💡 Quay lại tab 'Kiểm Tra Claims' và nhấn\n"
                f"   'KIỂM TRA CLAIM' để xem kết quả"
            )
        else:
            print(f"✅ Accepted {moved_count} claims. Remaining: {remaining}")
            # Clear selection để tiếp tục
            for item in self.review_tree.selection():
                self.review_tree.selection_remove(item)

    def reject_selected_claims(self):
        """
        ✅ NEW: Loại bỏ nhiều claims đã chọn
        """
        selections = self.review_tree.selection()
        if not selections:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất 1 claim!")
            return
        
        # Lấy indices và preview
        indices = []
        claim_previews = []
        for sel in selections:
            item = self.review_tree.item(sel)
            claim_id = int(item['values'][0]) - 1
            indices.append(claim_id)
            
            song_name = item['values'][1]
            time_range = item['values'][2]
            claim_previews.append(f"  • {song_name} ({time_range})")
        
        # Xác nhận với cảnh báo
        preview_text = "\n".join(claim_previews[:10])
        if len(claim_previews) > 10:
            preview_text += f"\n  ... và {len(claim_previews)-10} claims khác"
        
        confirm = messagebox.askyesno(
            "⚠️ Xác nhận loại bỏ",
            f"❌ LOẠI BỎ {len(selections)} claim(s)?\n\n"
            f"{preview_text}\n\n"
            f"⚠️ Claims sẽ bị XÓA HẲN khỏi dữ liệu!\n"
            f"⚠️ KHÔNG THỂ HOÀN TÁC!\n\n"
            f"Chắc chắn loại bỏ?"
        )
        
        if not confirm:
            return
        
        # ✅ Xóa wrappers và claims
        # Sort giảm dần để remove không bị lỗi index
        indices.sort(reverse=True)
        
        removed_count = 0
        for idx in indices:
            if idx < len(self.ambiguous_claims):
                wrapper = self.ambiguous_claims[idx]
                claim = wrapper['claim']
                
                # Xóa wrapper
                self.ambiguous_claims.remove(wrapper)
                
                # Xóa claim khỏi self.claims
                if claim in self.claims:
                    self.claims.remove(claim)
                
                removed_count += 1
        
        # Update UI
        self.update_review_tab()
        
        # Thông báo
        remaining = len(self.ambiguous_claims)
        if remaining == 0:
            messagebox.showinfo(
                "✅ Hoàn thành Review",
                f"Đã loại bỏ {removed_count} claim(s)!\n\n"
                f"✅ TẤT CẢ claims đã được xử lý!\n"
                f"📊 Tổng: {len(self.auto_accepted_claims)} claims\n\n"
                f"💡 Quay lại tab 'Kiểm Tra Claims' và nhấn\n"
                f"   'KIỂM TRA CLAIM' để xem kết quả"
            )
        else:
            print(f"❌ Rejected {removed_count} claims. Remaining: {remaining}")
            # Clear selection để tiếp tục
            for item in self.review_tree.selection():
                self.review_tree.selection_remove(item)

    def smart_accept_claim(self):
        """
        ✅ Smart Accept - Tự động nhận diện 1 hoặc nhiều
        - Nếu chọn 1 claim → Accept đơn giản, không popup
        - Nếu chọn nhiều → Confirm trước khi accept
        """
        selections = self.review_tree.selection()
        
        if not selections:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất 1 claim!")
            return
        
        if len(selections) == 1:
            # ✅ Chỉ 1 claim → Xử lý trực tiếp
            self.accept_claim()
        else:
            # ✅ Nhiều claims → Gọi hàm accept_selected
            self.accept_selected_claims()


    def smart_reject_claim(self):
        """
        ✅ Smart Reject - Tự động nhận diện 1 hoặc nhiều
        - Nếu chọn 1 claim → Confirm trước khi reject
        - Nếu chọn nhiều → Confirm với danh sách đầy đủ
        """
        selections = self.review_tree.selection()
        
        if not selections:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất 1 claim!")
            return
        
        if len(selections) == 1:
            # ✅ Chỉ 1 claim → Xử lý trực tiếp
            self.reject_claim()
        else:
            # ✅ Nhiều claims → Gọi hàm reject_selected
            self.reject_selected_claims()

    def edit_claim(self):
        """
        ✅ FIX: Chỉ cho phép chỉnh sửa 1 claim
        """
        selections = self.review_tree.selection()
        
        # ✅ THÊM: Kiểm tra số lượng selection
        if not selections:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn claim!")
            return
        
        if len(selections) > 1:
            messagebox.showwarning(
                "Cảnh báo", 
                f"Chỉ có thể chỉnh sửa 1 claim tại một thời điểm!\n\n"
                f"Bạn đang chọn {len(selections)} claims.\n"
                f"Vui lòng chọn lại chỉ 1 claim."
            )
            return
        
        item = self.review_tree.item(selection[0])
        claim_id = int(item['values'][0]) - 1
        
        if claim_id >= len(self.ambiguous_claims):
            messagebox.showerror("Lỗi", "Claim không tồn tại!")
            return
        
        # ✅ FIX: Lấy wrapper và claim
        wrapper = self.ambiguous_claims[claim_id]
        claim = wrapper['claim']
        
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
                
                # ✅ TẠO WRAPPER MỚI
                new_wrapper = {
                    'claim': new_claim,
                    'track': wrapper.get('track'),  # Giữ track cũ
                    'match_info': {
                        'reasons': ['User edited'],
                        'name_similarity': 100,
                        'overlap_percent': 100,
                        'is_substring': True,
                        'is_time_contained': True
                    }
                }
                
                # ✅ XÓA WRAPPER CŨ
                self.ambiguous_claims.remove(wrapper)
                if claim in self.claims:
                    self.claims.remove(claim)
                
                # ✅ THÊM WRAPPER MỚI
                self.claims.append(new_claim)
                self.auto_accepted_claims.append(new_wrapper)
                
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


    def reprocess_claims(self):
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
        ✅ V3.9.2: Quay lại + TỰ ĐỘNG PROCESS CLAIMS ĐÃ REVIEW
        
        Flow mới:
        1. Kiểm tra còn claims chưa xử lý không
        2. Nếu còn → Hỏi user muốn gì
        3. Nếu không còn hoặc user chọn bỏ qua → TỰ ĐỘNG process & display
        4. KHÔNG CẦN nhấn "Kiểm Tra Claim" nữa
        """
        remaining = len(self.ambiguous_claims)
        accepted = len(self.auto_accepted_claims)
        
        # ============================================
        # CASE 1: CÒN CLAIMS CHƯA XỬ LÝ
        # ============================================
        if remaining > 0:
            response = messagebox.askyesnocancel(
                "⚠️  Còn Claims Chưa Xử Lý",
                f"Còn {remaining} claim(s) chưa được xử lý!\n\n"
                f"📊 Hiện tại:\n"
                f"  ✅ Đã chấp nhận: {accepted} claims\n"
                f"  ⚠️  Chưa xử lý: {remaining} claims\n\n"
                f"Bạn muốn:\n"
                f"• YES: Tiếp tục review (ở lại tab này)\n"
                f"• NO: Bỏ qua & xử lý claims đã chấp nhận\n"
                f"       → Tự động hiển thị kết quả\n"
                f"• CANCEL: Hủy"
            )
            
            if response is None:  # CANCEL
                return
            
            elif response:  # YES → Ở lại
                return
            
            else:  # NO → Bỏ qua & process
                # Xóa ambiguous
                for wrapper in self.ambiguous_claims:
                    claim = wrapper['claim']
                    if claim in self.claims:
                        self.claims.remove(claim)
                self.ambiguous_claims = []
        
        # ============================================
        # CASE 2: ĐÃ XỬ LÝ XONG HOẶC BỎ QUA
        # ============================================
        
        if accepted == 0:
            messagebox.showwarning(
                "⚠️  Không Có Claims",
                "Không có claim nào được chấp nhận!\n\n"
                "Quay lại tab chính mà không có dữ liệu."
            )
            self.notebook.select(0)
            return
        
        # ============================================
        # BƯỚC 1: BUILD & DISPLAY RESULTS TỰ ĐỘNG
        # ============================================
        print(f"\n{'='*80}")
        print(f"📊 AUTO-PROCESSING {accepted} ACCEPTED CLAIMS...")
        print(f"{'='*80}\n")
        
        # Build claimed_tracks
        claimed_tracks = []
        for wrapper in self.auto_accepted_claims:
            claimed_tracks.append({
                'track': wrapper['track'],
                'claim': wrapper['claim'],
                'match_info': wrapper.get('match_info', {}),
                'overlap_percent': wrapper.get('match_info', {}).get('overlap_percent', 0),
                'name_similarity': wrapper.get('match_info', {}).get('name_similarity', 0),
                'match_score': wrapper.get('match_info', {}).get('overlap_percent', 0)
            })
        
        # Display results
        self.display_results_v2(claimed_tracks)
        
        # ============================================
        # BƯỚC 2: CHUYỂN VỀ TAB CHÍNH
        # ============================================
        self.notebook.select(0)
        
        # ============================================
        # BƯỚC 3: THÔNG BÁO
        # ============================================
        unique_files = len(set(item['track']['filename'] for item in claimed_tracks))
        
        if remaining > 0:
            # Đã bỏ qua một số claims
            messagebox.showinfo(
                "✅ Đã Xử Lý",
                f"⚠️  ĐÃ BỎ QUA {remaining} CLAIMS CHƯA XỬ LÝ\n\n"
                f"📊 KẾT QUẢ:\n"
                f"  ✅ Claims đã chấp nhận: {accepted}\n"
                f"  ⚠️  File bị claim: {unique_files}/{len(self.tracklist)}\n"
                f"  📍 Tổng lần claim: {len(claimed_tracks)}\n\n"
                f"💡 Kết quả chi tiết xem bên dưới!"
            )
        else:
            # Đã xử lý hết
            messagebox.showinfo(
                "✅ Hoàn Thành Review",
                f"✅ ĐÃ XỬ LÝ XONG TẤT CẢ!\n\n"
                f"📊 KẾT QUẢ:\n"
                f"  ✅ Claims đã chấp nhận: {accepted}\n"
                f"  ⚠️  File bị claim: {unique_files}/{len(self.tracklist)}\n"
                f"  📍 Tổng lần claim: {len(claimed_tracks)}\n\n"
                f"💡 BẠN CÓ THỂ:\n"
                f"  • Xem kết quả chi tiết bên dưới\n"
                f"  • Nhấn '💾 Xuất TXT/CSV'\n"
                f"  • Chuyển sang tab 'Di Chuyển File'"
            )
        
        print(f"\n✅ go_back_to_main_tab() completed successfully\n")

# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    root = tk.Tk()
    app = ClaimCheckerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()