import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import re
from datetime import timedelta
from pathlib import Path
import pytesseract
from PIL import Image, ImageGrab, ImageEnhance, ImageFilter
import os
import difflib

class ClaimCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Claim Checker v3.0 - Kiểm Tra File WAV Bị Claim")
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
    
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        title_label = ttk.Label(main_frame, text="YOUTUBE CLAIM CHECKER v3.0", 
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
        
        # Text input section
        self.text_frame = ttk.LabelFrame(self.main_tab, text="Nhập Claims từ Text", padding="10")
        self.text_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        self.text_frame.grid_remove()
        
        ttk.Label(self.text_frame, text="Paste text claim vào đây (có thể paste nhiều lần):").grid(row=0, column=0, sticky=tk.W)
        
        self.text_input = scrolledtext.ScrolledText(self.text_frame, width=100, height=8, 
                                                    font=('Consolas', 9))
        self.text_input.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        text_btn_frame = ttk.Frame(self.text_frame)
        text_btn_frame.grid(row=2, column=0, pady=5)
        ttk.Button(text_btn_frame, text="➕ Thêm Claims", command=self.add_text_claims).pack(side=tk.LEFT, padx=2)
        ttk.Button(text_btn_frame, text="🗑️ Xóa Text", command=self.clear_text_input).pack(side=tk.LEFT, padx=2)
        ttk.Button(text_btn_frame, text="🗑️ Xóa Tất Cả", command=self.clear_all_text_claims).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(self.text_frame, text="Claims đã nhập:").grid(row=3, column=0, sticky=tk.W, pady=(10,0))
        self.text_claims_display = scrolledtext.ScrolledText(self.text_frame, width=100, height=6, 
                                                            font=('Consolas', 9), state='disabled')
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
    
    def add_text_claims(self):
        text = self.text_input.get("1.0", tk.END).strip()
        
        if not text:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập text claim!")
            return
        
        try:
            parsed_claims = self.parse_text_claims(text)
            
            if not parsed_claims:
                messagebox.showwarning("Cảnh báo", "Không tìm thấy claim hợp lệ trong text!")
                return
            
            for claim in parsed_claims:
                self.claims.append(claim)
            
            self.update_text_claims_display()
            self.text_input.delete("1.0", tk.END)
            
            messagebox.showinfo("Thành công", f"Đã thêm {len(parsed_claims)} claims từ text!")
            
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể parse text:\n{str(e)}")
    
    def parse_text_claims(self, text):
        claims = []
        lines = text.split('\n')
        current_song = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if not re.search(r'\d+:\d+', line):
                current_song = line
                continue
            
            if "Nội dung được tìm thấy trong" in line or "Nội dung" in line:
                continue
            
            if current_song:
                timestamp_pattern = r'(\d{1,2}):(\d{2}):(\d{2})\s*[—–-]\s*(\d{1,2}):(\d{2}):(\d{2})'
                matches = re.findall(timestamp_pattern, line)
                
                for match in matches:
                    try:
                        start_h, start_m, start_s, end_h, end_m, end_s = map(int, match)
                        start_seconds = start_h * 3600 + start_m * 60 + start_s
                        end_seconds = end_h * 3600 + end_m * 60 + end_s
                        
                        if start_seconds >= end_seconds:
                            continue
                        
                        duration = end_seconds - start_seconds
                        if duration < 1 or duration > 14400:
                            continue
                        
                        claim = {
                            'song': current_song,
                            'start': start_seconds,
                            'end': end_seconds,
                            'source': 'Text Input',
                            'confidence': 100,
                            'song_confidence': 100,
                            'duration': duration
                        }
                        
                        claims.append(claim)
                    except ValueError:
                        continue
        
        return claims
    
    def update_text_claims_display(self):
        self.text_claims_display.config(state='normal')
        self.text_claims_display.delete("1.0", tk.END)
        
        songs = {}
        for claim in self.claims:
            if claim['source'] == 'Text Input':
                song = claim['song']
                if song not in songs:
                    songs[song] = []
                songs[song].append(claim)
        
        for song_name, song_claims in songs.items():
            time_ranges = []
            for claim in sorted(song_claims, key=lambda x: x['start']):
                time_ranges.append(f"{self.format_time(claim['start'])} — {self.format_time(claim['end'])}")
            
            display_line = f"{song_name}: {' | '.join(time_ranges)}\n\n"
            self.text_claims_display.insert(tk.END, display_line)
        
        self.text_claims_display.config(state='disabled')
        
        text_claims_count = len([c for c in self.claims if c['source'] == 'Text Input'])
        self.img_count.set(f"{text_claims_count} claims từ text")
    
    def clear_text_input(self):
        self.text_input.delete("1.0", tk.END)
    
    def clear_all_text_claims(self):
        if not any(c['source'] == 'Text Input' for c in self.claims):
            messagebox.showinfo("Thông báo", "Chưa có claim nào từ text")
            return
        
        confirm = messagebox.askyesno("Xác nhận", "Xóa tất cả claims từ text?")
        if confirm:
            self.claims = [c for c in self.claims if c['source'] != 'Text Input']
            self.update_text_claims_display()
            messagebox.showinfo("Thành công", "Đã xóa tất cả claims từ text")
    
    def setup_review_tab(self):
        info_frame = ttk.LabelFrame(self.review_tab, text="Hướng Dẫn", padding="10")
        info_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        info_text = ("Claims được đánh dấu 'Cần Review' khi:\n"
                    "• OCR confidence < 50% (rất thấp)\n"
                    "• Timestamp có vấn đề (duration quá dài/ngắn bất thường)\n"
                    "• Không tìm được file nào match trong tracklist\n"
                    "Các claims khác đã được tự động chấp nhận.")
        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).pack()
        
        review_frame = ttk.LabelFrame(self.review_tab, text="Claims Cần Review", padding="10")
        review_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        columns = ('claim_id', 'song', 'time_range', 'confidence', 'reason', 'matched_files')
        self.review_tree = ttk.Treeview(review_frame, columns=columns, show='headings', height=15)
        
        self.review_tree.heading('claim_id', text='ID')
        self.review_tree.heading('song', text='Tên Bài Hát')
        self.review_tree.heading('time_range', text='Khoảng Thời Gian')
        self.review_tree.heading('confidence', text='Confidence')
        self.review_tree.heading('reason', text='Lý Do')
        self.review_tree.heading('matched_files', text='Files Có Thể Match')
        
        self.review_tree.column('claim_id', width=50)
        self.review_tree.column('song', width=250)
        self.review_tree.column('time_range', width=150)
        self.review_tree.column('confidence', width=100)
        self.review_tree.column('reason', width=200)
        self.review_tree.column('matched_files', width=250)
        
        self.review_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        scrollbar = ttk.Scrollbar(review_frame, orient=tk.VERTICAL, command=self.review_tree.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.review_tree.configure(yscrollcommand=scrollbar.set)
        
        action_frame = ttk.Frame(review_frame)
        action_frame.grid(row=1, column=0, pady=10)
        
        ttk.Button(action_frame, text="✅ Chấp Nhận", command=self.accept_claim).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="❌ Loại Bỏ", command=self.reject_claim).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="✏️ Chỉnh Sửa", command=self.edit_claim).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="✅ Chấp Nhận Tất Cả", command=self.accept_all_claims).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="🔄 Xử Lý Lại", command=self.reprocess_claims).pack(side=tk.LEFT, padx=5)
        
        self.review_tab.columnconfigure(0, weight=1)
        self.review_tab.rowconfigure(1, weight=1)
        review_frame.columnconfigure(0, weight=1)
        review_frame.rowconfigure(0, weight=1)
    
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
                    f"Thời lượng: {self.format_time(self.tracklist[-1]['end'])}"
                )
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể tải file!\n\n{str(e)}")
    
    def load_images(self):
        filepaths = filedialog.askopenfilenames(
            title="Chọn ảnh claim",
            filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")]
        )
        if filepaths:
            for filepath in filepaths:
                self.extract_claims_from_image(filepath)
            self.remove_duplicate_claims()
            self.update_image_count()
            messagebox.showinfo("Thành công", f"Đã tải {len(filepaths)} ảnh từ file")
    
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
            self.update_image_count()
            self.update_review_tab()
            messagebox.showinfo("Thành công", "Đã xóa tất cả ảnh")
    
    def update_image_count(self):
        if self.input_mode.get() == "image":
            unique_sources = len(set(c.get('source', '') for c in self.claims if c['source'] != 'Text Input'))
            self.img_count.set(f"{unique_sources} ảnh - {len([c for c in self.claims if c['source'] != 'Text Input'])} claim")
        else:
            text_claims_count = len([c for c in self.claims if c['source'] == 'Text Input'])
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
            methods = [self.preprocess_method_1, self.preprocess_method_2, self.preprocess_method_3]
            all_claims = []
            
            for method in methods:
                img_processed = method(img)
                claims = self.ocr_extract_claims(img_processed, source_name)
                all_claims.extend(claims)
            
            self.merge_and_add_claims(all_claims)
        except Exception as e:
            print(f"Error: {e}")
    
    def preprocess_method_1(self, img):
        img_gray = img.convert('L')
        img_contrast = ImageEnhance.Contrast(img_gray).enhance(2.5)
        img_sharp = ImageEnhance.Sharpness(img_contrast).enhance(2.0)
        return img_sharp
    
    def preprocess_method_2(self, img):
        img_gray = img.convert('L')
        img_contrast = ImageEnhance.Contrast(img_gray).enhance(1.8)
        img_bright = ImageEnhance.Brightness(img_contrast).enhance(1.2)
        return img_bright
    
    def preprocess_method_3(self, img):
        img_gray = img.convert('L')
        img_edge = img_gray.filter(ImageFilter.EDGE_ENHANCE_MORE)
        img_contrast = ImageEnhance.Contrast(img_edge).enhance(2.0)
        return img_contrast
    
    def ocr_extract_claims(self, img_processed, source_name):
        claims = []
        
        try:
            ocr_data = pytesseract.image_to_data(img_processed, lang='vie+eng+spa', 
                                                output_type=pytesseract.Output.DICT)
            text = pytesseract.image_to_string(img_processed, lang='vie+eng+spa')
            
            lines = text.split('\n')
            song_name = "Unknown"
            song_confidence = 0
            
            for i, line in enumerate(lines[:15]):
                clean_line = line.strip()
                if len(clean_line) > 5 and not clean_line.startswith('Nội dung'):
                    song_name = clean_line
                    if i < len(ocr_data['text']):
                        song_confidence = int(ocr_data['conf'][i]) if ocr_data['conf'][i] != -1 else 0
                    break
            
            timestamp_patterns = [
                r'(\d{1,2}):(\d{2}):(\d{2})\s*[-—–]\s*(\d{1,2}):(\d{2}):(\d{2})',
                r'(\d{1,2}):(\d{2}):(\d{2})\s+[-—–]\s+(\d{1,2}):(\d{2}):(\d{2})',
                r'(\d{1,2}):(\d{2}):(\d{2})[-—–](\d{1,2}):(\d{2}):(\d{2})',
            ]
            
            matches = []
            for pattern in timestamp_patterns:
                matches.extend(re.findall(pattern, text))
            
            for match in matches:
                try:
                    start_h, start_m, start_s, end_h, end_m, end_s = map(int, match)
                    start_seconds = start_h * 3600 + start_m * 60 + start_s
                    end_seconds = end_h * 3600 + end_m * 60 + end_s
                    
                    if start_seconds >= end_seconds:
                        continue
                    
                    duration = end_seconds - start_seconds
                    if duration < 1 or duration > 14400:
                        continue
                    
                    timestamp_str = f"{start_h}:{start_m:02d}:{start_s:02d}"
                    confidence = self.estimate_confidence(timestamp_str, ocr_data)
                    
                    claim = {
                        'song': song_name,
                        'start': start_seconds,
                        'end': end_seconds,
                        'source': source_name,
                        'confidence': confidence,
                        'song_confidence': song_confidence,
                        'duration': duration
                    }
                    
                    claims.append(claim)
                except:
                    continue
        except Exception as e:
            print(f"OCR error: {e}")
        
        return claims
    
    def merge_and_add_claims(self, all_claims):
        if not all_claims:
            return
        
        sorted_claims = sorted(all_claims, key=lambda x: x['start'])
        merged = []
        
        for claim in sorted_claims:
            is_similar = False
            for existing in merged:
                if (abs(claim['start'] - existing['start']) <= 3 and
                    abs(claim['end'] - existing['end']) <= 3 and
                    claim['source'] == existing['source']):
                    if claim['confidence'] > existing['confidence']:
                        merged.remove(existing)
                        merged.append(claim)
                    is_similar = True
                    break
            
            if not is_similar:
                merged.append(claim)
        
        self.claims.extend(merged)
    
    def estimate_confidence(self, timestamp_str, ocr_data):
        confidences = []
        for i, text in enumerate(ocr_data['text']):
            if timestamp_str[:5] in text:
                conf = int(ocr_data['conf'][i])
                if conf != -1:
                    confidences.append(conf)
        return sum(confidences) / len(confidences) if confidences else 60
    
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
    
    def validate_claims_smart(self):
        if not self.tracklist or not self.claims:
            return
        
        max_tracklist_time = max(track['end'] for track in self.tracklist)
        valid_claims = []
        self.ambiguous_claims = []
        self.auto_accepted_claims = []
        
        for claim in self.claims:
            if claim['start'] > max_tracklist_time + 600:
                continue
            
            if claim['end'] > max_tracklist_time + 600:
                claim['end'] = min(claim['end'], max_tracklist_time + 300)
            
            is_ambiguous = False
            ambiguous_reasons = []
            
            if claim['confidence'] < 50:
                is_ambiguous = True
                ambiguous_reasons.append(f"Very low OCR confidence: {claim['confidence']:.1f}%")
            
            duration = claim['end'] - claim['start']
            if duration < 10 or duration > 3600:
                is_ambiguous = True
                ambiguous_reasons.append(f"Unusual duration: {duration}s")
            
            has_match = False
            for track in self.tracklist:
                if self.check_claim_overlap(track['start'], track['end'], 
                                          claim['start'], claim['end']):
                    has_match = True
                    break
            
            if not has_match:
                is_ambiguous = True
                ambiguous_reasons.append("No matching file in tracklist")
            
            if is_ambiguous:
                claim['ambiguous_reason'] = '; '.join(ambiguous_reasons)
                self.ambiguous_claims.append(claim)
            else:
                self.auto_accepted_claims.append(claim)
            
            valid_claims.append(claim)
        
        self.claims = valid_claims
        self.update_review_tab()
    
    def update_review_tab(self):
        for item in self.review_tree.get_children():
            self.review_tree.delete(item)
        
        for idx, claim in enumerate(self.ambiguous_claims, 1):
            time_range = f"{self.format_time(claim['start'])} → {self.format_time(claim['end'])}"
            confidence = f"{claim['confidence']:.1f}%"
            reason = claim.get('ambiguous_reason', 'Unknown')
            
            matched_files_str = "Không tìm thấy"
            potential_matches = []
            for track in self.tracklist:
                if abs(track['start'] - claim['start']) < 300 or abs(track['end'] - claim['end']) < 300:
                    potential_matches.append(track['filename'])
            
            if potential_matches:
                matched_files_str = potential_matches[0][:40]
            
            self.review_tree.insert('', 'end', values=(
                idx, claim['song'][:35], time_range, confidence, reason, matched_files_str
            ))
        
        self.notebook.tab(1, text=f"Review Claims ({len(self.ambiguous_claims)})")
    
    def parse_time(self, time_str):
        parts = time_str.split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    
    def format_time(self, seconds):
        return str(timedelta(seconds=seconds))
    
    def check_claim_overlap(self, track_start, track_end, claim_start, claim_end):
        tolerance = 10
        start_in_range = (claim_start >= track_start - tolerance and 
                         claim_start <= track_end + tolerance)
        end_in_range = (claim_end >= track_start - tolerance and 
                       claim_end <= track_end + tolerance)
        return start_in_range and end_in_range
    
    def process_claims(self):
        if not self.tracklist:
            messagebox.showerror("Lỗi", "Vui lòng tải file TXT trước!")
            return
        
        if not self.claims:
            messagebox.showerror("Lỗi", "Vui lòng tải ảnh claim hoặc nhập text claim!")
            return
        
        self.validate_claims_smart()
        
        if not self.claims:
            messagebox.showwarning("Cảnh báo", "Không có claim hợp lệ!")
            return
        
        if self.ambiguous_claims:
            response = messagebox.askquestion(
                "Kết Quả Validate",
                f"✅ Đã tự động chấp nhận: {len(self.auto_accepted_claims)} claims\n"
                f"⚠️ Cần review: {len(self.ambiguous_claims)} claims\n\n"
                f"Xem review tab?"
            )
            if response == 'yes':
                self.notebook.select(1)
                return
        
        self.results = []
        claimed_tracks = []
        
        for claim in self.claims:
            for track in self.tracklist:
                if self.check_claim_overlap(track['start'], track['end'], 
                                          claim['start'], claim['end']):
                    claimed_tracks.append({'track': track, 'claim': claim})
        
        self.display_results(claimed_tracks)
    
    def get_base_song_name(self, filename):
        name = filename.replace('.wav', '')
        match = re.match(r'(\d+- [^(]+)', name)
        if match:
            return match.group(1).strip()
        return name
    
    def display_results(self, claimed_tracks):
        self.results_text.delete(1.0, tk.END)
        
        header = "="*140 + "\n"
        header += "DANH SÁCH FILE WAV BỊ CLAIM - KẾT QUẢ KIỂM TRA (v3.0)\n"
        header += "="*140 + "\n\n"
        self.results_text.insert(tk.END, header)
        
        songs = {}
        for item in claimed_tracks:
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
                source_icon = "📝" if claim['source'] == 'Text Input' else "📷"
                
                result = f"Claim #{idx} {status} {source_icon}:\n"
                result += f"  ⚠️ FILE BỊ CLAIM: {track['filename']}\n"
                result += f"  📍 Thời gian file: {self.format_time(track['start'])} → {self.format_time(track['end'])}\n"
                result += f"  🎯 Claim phát hiện: {self.format_time(claim['start'])} → {self.format_time(claim['end'])}\n"
                result += f"  📷 Nguồn: {claim['source']}\n"
                
                conf_icon = "✅" if claim['confidence'] >= 70 else "⚠️"
                result += f"  {conf_icon} Confidence: {claim['confidence']:.1f}%\n"
                
                file_duration = max(1, track['end'] - track['start'])
                claim_duration = max(0, claim['end'] - claim['start'])
                claim_percent = (claim_duration / file_duration * 100) if file_duration > 0 else 0
                
                result += f"  📊 Tỷ lệ claim: {claim_percent:.1f}% thời lượng file\n"
                result += f"  ✅ KHỚP: Claim nằm trong khoảng file\n\n"
                
                self.results_text.insert(tk.END, result)
                total_claims += 1
        
        unique_filenames_tracklist = set(track['filename'] for track in self.tracklist)
        unique_claimed = set(claimed_filenames.keys())
        not_claimed_filenames = unique_filenames_tracklist - unique_claimed
        
        text_claims = len([c for c in self.claims if c['source'] == 'Text Input'])
        image_claims = len([c for c in self.claims if c['source'] != 'Text Input'])
        
        summary = f"\n{'='*140}\n"
        summary += f"TỔNG KẾT\n"
        summary += f"{'='*140}\n"
        summary += f"✓ Tổng file trong tracklist: {len(unique_filenames_tracklist)}\n"
        summary += f"✓ Tổng claims phát hiện: {len(self.claims)}\n"
        summary += f"✅ Claims tự động chấp nhận: {len(self.auto_accepted_claims)}\n"
        summary += f"⚠️ Claims cần review: {len(self.ambiguous_claims)}\n"
        summary += f"📝 Claims từ text: {text_claims}\n"
        summary += f"📷 Claims từ ảnh: {image_claims}\n"
        summary += f"⚠️ Tổng lần bị claim: {total_claims}\n"
        summary += f"⚠️ File UNIQUE bị claim: {len(unique_claimed)}\n"
        summary += f"✅ File KHÔNG bị claim: {len(not_claimed_filenames)}\n"
        summary += f"📊 Tỷ lệ bị claim: {len(unique_claimed)}/{len(unique_filenames_tracklist)} "
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
        self.results = claimed_tracks
    
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
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )
        
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                    f.write("File,Start,End,Claim_Start,Claim_End,Source,Song,Confidence,Percent,Status,Input_Method\n")
                    
                    for item in self.results:
                        track = item['track']
                        claim = item['claim']
                        
                        file_duration = max(1, track['end'] - track['start'])
                        claim_duration = max(0, claim['end'] - claim['start'])
                        claim_percent = (claim_duration / file_duration * 100) if file_duration > 0 else 0
                        
                        status = "AUTO" if claim in self.auto_accepted_claims else "REVIEW"
                        input_method = "Text" if claim['source'] == 'Text Input' else "Image"
                        
                        f.write(f'"{track["filename"]}",')
                        f.write(f'"{self.format_time(track["start"])}",')
                        f.write(f'"{self.format_time(track["end"])}",')
                        f.write(f'"{self.format_time(claim["start"])}",')
                        f.write(f'"{self.format_time(claim["end"])}",')
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
                f.write("BÁO CÁO CHI TIẾT - v3.0\n")
                f.write("="*140 + "\n\n")
                
                f.write("1. CLAIMS TỰ ĐỘNG CHẤP NHẬN\n")
                f.write("-"*140 + "\n\n")
                
                for idx, claim in enumerate(self.auto_accepted_claims, 1):
                    method = "📝 Text" if claim['source'] == 'Text Input' else "📷 Image"
                    f.write(f"#{idx} ({method}):\n")
                    f.write(f"  Bài: {claim['song']}\n")
                    f.write(f"  Time: {self.format_time(claim['start'])} → {self.format_time(claim['end'])}\n")
                    f.write(f"  Confidence: {claim['confidence']:.1f}%\n\n")
                
                if self.ambiguous_claims:
                    f.write("\n2. CLAIMS CẦN REVIEW\n")
                    f.write("-"*140 + "\n\n")
                    
                    for idx, claim in enumerate(self.ambiguous_claims, 1):
                        method = "📝 Text" if claim['source'] == 'Text Input' else "📷 Image"
                        f.write(f"#{idx} ({method}):\n")
                        f.write(f"  Bài: {claim['song']}\n")
                        f.write(f"  Time: {self.format_time(claim['start'])} → {self.format_time(claim['end'])}\n")
                        f.write(f"  Lý do: {claim.get('ambiguous_reason', 'Unknown')}\n\n")
                
                text_claims = len([c for c in self.claims if c['source'] == 'Text Input'])
                image_claims = len([c for c in self.claims if c['source'] != 'Text Input'])
                
                f.write("\n3. THỐNG KÊ\n")
                f.write(f"Tổng: {len(self.claims)}\n")
                f.write(f"Auto: {len(self.auto_accepted_claims)}\n")
                f.write(f"Review: {len(self.ambiguous_claims)}\n")
                f.write(f"Text: {text_claims}\n")
                f.write(f"Image: {image_claims}\n")
                
            messagebox.showinfo("Thành công", f"Đã xuất: {filepath}")
    
    def accept_claim(self):
        selection = self.review_tree.selection()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Chọn claim trước!")
            return
        
        item = self.review_tree.item(selection[0])
        claim_id = int(item['values'][0]) - 1
        
        if claim_id < len(self.ambiguous_claims):
            claim = self.ambiguous_claims[claim_id]
            self.auto_accepted_claims.append(claim)
            self.ambiguous_claims.remove(claim)
            self.update_review_tab()
            messagebox.showinfo("OK", "Đã chấp nhận")
    
    def reject_claim(self):
        selection = self.review_tree.selection()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Chọn claim trước!")
            return
        
        item = self.review_tree.item(selection[0])
        claim_id = int(item['values'][0]) - 1
        
        if claim_id < len(self.ambiguous_claims):
            claim = self.ambiguous_claims[claim_id]
            self.ambiguous_claims.remove(claim)
            if claim in self.claims:
                self.claims.remove(claim)
            self.update_review_tab()
            messagebox.showinfo("OK", "Đã loại bỏ")
    
    def edit_claim(self):
        selection = self.review_tree.selection()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Chọn claim!")
            return
        
        item = self.review_tree.item(selection[0])
        claim_id = int(item['values'][0]) - 1
        
        if claim_id < len(self.ambiguous_claims):
            claim = self.ambiguous_claims[claim_id]
            
            edit_window = tk.Toplevel(self.root)
            edit_window.title("Chỉnh Sửa")
            edit_window.geometry("500x250")
            
            ttk.Label(edit_window, text="Bài hát:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
            song_var = tk.StringVar(value=claim['song'])
            ttk.Entry(edit_window, textvariable=song_var, width=50).grid(row=0, column=1, padx=10)
            
            ttk.Label(edit_window, text="Start (s):").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
            start_var = tk.IntVar(value=claim['start'])
            ttk.Entry(edit_window, textvariable=start_var, width=50).grid(row=1, column=1, padx=10)
            
            ttk.Label(edit_window, text="End (s):").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
            end_var = tk.IntVar(value=claim['end'])
            ttk.Entry(edit_window, textvariable=end_var, width=50).grid(row=2, column=1, padx=10)
            
            def save():
                claim['song'] = song_var.get()
                claim['start'] = start_var.get()
                claim['end'] = end_var.get()
                self.update_review_tab()
                edit_window.destroy()
                messagebox.showinfo("OK", "Đã cập nhật")
            
            ttk.Button(edit_window, text="Lưu", command=save).grid(row=3, column=0, columnspan=2, pady=15)
    
    def accept_all_claims(self):
        if not self.ambiguous_claims:
            messagebox.showinfo("Thông báo", "Không có claim nào")
            return
        
        confirm = messagebox.askyesno("Xác nhận", f"Chấp nhận {len(self.ambiguous_claims)} claims?")
        if confirm:
            self.auto_accepted_claims.extend(self.ambiguous_claims)
            self.ambiguous_claims = []
            self.update_review_tab()
            messagebox.showinfo("OK", "Đã chấp nhận tất cả")
    
    def reprocess_claims(self):
        if not self.claims:
            messagebox.showwarning("Cảnh báo", "Không có claims")
            return
        
        self.ambiguous_claims = []
        self.notebook.select(0)
        self.process_claims()

def main():
    root = tk.Tk()
    app = ClaimCheckerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()