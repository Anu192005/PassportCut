# 🪪 PassportCut – AI Passport & ID Photo Generator

PassportCut is an AI-powered passport and ID photo generator built with Python and Streamlit. It automatically detects faces, crops them to standard passport/ID photo specifications, and generates print-ready photo sheets.

## ✨ Features

- 📷 **Automatic face detection** using YuNet (OpenCV DNN)
- ✂️ **Smart cropping** to standard passport photo sizes (35×45mm, 2×2 inch, etc.)
- 🖨️ **Print-ready sheets** with multiple copies laid out on A4/letter paper
- 🎨 **Background removal/replacement** (white background standard)
- 📐 **Multiple ID formats** supported
- 🌐 **Easy-to-use Streamlit web interface**

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- pip

### Installation

```bash
git clone https://github.com/Anu192005/PassportCut.git
cd PassportCut
pip install -r requirements.txt
```

### Run

```bash
streamlit run id_card_app.py
```

Then open your browser at `http://localhost:8501`

## 📁 Project Structure

```
PassportCut/
├── id_card_app.py          # Streamlit web application
├── id_engine.py            # Core face detection & cropping engine
├── id_data/
│   ├── face_detection_yunet_2023mar.onnx   # YuNet face detection model
│   └── passport_photos/    # Generated photos output
├── requirements.txt
└── .gitignore
```

## 🧰 Tech Stack

- [Streamlit](https://streamlit.io/) – Web UI
- [OpenCV](https://opencv.org/) – Computer Vision & Face Detection
- [Pillow](https://python-pillow.org/) – Image Processing
- [YuNet](https://github.com/ShiqiYu/libfacedetection) – Lightweight Face Detection Model

## 📄 License

MIT License © 2026 Anu192005
