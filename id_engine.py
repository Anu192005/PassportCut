import os
import io
import re
import json
import zipfile
import urllib.request
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

# ─── Constants ──────────────────────────────────────────────────────────────
DATA_DIR    = os.path.join(os.getcwd(), "id_data")
YUNET_PATH  = os.path.join(DATA_DIR, "face_detection_yunet_2023mar.onnx")
YUNET_URL   = "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx"
OUTPUT_DIR  = os.path.join(DATA_DIR, "passport_photos")

# Passport photo specification: 35mm x 45mm at 200 dpi
# 35mm  -> 35/25.4 * 200 = ~276 px   45mm -> 45/25.4 * 200 = ~354 px
PASSPORT_W  = 276
PASSPORT_H  = 354

_detector   = None


# ─── Init ────────────────────────────────────────────────────────────────────
def init():
    os.makedirs(DATA_DIR,   exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    _download_model_if_missing(YUNET_PATH, YUNET_URL, "YuNet Face Detector")


def _download_model_if_missing(path, url, name):
    if not os.path.exists(path):
        print(f"Downloading {name}…")
        opener = urllib.request.build_opener()
        opener.addheaders = [("User-agent", "Mozilla/5.0")]
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url, path)
        print(f"Saved {name} -> {path}")


def get_detector():
    global _detector
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(
            model=YUNET_PATH,
            config="",
            input_size=(320, 320),
            score_threshold=0.5,
            nms_threshold=0.3,
            top_k=5000,
            backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
            target_id=cv2.dnn.DNN_TARGET_CPU,
        )
    return _detector


# ─── Core detection ──────────────────────────────────────────────────────────
def detect_faces(pil_img: Image.Image):
    """Return list of dicts: {box, confidence, face_crop_raw}."""
    img_rgb = np.array(pil_img.convert("RGB"))
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    h, w = img_bgr.shape[:2]
    det = get_detector()
    det.setInputSize((w, h))

    ret, faces = det.detect(img_bgr)
    results = []
    if faces is None or len(faces) == 0:
        return results

    for face in faces:
        x, y, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
        conf = float(face[14])

        # ── Expand the bounding box for a proper passport framing ──────────
        # YuNet returns a tight face box (forehead to chin).
        # For a passport photo we need:
        #   • Top:    +35% of face height  → includes hair / top of head
        #   • Bottom: +110% of face height → includes neck + shoulders
        #   • Sides:  +45% of face width   → includes ears + shoulder width
        pad_top    = int(fh * 0.35)
        pad_bottom = int(fh * 1.10)
        pad_side   = int(fw * 0.45)

        x1 = max(0, x - pad_side)
        y1 = max(0, y - pad_top)
        x2 = min(w, x + fw + pad_side)
        y2 = min(h, y + fh + pad_bottom)

        raw_crop = pil_img.crop((x1, y1, x2, y2))
        results.append({
            "box": {"x": x, "y": y, "w": fw, "h": fh},
            "confidence": round(conf, 3),
            "face_crop_raw": raw_crop,
        })

    return results



# ─── Passport photo creation ──────────────────────────────────────────────────
def make_passport_photo(face_pil: Image.Image, white_bg: bool = True) -> Image.Image:
    """
    Resize the expanded shoulder-crop to fill the standard passport canvas
    (276 x 354 px at 200 dpi = 35mm x 45mm).
    The crop already contains hair + neck + shoulders from detect_faces().
    We letterbox-fit it to the canvas so nothing is cropped out.
    """
    orig_w, orig_h = face_pil.size

    # Scale to fill the full passport canvas (letterbox – fit inside)
    scale = min(PASSPORT_W / orig_w, PASSPORT_H / orig_h) if orig_w > 0 and orig_h > 0 else 1.0
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    face_resized = face_pil.resize((new_w, new_h), Image.LANCZOS)

    # Create canvas with chosen background
    bg_color = (255, 255, 255) if white_bg else (173, 216, 230)
    canvas = Image.new("RGB", (PASSPORT_W, PASSPORT_H), bg_color)

    # Centre the resized crop on the canvas
    paste_x = (PASSPORT_W - new_w) // 2
    paste_y = (PASSPORT_H - new_h) // 2

    canvas.paste(face_resized, (paste_x, paste_y))
    return canvas


# ─── Save passport photo ─────────────────────────────────────────────────────
def save_passport_photo(passport_img: Image.Image, filename: str, folder: str = None) -> str:
    """Save to folder (defaults to OUTPUT_DIR) and return the absolute path."""
    dest_dir = folder if folder else OUTPUT_DIR
    os.makedirs(dest_dir, exist_ok=True)
    if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
        filename += ".jpg"
    dest = os.path.join(dest_dir, filename)
    passport_img.save(dest, "JPEG", quality=95)
    return dest



# ─── Bulk ZIP helper ─────────────────────────────────────────────────────────
def build_zip(photo_paths: list) -> bytes:
    """Return a ZIP bytes object containing all saved passport photos."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in photo_paths:
            if os.path.exists(p):
                zf.write(p, os.path.basename(p))
    buf.seek(0)
    return buf.read()


# ─── Sanitise filename helper ────────────────────────────────────────────────
def sanitise(name: str) -> str:
    return re.sub(r"[^\w\-_\. ]", "_", name).strip().replace(" ", "_")
