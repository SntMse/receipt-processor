import os
import re
import shutil
import time
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from google.cloud import vision
import fitz  # PyMuPDF

# ==========================================
# 環境変数から設定を取得 (Docker連携)
# ==========================================
WATCH_DIR = os.getenv("WATCH_DIR", "/data/inbox")
DEST_BASE_DIR = os.getenv("DEST_BASE_DIR", "/data/db")
MANUAL_DIR = os.getenv("MANUAL_DIR", os.path.join(DEST_BASE_DIR, "Manual_Check"))

def get_image_bytes_from_pdf(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0: return None
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=150)
        return pix.tobytes("jpeg")
    except Exception as e:
        print(f"PDF変換エラー: {e}")
        return None

def extract_text_with_vision(image_content):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_content)
        response = client.document_text_detection(image=image)
        if response.error.message:
            print(f"Vision API エラー: {response.error.message}")
            return ""
        if response.full_text_annotation:
            return response.full_text_annotation.text
        return ""
    except Exception as e:
        print(f"Vision API 通信エラー: {e}")
        return ""

def extract_date_from_receipt(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    image_content = None
    
    if ext == '.pdf':
        image_content = get_image_bytes_from_pdf(file_path)
    elif ext in ['.jpg', '.jpeg', '.png']:
        with open(file_path, "rb") as f:
            image_content = f.read()
            
    if not image_content: return None

    text = extract_text_with_vision(image_content)
    if not text: return None

    pattern = r'(20\d{2})\s*[年/\-\.]\s*([01]?\d)\s*[月/\-\.]\s*([0-3]?\d)\s*[日]?'
    match = re.search(pattern, text)
    if match:
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            pass
    return None

def get_quarter(month):
    if 1 <= month <= 3: return "1Q"
    elif 4 <= month <= 6: return "2Q"
    elif 7 <= month <= 9: return "3Q"
    else: return "4Q"

class ReceiptHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory: return
            
        file_path = event.src_path
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.pdf']: return

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 新規ファイルを検知: {file_path}")
        time.sleep(3) # スキャンファイルの書き込み完了待ち

        receipt_date = extract_date_from_receipt(file_path)
        
        if receipt_date:
            year_str = receipt_date.strftime("%Y")
            quarter_str = get_quarter(receipt_date.month)
            date_str = receipt_date.strftime("%Y%m%d")
            
            target_dir = os.path.join(DEST_BASE_DIR, year_str, quarter_str)
            os.makedirs(target_dir, exist_ok=True)
            
            new_filename = f"{date_str}{ext}"
            new_file_path = os.path.join(target_dir, new_filename)
            
            counter = 1
            while os.path.exists(new_file_path):
                new_filename = f"{date_str}_{counter}{ext}"
                new_file_path = os.path.join(target_dir, new_filename)
                counter += 1
                
            shutil.move(file_path, new_file_path)
            print(f" -> 成功: 移動完了 {new_file_path}")
        else:
            os.makedirs(MANUAL_DIR, exist_ok=True)
            new_file_path = os.path.join(MANUAL_DIR, os.path.basename(file_path))
            shutil.move(file_path, new_file_path)
            print(f" -> 失敗: 日付読取不可。手動確認フォルダへ移動 {new_file_path}")

if __name__ == "__main__":
    for d in [WATCH_DIR, DEST_BASE_DIR, MANUAL_DIR]:
        os.makedirs(d, exist_ok=True)
        
    event_handler = ReceiptHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    observer.start()
    
    print(f"レシート監視を開始しました (監視フォルダ: {WATCH_DIR})")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()