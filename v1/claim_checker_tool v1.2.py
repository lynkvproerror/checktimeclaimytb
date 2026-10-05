import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import re
from datetime import timedelta
from pathlib import Path
import pytesseract
from PIL import Image, ImageGrab
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
        self.pasted_images = []  # Store pasted images
        
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
        
        # Export button
        ttk.Button(results_frame, text="💾 Xuất Kết Quả", 
                  command=self.export_results).grid(row=1, column=0, pady=5)
        
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
            self.update_image_count()
            messagebox.showinfo("Thành công", f"Đã tải {len(filepaths)} ảnh từ file")
    
    def paste_image(self):
        """Paste image from clipboard"""
        try:
            # Get image from clipboard
            img = ImageGrab.grabclipboard()
            
            if img is None:
                messagebox.showwarning("Cảnh báo", "Clipboard không có ảnh!\n\nHãy copy ảnh (Ctrl+C) trước khi paste.")
                return
            
            if not isinstance(img, Image.Image):
                messagebox.showerror("Lỗi", "Dữ liệu clipboard không phải ảnh hợp lệ!")
                return
            
            # Save to temporary location for processing
            self.pasted_images.append(img)
            
            # Process the pasted image
            self.extract_claims_from_pil_image(img, f"Pasted_Image_{len(self.pasted_images)}")
            
            self.update_image_count()
            messagebox.showinfo("Thành công", f"Đã paste ảnh #{len(self.pasted_images)}")
            
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể paste ảnh:\n{str(e)}")
    
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
        total_images = len(self.pasted_images) + len([c for c in self.claims if 'source' in c])
        self.img_count.set(f"{total_images} ảnh - {len(self.claims)} claim")
    
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
        """Extract claim timestamps from PIL Image object using OCR"""
        try:
            # Use pytesseract to extract text
            text = pytesseract.image_to_string(img, lang='vie+eng')
            
            # Extract song name (first line that looks like a title)
            lines = text.split('\n')
            song_name = "Unknown"
            for line in lines[:10]:
                if len(line.strip()) > 5 and not line.strip().startswith('Nội dung'):
                    song_name = line.strip()
                    break
            
            # Extract timestamps (format: MM:SS or H:MM:SS or HH:MM:SS)
            timestamp_pattern = r'(\d{1,2}):(\d{2}):(\d{2})\s*[—-]\s*(\d{1,2}):(\d{2}):(\d{2})'
            matches = re.findall(timestamp_pattern, text)
            
            for match in matches:
                start_h, start_m, start_s, end_h, end_m, end_s = map(int, match)
                start_seconds = start_h * 3600 + start_m * 60 + start_s
                end_seconds = end_h * 3600 + end_m * 60 + end_s
                
                self.claims.append({
                    'song': song_name,
                    'start': start_seconds,
                    'end': end_seconds,
                    'source': source_name
                })
        except Exception as e:
            print(f"Error processing image: {e}")
    
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
    
    def display_results(self, claimed_tracks):
        """Display check results"""
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
        claimed_filenames = set()
        
        for song_name, items in songs.items():
            self.results_text.insert(tk.END, f"\n{'='*120}\n")
            self.results_text.insert(tk.END, f"BÀI HÁT: {song_name}\n")
            self.results_text.insert(tk.END, f"{'='*120}\n\n")
            
            for idx, item in enumerate(items, 1):
                track = item['track']
                claim = item['claim']
                
                result = f"Claim #{idx}:\n"
                result += f"  ⚠️ FILE BỊ CLAIM: {track['filename']}\n"
                result += f"  📍 Thời gian file: {self.format_time(track['start'])} → {self.format_time(track['end'])}\n"
                result += f"  🎯 Claim phát hiện: {self.format_time(claim['start'])} → {self.format_time(claim['end'])}\n"
                result += f"  📷 Nguồn: {claim['source']}\n"
                result += f"  ✅ KHỚP: Claim nằm hoàn toàn trong khoảng file\n\n"
                
                self.results_text.insert(tk.END, result)
                claimed_filenames.add(track['filename'])
                total_claims += 1
        
        # Get unique claimed files and not claimed files
        all_filenames = set(track['filename'] for track in self.tracklist)
        not_claimed_filenames = all_filenames - claimed_filenames
        
        # Summary
        summary = f"\n{'='*120}\n"
        summary += f"TỔNG KẾT\n"
        summary += f"{'='*120}\n"
        summary += f"✓ Tổng số file trong tracklist: {len(self.tracklist)}\n"
        summary += f"✓ Tổng số claim phát hiện: {len(self.claims)}\n"
        summary += f"⚠️ Tổng số lần bị claim: {total_claims}\n"
        summary += f"⚠️ Số file UNIQUE bị claim: {len(claimed_filenames)}\n"
        summary += f"✅ Số file KHÔNG bị claim: {len(not_claimed_filenames)}\n"
        summary += f"📊 Tỷ lệ bị claim: {len(claimed_filenames)}/{len(all_filenames)} ({len(claimed_filenames)/len(all_filenames)*100:.1f}%)\n"
        summary += f"{'='*120}\n\n"
        
        # List of claimed files (grouped by base name)
        summary += f"{'='*120}\n"
        summary += f"⚠️ DANH SÁCH FILE BỊ CLAIM ({len(claimed_filenames)} file)\n"
        summary += f"{'='*120}\n"
        
        # Group claimed files by song name
        claimed_by_song = {}
        for filename in sorted(claimed_filenames):
            # Extract song name from filename
            base_name = filename.split(' - ')[0] if ' - ' in filename else filename.split('.')[0]
            if base_name not in claimed_by_song:
                claimed_by_song[base_name] = []
            claimed_by_song[base_name].append(filename)
        
        for song_id, files in sorted(claimed_by_song.items()):
            summary += f"\n{song_id}:\n"
            for filename in sorted(files):
                summary += f"  ⚠️ {filename}\n"
        
        summary += f"\n{'='*120}\n"
        summary += f"✅ DANH SÁCH FILE KHÔNG BỊ CLAIM ({len(not_claimed_filenames)} file)\n"
        summary += f"{'='*120}\n"
        
        # Group not claimed files by song name
        not_claimed_by_song = {}
        for filename in sorted(not_claimed_filenames):
            base_name = filename.split(' - ')[0] if ' - ' in filename else filename.split('.')[0]
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
        """Export results to file"""
        if not self.results:
            messagebox.showwarning("Cảnh báo", "Chưa có kết quả để xuất!")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filepath:
            content = self.results_text.get(1.0, tk.END)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            messagebox.showinfo("Thành công", f"Đã xuất kết quả ra file:\n{filepath}")

def main():
    root = tk.Tk()
    app = ClaimCheckerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
