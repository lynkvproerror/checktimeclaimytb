import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import re
from datetime import timedelta
from pathlib import Path
import pytesseract
from PIL import Image, ImageGrab, ImageEnhance
import os
import io

class ClaimCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Claim Checker - Kiểm Tra File WAV Bị Claim")
        self.root.geometry("1200x800")
        
        # Configure Tesseract path for Windows
        if os.name == 'nt':  # Windows
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
        
        self.setup_ui()
        self.setup_paste_handler()
    
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Title
        title_label = ttk.Label(main_frame, text="YOUTUBE CLAIM CHECKER", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, columnspan=3, pady=10)
        
        # File input section
        input_frame = ttk.LabelFrame(main_frame, text="1. Chọn File", padding="10")
        input_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # TXT file
        ttk.Label(input_frame, text="File TXT (Tracklist):").grid(row=0, column=0, sticky=tk.W)
        self.txt_path = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.txt_path, width=60).grid(row=0, column=1, padx=5)
        ttk.Button(input_frame, text="Chọn TXT", command=self.load_txt).grid(row=0, column=2)
        
        # Image files
        ttk.Label(input_frame, text="Ảnh Claim (nhiều file):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.img_count = tk.StringVar(value="0 ảnh")
        ttk.Label(input_frame, textvariable=self.img_count).grid(row=1, column=1, sticky=tk.W)
        
        img_btn_frame = ttk.Frame(input_frame)
        img_btn_frame.grid(row=1, column=2)
        ttk.Button(img_btn_frame, text="📁 Chọn File", command=self.load_images).pack(side=tk.LEFT, padx=2)
        ttk.Button(img_btn_frame, text="📋 Paste (Ctrl+V)", command=self.paste_image).pack(side=tk.LEFT, padx=2)
        ttk.Button(img_btn_frame, text="🗑️ Xóa Tất Cả", command=self.clear_images).pack(side=tk.LEFT, padx=2)
        
        # Process button
        ttk.Button(input_frame, text="🔍 KIỂM TRA CLAIM", 
                  command=self.process_claims, style='Accent.TButton').grid(row=2, column=0, columnspan=3, pady=10)
        
        # Results section
        results_frame = ttk.LabelFrame(main_frame, text="2. Kết Quả Kiểm Tra", padding="10")
        results_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Results text area
        self.results_text = scrolledtext.ScrolledText(results_frame, width=140, height=30, 
                                                      font=('Consolas', 10))
        self.results_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Export buttons
        export_frame = ttk.Frame(results_frame)
        export_frame.grid(row=1, column=0, pady=5)
        ttk.Button(export_frame, text="💾 Xuất TXT", command=self.export_results).pack(side=tk.LEFT, padx=2)
        ttk.Button(export_frame, text="📊 Xuất CSV", command=self.export_csv).pack(side=tk.LEFT, padx=2)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
    
    def setup_paste_handler(self):
        """Setup keyboard shortcut for paste"""
        self.root.bind('<Control-v>', lambda e: self.paste_image())
        self.root.bind('<Control-V>', lambda e: self.paste_image())
    
    def load_txt(self):
        """Load tracklist from TXT file"""
        filepath = filedialog.askopenfilename(
            title="Chọn file TXT",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filepath:
            self.txt_path.set(filepath)
            self.parse_tracklist(filepath)
            messagebox.showinfo("Thành công", f"Đã tải {len(self.tracklist)} bài hát từ tracklist")
    
    def load_images(self):
        """Load multiple claim images from files"""
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
        """Paste image from clipboard - supports multiple sources"""
        try:
            # Try to get image from clipboard
            img = ImageGrab.grabclipboard()
            
            # Handle different clipboard content types
            if img is None:
                # Try alternative method for file paths in clipboard
                try:
                    import win32clipboard
                    from io import BytesIO
                    
                    win32clipboard.OpenClipboard()
                    try:
                        # Check if clipboard contains file paths
                        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_HDROP):
                            files = win32clipboard.GetClipboardData(win32clipboard.CF_HDROP)
                            if files and len(files) > 0:
                                filepath = files[0]
                                if filepath.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                                    img = Image.open(filepath)
                    finally:
                        win32clipboard.CloseClipboard()
                except:
                    pass
            
            if img is None:
                messagebox.showwarning(
                    "Clipboard Trống", 
                    "Không tìm thấy ảnh trong clipboard!\n\n"
                    "Cách copy ảnh:\n"
                    "• Từ Chrome/Web: Click phải → Copy Image\n"
                    "• Screenshot: Win + Shift + S\n"
                    "• From File: Click phải ảnh → Copy\n\n"
                    "Sau đó nhấn Ctrl+V hoặc nút Paste trong tool."
                )
                return
            
            # Handle list of images (from some clipboard managers)
            if isinstance(img, list):
                if len(img) > 0:
                    img = img[0]
                else:
                    messagebox.showerror("Lỗi", "Clipboard chứa list rỗng!")
                    return
            
            # Convert to PIL Image if needed
            if not isinstance(img, Image.Image):
                try:
                    # Try to convert
                    if hasattr(img, 'convert'):
                        img = img.convert('RGB')
                    else:
                        messagebox.showerror("Lỗi", f"Không thể chuyển đổi dữ liệu clipboard!\nLoại dữ liệu: {type(img)}")
                        return
                except:
                    messagebox.showerror("Lỗi", "Dữ liệu clipboard không phải ảnh hợp lệ!")
                    return
            
            # Save to temporary location for processing
            self.pasted_images.append(img)
            
            # Process the pasted image
            self.extract_claims_from_pil_image(img, f"Pasted_Image_{len(self.pasted_images)}")
            
            self.remove_duplicate_claims()
            self.update_image_count()
            
            # Show success with image info
            width, height = img.size
            messagebox.showinfo(
                "Paste Thành Công", 
                f"✅ Đã paste ảnh #{len(self.pasted_images)}\n\n"
                f"Kích thước: {width}×{height}px\n"
                f"Đang xử lý OCR..."
            )
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            messagebox.showerror(
                "Lỗi Paste Ảnh", 
                f"Không thể paste ảnh từ clipboard!\n\n"
                f"Chi tiết lỗi:\n{str(e)}\n\n"
                f"Vui lòng thử:\n"
                f"1. Copy lại ảnh\n"
                f"2. Dùng nút 'Chọn File' thay thế\n"
                f"3. Lưu ảnh ra file rồi chọn file"
            )
    
    def clear_images(self):
        """Clear all loaded images"""
        if not self.claims and not self.pasted_images:
            messagebox.showinfo("Thông báo", "Chưa có ảnh nào được tải")
            return
        
        confirm = messagebox.askyesno("Xác nhận", "Xóa tất cả ảnh đã tải?")
        if confirm:
            self.claims = []
            self.pasted_images = []
            self.update_image_count()
            messagebox.showinfo("Thành công", "Đã xóa tất cả ảnh")
    
    def update_image_count(self):
        """Update image count display"""
        unique_sources = len(set(c.get('source', '') for c in self.claims))
        self.img_count.set(f"{unique_sources} ảnh - {len(self.claims)} claim")
    
    def parse_tracklist(self, filepath):
        """Parse tracklist TXT file"""
        self.tracklist = []
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract track entries using regex
        pattern = r'│\s+(\d{2}:\d{2}:\d{2})\s+\|\s+(\d{2}:\d{2}:\d{2})\s+\|\s+(.+?)\.wav'
        matches = re.findall(pattern, content)
        
        for start, end, filename in matches:
            self.tracklist.append({
                'start': self.parse_time(start),
                'end': self.parse_time(end),
                'filename': filename.strip() + '.wav'
            })
    
    def extract_claims_from_image(self, filepath):
        """Extract claim timestamps from image file using OCR"""
        try:
            img = Image.open(filepath)
            source_name = Path(filepath).name
            self.extract_claims_from_pil_image(img, source_name)
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
    
    def extract_claims_from_pil_image(self, img, source_name):
        """Extract claim timestamps from PIL Image object using OCR with preprocessing"""
        try:
            # Preprocessing for better OCR
            img_enhanced = img.convert('L')  # Grayscale
            img_enhanced = ImageEnhance.Contrast(img_enhanced).enhance(2)  # Increase contrast
            
            # Use pytesseract to extract text with multiple languages
            text = pytesseract.image_to_string(img_enhanced, lang='vie+eng+spa')
            
            # Extract song name (first line that looks like a title)
            lines = text.split('\n')
            song_name = "Unknown"
            for line in lines[:10]:
                clean_line = line.strip()
                if len(clean_line) > 5 and not clean_line.startswith('Nội dung'):
                    song_name = clean_line
                    break
            
            # Extract timestamps (format: MM:SS or H:MM:SS or HH:MM:SS)
            timestamp_pattern = r'(\d{1,2}):(\d{2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2}):(\d{2})'
            matches = re.findall(timestamp_pattern, text)
            
            for match in matches:
                start_h, start_m, start_s, end_h, end_m, end_s = map(int, match)
                start_seconds = start_h * 3600 + start_m * 60 + start_s
                end_seconds = end_h * 3600 + end_m * 60 + end_s
                
                # ✅ VALIDATE: Start phải < End
                if start_seconds >= end_seconds:
                    print(f"⚠️ SKIP invalid claim: {self.format_time(start_seconds)} → {self.format_time(end_seconds)} (start >= end)")
                    continue
                
                # ✅ VALIDATE: Duration hợp lý (1s - 30 phút)
                duration = end_seconds - start_seconds
                if duration < 1 or duration > 1800:
                    print(f"⚠️ SKIP invalid duration: {duration}s")
                    continue
                
                self.claims.append({
                    'song': song_name,
                    'start': start_seconds,
                    'end': end_seconds,
                    'source': source_name
                })
                
        except Exception as e:
            print(f"Error processing image: {e}")
    
    def remove_duplicate_claims(self):
        """Remove duplicate claims based on timestamps with tolerance"""
        if not self.claims:
            return
        
        unique_claims = []
        
        # Sort claims by start time
        sorted_claims = sorted(self.claims, key=lambda x: x['start'])
        
        for claim in sorted_claims:
            # Check if this claim overlaps significantly with any existing unique claim
            is_duplicate = False
            
            for existing in unique_claims:
                # Calculate overlap
                overlap_start = max(claim['start'], existing['start'])
                overlap_end = min(claim['end'], existing['end'])
                overlap_duration = max(0, overlap_end - overlap_start)
                
                claim_duration = claim['end'] - claim['start']
                existing_duration = existing['end'] - existing['start']
                
                # If overlap > 80% of either claim, consider duplicate
                overlap_ratio_claim = overlap_duration / claim_duration if claim_duration > 0 else 0
                overlap_ratio_existing = overlap_duration / existing_duration if existing_duration > 0 else 0
                
                if overlap_ratio_claim > 0.8 or overlap_ratio_existing > 0.8:
                    is_duplicate = True
                    print(f"🔄 Merged duplicate: {self.format_time(claim['start'])}-{self.format_time(claim['end'])}")
                    break
            
            if not is_duplicate:
                unique_claims.append(claim)
        
        removed_count = len(self.claims) - len(unique_claims)
        if removed_count > 0:
            print(f"✅ Removed {removed_count} duplicate/overlapping claims")
        
        self.claims = unique_claims
    
    def validate_claims_against_tracklist(self):
        """Validate that claims make sense with tracklist duration"""
        if not self.tracklist or not self.claims:
            return
        
        # Get max time from tracklist
        max_tracklist_time = max(track['end'] for track in self.tracklist)
        
        valid_claims = []
        for claim in self.claims:
            # Check if claim is within reasonable range of tracklist
            if claim['start'] > max_tracklist_time + 300:  # 5 minutes tolerance
                print(f"⚠️ SKIP claim outside tracklist range: {self.format_time(claim['start'])}")
                continue
            
            if claim['end'] > max_tracklist_time + 300:
                print(f"⚠️ Truncate claim end time to match tracklist")
                claim['end'] = min(claim['end'], max_tracklist_time)
            
            valid_claims.append(claim)
        
        removed_count = len(self.claims) - len(valid_claims)
        if removed_count > 0:
            print(f"✅ Removed {removed_count} claims outside valid range")
        
        self.claims = valid_claims
    
    def parse_time(self, time_str):
        """Convert HH:MM:SS to seconds"""
        parts = time_str.split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    
    def format_time(self, seconds):
        """Convert seconds to HH:MM:SS"""
        return str(timedelta(seconds=seconds))
    
    def check_claim_overlap(self, track_start, track_end, claim_start, claim_end):
        """Check if claim overlaps with track"""
        # Claim must be completely within track time range
        return claim_start >= track_start and claim_end <= track_end
    
    def process_claims(self):
        """Process and match claims with tracklist"""
        if not self.tracklist:
            messagebox.showerror("Lỗi", "Vui lòng tải file TXT trước!")
            return
        
        if not self.claims:
            messagebox.showerror("Lỗi", "Vui lòng tải ảnh claim trước!")
            return
        
        # ✅ VALIDATE claims against tracklist
        self.validate_claims_against_tracklist()
        
        if not self.claims:
            messagebox.showwarning("Cảnh báo", "Không có claim hợp lệ sau khi validate!")
            return
        
        self.results = []
        claimed_tracks = []
        
        # Check each claim
        for claim in self.claims:
            for track in self.tracklist:
                if self.check_claim_overlap(track['start'], track['end'], 
                                          claim['start'], claim['end']):
                    claimed_tracks.append({
                        'track': track,
                        'claim': claim
                    })
        
        # Display results
        self.display_results(claimed_tracks)
    
    def get_base_song_name(self, filename):
        """Extract base song name from filename"""
        # Remove .wav extension
        name = filename.replace('.wav', '')
        
        # Extract pattern like "01- Song Name" before (Cover)
        match = re.match(r'(\d+- [^(]+)', name)
        if match:
            return match.group(1).strip()
        
        return name
    
    def display_results(self, claimed_tracks):
        """Display check results with improved formatting"""
        self.results_text.delete(1.0, tk.END)
        
        # Header
        header = "="*120 + "\n"
        header += "DANH SÁCH FILE WAV BỊ CLAIM - KẾT QUẢ KIỂM TRA\n"
        header += "="*120 + "\n\n"
        self.results_text.insert(tk.END, header)
        
        # Group by song
        songs = {}
        for item in claimed_tracks:
            song = item['claim']['song']
            if song not in songs:
                songs[song] = []
            songs[song].append(item)
        
        # Display each song group
        total_claims = 0
        claimed_filenames = {}  # filename -> count
        
        for song_name, items in songs.items():
            self.results_text.insert(tk.END, f"\n{'='*120}\n")
            self.results_text.insert(tk.END, f"BÀI HÁT: {song_name}\n")
            self.results_text.insert(tk.END, f"{'='*120}\n\n")
            
            for idx, item in enumerate(items, 1):
                track = item['track']
                claim = item['claim']
                
                # Count claims per file
                if track['filename'] not in claimed_filenames:
                    claimed_filenames[track['filename']] = 0
                claimed_filenames[track['filename']] += 1
                
                result = f"Claim #{idx}:\n"
                result += f"  ⚠️ FILE BỊ CLAIM: {track['filename']}\n"
                result += f"  📍 Thời gian file: {self.format_time(track['start'])} → {self.format_time(track['end'])}\n"
                result += f"  🎯 Claim phát hiện: {self.format_time(claim['start'])} → {self.format_time(claim['end'])}\n"
                result += f"  📷 Nguồn: {claim['source']}\n"
                
                # Calculate claim percentage
                file_duration = max(1, track['end'] - track['start'])  # Avoid division by zero
                claim_duration = claim['end'] - claim['start']
                if claim_duration < 0:
                    claim_duration = 0
                claim_percent = (claim_duration / file_duration * 100) if file_duration > 0 else 0
                if claim_percent < 0 or claim_percent > 100:
                    result += f"  ⚠️ WARNING: Bất thường - claim % = {claim_percent:.1f}%\n"
                    result += f"  ✅ KHỔ̀P: Claim nằm hoàn toàn trong khoảng file\n\n"
                else:
                    result += f"  📊 Tỷ lệ claim: {claim_percent:.1f}% thời lượng file\n"
                    result += f"  ✅ KHỚP: Claim nằm hoàn toàn trong khoảng file\n\n"
                
                self.results_text.insert(tk.END, result)
                total_claims += 1
        
        # Get unique files in tracklist (handle duplicates across loops)
        unique_filenames_tracklist = set(track['filename'] for track in self.tracklist)
        unique_claimed = set(claimed_filenames.keys())
        not_claimed_filenames = unique_filenames_tracklist - unique_claimed
        
        # Summary statistics
        summary = f"\n{'='*120}\n"
        summary += f"TỔNG KẾT\n"
        summary += f"{'='*120}\n"
        summary += f"✓ Tổng số file UNIQUE trong tracklist: {len(unique_filenames_tracklist)}\n"
        summary += f"✓ Tổng số claim phát hiện: {len(self.claims)}\n"
        summary += f"⚠️ Tổng số lần bị claim: {total_claims}\n"
        summary += f"⚠️ Số file UNIQUE bị claim: {len(unique_claimed)}\n"
        summary += f"✅ Số file KHÔNG bị claim: {len(not_claimed_filenames)}\n"
        summary += f"📊 Tỷ lệ bị claim: {len(unique_claimed)}/{len(unique_filenames_tracklist)} "
        summary += f"({len(unique_claimed)/len(unique_filenames_tracklist)*100:.1f}%)\n"
        summary += f"{'='*120}\n\n"
        
        # List of claimed files (grouped by base song name)
        summary += f"{'='*120}\n"
        summary += f"⚠️ DANH SÁCH FILE BỊ CLAIM ({len(unique_claimed)} file)\n"
        summary += f"{'='*120}\n"
        
        # Group claimed files by base song name
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
        
        summary += f"\n{'='*120}\n"
        summary += f"✅ DANH SÁCH FILE KHÔNG BỊ CLAIM ({len(not_claimed_filenames)} file)\n"
        summary += f"{'='*120}\n"
        
        # Group not claimed files by song name
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
        
        summary += f"\n{'='*120}\n"
        
        self.results_text.insert(tk.END, summary)
        
        # Store for export
        self.results = claimed_tracks
    
    def export_results(self):
        """Export results to TXT file with UTF-8 encoding"""
        if not self.results:
            messagebox.showwarning("Cảnh báo", "Chưa có kết quả để xuất!")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filepath:
            content = self.results_text.get(1.0, tk.END)
            # Use UTF-8 with BOM for better compatibility
            with open(filepath, 'w', encoding='utf-8-sig') as f:
                f.write(content)
            messagebox.showinfo("Thành công", f"Đã xuất kết quả ra file:\n{filepath}")
    
    def export_csv(self):
        """Export results to CSV file"""
        if not self.results:
            messagebox.showwarning("Cảnh báo", "Chưa có kết quả để xuất!")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                    # Write header
                    f.write("Tên File,Thời Gian Bắt Đầu,Thời Gian Kết Thúc,Claim Bắt Đầu,Claim Kết Thúc,Nguồn Ảnh,Bài Hát\n")
                    
                    # Write data
                    for item in self.results:
                        track = item['track']
                        claim = item['claim']
                        
                        f.write(f'"{track["filename"]}",')
                        f.write(f'"{self.format_time(track["start"])}",')
                        f.write(f'"{self.format_time(track["end"])}",')
                        f.write(f'"{self.format_time(claim["start"])}",')
                        f.write(f'"{self.format_time(claim["end"])}",')
                        f.write(f'"{claim["source"]}",')
                        f.write(f'"{claim["song"]}"\n')
                
                messagebox.showinfo("Thành công", f"Đã xuất CSV ra file:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể xuất CSV:\n{str(e)}")

def main():
    root = tk.Tk()
    app = ClaimCheckerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
