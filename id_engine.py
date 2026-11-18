import os
import io
import re
import json
import zipfile
import tempfile
import urllib.request
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

# ─── Constants ──────────────────────────────────────────────────────────────
# DATA_DIR: where the ONNX model lives (repo directory, read-only on cloud)
DATA_DIR   = os.path.join(os.getcwd(), "id_data")
YUNET_PATH = os.path.join(DATA_DIR, "face_detection_yunet_2023mar.onnx")
YUNET_URL  = "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx"

# OUTPUT_DIR: writable location for saved photos.
# On Streamlit Cloud the repo is mounted read-only, so fall back to /tmp.
def _resolve_output_dir() -> str:
    candidate = os.path.join(DATA_DIR, "passport_photos")
    try:
        os.makedirs(candidate, exist_ok=True)
        # Quick write-test
        _probe = os.path.join(candidate, ".probe")
        with open(_probe, "w") as _f:
            _f.write("ok")
        os.remove(_probe)
        return candidate
    except (OSError, PermissionError):
        fallback = os.path.join(tempfile.gettempdir(), "passportcut", "passport_photos")
        os.makedirs(fallback, exist_ok=True)
        return fallback

OUTPUT_DIR = _resolve_output_dir()

# ─── Dimension Presets (label: (width_mm, height_mm)) ───────────────────────
DIMENSION_PRESETS = {
    "22 × 27.5 mm  (Indian Passport – small)": (22,   27.5),
    "35 × 45 mm    (Standard Passport / UK / EU)": (35,   45),
    "51 × 51 mm    (US Visa / 2×2 inch)":       (51,   51),
    "40 × 60 mm    (Indian Passport – large)":   (40,   60),
    "30 × 40 mm    (Schengen Visa)":             (30,   40),
    "35 × 35 mm    (Australian Passport)":       (35,   35),
    "Custom":                                    None,
}

# Default passport photo spec: 35mm x 45mm at 200 dpi
PASSPORT_W  = 276   # 35mm @ 200 dpi
PASSPORT_H  = 354   # 45mm @ 200 dpi
DEFAULT_DPI = 200

_detector   = None


# ─── Init ────────────────────────────────────────────────────────────────────
def init():
    # DATA_DIR may be read-only on cloud; OUTPUT_DIR is already resolved above.
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
        # backend_id / target_id removed: OpenCV 5.x's new graph engine does
        # not support them for FaceDetectorYN and emits a WARN that breaks
        # Streamlit Cloud logs.  Omitting the args lets OpenCV pick defaults.
        _detector = cv2.FaceDetectorYN.create(
            model=YUNET_PATH,
            config="",
            input_size=(320, 320),
            score_threshold=0.5,
            nms_threshold=0.3,
            top_k=5000,
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


# ─── Dimension helper ────────────────────────────────────────────────────────
def mm_to_px(mm: float, dpi: int = DEFAULT_DPI) -> int:
    """Convert millimetres to pixels at the given DPI."""
    return max(1, round(mm / 25.4 * dpi))


def resize_to_dimensions(
    img: Image.Image,
    width_mm: float,
    height_mm: float,
    dpi: int = DEFAULT_DPI,
    bg_color: tuple = (255, 255, 255),
) -> Image.Image:
    """
    Resize *img* to exactly (width_mm x height_mm) at *dpi*.
    The image is letterbox-fitted (aspect ratio preserved) onto a
    solid-colour canvas of the target size.
    """
    target_w = mm_to_px(width_mm, dpi)
    target_h = mm_to_px(height_mm, dpi)

    orig_w, orig_h = img.size
    if orig_w == 0 or orig_h == 0:
        return Image.new("RGB", (target_w, target_h), bg_color)

    scale  = min(target_w / orig_w, target_h / orig_h)
    new_w  = int(orig_w * scale)
    new_h  = int(orig_h * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (target_w, target_h), bg_color)
    paste_x = (target_w - new_w) // 2
    paste_y = (target_h - new_h) // 2
    canvas.paste(resized, (paste_x, paste_y))
    return canvas


# ─── Passport photo creation ──────────────────────────────────────────────────
def make_passport_photo(
    face_pil: Image.Image,
    white_bg: bool = True,
    width_mm: float = 35,
    height_mm: float = 45,
    dpi: int = DEFAULT_DPI,
) -> Image.Image:
    """
    Resize the expanded shoulder-crop to fill the given canvas size.
    The crop already contains hair + neck + shoulders from detect_faces().
    We letterbox-fit it to the canvas so nothing is cropped out.
    """
    bg_color = (255, 255, 255) if white_bg else (173, 216, 230)
    return resize_to_dimensions(face_pil, width_mm, height_mm, dpi, bg_color)


def make_raw_photo(
    original_pil: Image.Image,
    width_mm: float,
    height_mm: float,
    dpi: int = DEFAULT_DPI,
    bg_color: tuple = (255, 255, 255),
) -> Image.Image:
    """
    Resize the *original* (un-cropped) image to the requested dimensions
    without any face-detection cropping applied.
    """
    return resize_to_dimensions(original_pil, width_mm, height_mm, dpi, bg_color)


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
