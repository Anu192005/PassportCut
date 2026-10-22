import os
import io
import re
import datetime
import streamlit as st
from PIL import Image
import id_engine

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PassportCut – ID Photo Generator",
    page_icon="🪪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Init engine ─────────────────────────────────────────────────────────────
id_engine.init()

# ─── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"], .stMarkdown {
    font-family: 'Inter', sans-serif;
}

.stApp { background-color: #f0f4f8; color: #1e293b; }

section[data-testid="stSidebar"] {
    background-color: #ffffff !important;
    border-right: 1px solid #e2e8f0 !important;
}

/* Style all containers */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 20px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
    margin-bottom: 16px !important;
}

/* Passport card style */
.passport-card {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 10px;
    padding: 12px;
    text-align: center;
    margin-bottom: 12px;
}

.page-title {
    color: #0f172a;
    font-weight: 800;
    font-size: 2rem;
    letter-spacing: -0.5px;
    margin-bottom: 2px;
}

.page-subtitle {
    color: #475569;
    font-size: 0.95rem;
    margin-bottom: 22px;
}

.pill-saved {
    background: #dcfce7;
    color: #166534;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
}
.pill-pending {
    background: #fef9c3;
    color: #713f12;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
}

.stButton>button {
    background-color: #4f46e5;
    color: white;
    border: none;
    border-radius: 7px;
    font-weight: 600;
    transition: background 0.2s;
}
.stButton>button:hover {
    background-color: #4338ca;
    color: white;
}

hr { border-color: #e2e8f0; margin: 14px 0; }
</style>
""", unsafe_allow_html=True)


# ─── Session state defaults ───────────────────────────────────────────────────
def _ss(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

_ss("faces", [])           # list of dicts per detected face
_ss("bg_color", "White")
_ss("naming_mode", "Custom Name")
_ss("output_folder", id_engine.OUTPUT_DIR)  # user-chosen save folder


# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<h2 style="font-weight:800;color:#4f46e5;margin-bottom:0;">🪪 PassportCut</h2>', unsafe_allow_html=True)
    st.markdown('<p style="color:#475569;font-size:0.83rem;margin-top:0;">ID Photo Generator · OpenCV DNN</p>', unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("#### ⚙️ Output Settings")
    st.session_state["bg_color"] = st.selectbox(
        "Background Colour",
        ["White", "Light Blue", "Light Grey"],
        index=0,
        help="Passport photo background colour."
    )
    st.session_state["naming_mode"] = st.radio(
        "Naming Strategy",
        ["Custom Name", "Code Name (auto)", "Filename as Name"],
        help=(
            "Custom Name: you type the name for each face.\n"
            "Code Name: auto-generated codes like FACE_001.\n"
            "Filename as Name: uses the source filename."
        )
    )
    st.markdown("---")

    saved = [f for f in st.session_state["faces"] if f.get("saved_path")]
    pending = [f for f in st.session_state["faces"] if not f.get("saved_path")]
    st.metric("Total Faces Detected", len(st.session_state["faces"]))
    st.metric("Saved to Disk", len(saved))
    st.metric("Pending", len(pending))

    if saved:
        st.markdown("---")
        zip_bytes = id_engine.build_zip([f["saved_path"] for f in saved])
        st.download_button(
            label="📦 Download ALL as ZIP",
            data=zip_bytes,
            file_name=f"passport_photos_{datetime.date.today()}.zip",
            mime="application/zip",
            use_container_width=True,
        )

    if st.session_state["faces"]:
        st.markdown("---")
        if st.button("🗑️ Clear All & Reset", use_container_width=True):
            st.session_state["faces"] = []
            st.rerun()


# ─── Main Area ───────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">🪪 PassportCut</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Upload individual photos or an entire folder — the system detects every face, generates standard passport-sized cutouts, lets you name them, and saves them to disk.</div>', unsafe_allow_html=True)

# ─── Upload Section ───────────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("### 📁 Upload Photos")

    tab_single, tab_folder = st.tabs(["Upload Individual Files", "Upload Full Folder (multiple files)"])

    with tab_single:
        uploaded_files = st.file_uploader(
            "Choose one or more photos",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="single_uploader",
        )

    with tab_folder:
        st.info(
            "**Tip:** Use Ctrl+A inside your photos folder to select all, then drag them here. "
            "Streamlit does not support native folder pickers, but you can select all files from a folder at once."
        )
        folder_files = st.file_uploader(
            "Select all files from your folder",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="folder_uploader",
        )

    # Merge both upload sources
    all_uploaded = []
    if uploaded_files:
        all_uploaded += uploaded_files
    if folder_files:
        all_uploaded += folder_files
    # Deduplicate by name
    seen_names = set()
    deduped = []
    for f in all_uploaded:
        if f.name not in seen_names:
            seen_names.add(f.name)
            deduped.append(f)
    all_uploaded = deduped

    if all_uploaded:
        col_btn1, col_btn2 = st.columns([2, 3])
        with col_btn1:
            process_btn = st.button("🔍 Detect Faces in All Photos", use_container_width=True)

        if process_btn:
            st.session_state["faces"] = []
            bg_map = {
                "White": True,
                "Light Blue": False,
                "Light Grey": False,
            }
            with st.spinner("Running face detection on all uploaded images…"):
                code_counter = 1
                for uf in all_uploaded:
                    source_name = os.path.splitext(uf.name)[0]
                    pil_img = Image.open(uf)
                    faces = id_engine.detect_faces(pil_img)

                    for idx, face in enumerate(faces):
                        raw_crop = face["face_crop_raw"]
                        white_bg = (st.session_state["bg_color"] == "White")
                        passport = id_engine.make_passport_photo(raw_crop, white_bg=white_bg)

                        # Determine default name
                        if st.session_state["naming_mode"] == "Code Name (auto)":
                            default_name = f"FACE_{code_counter:03d}"
                        elif st.session_state["naming_mode"] == "Filename as Name":
                            suffix = f"_{idx+1}" if len(faces) > 1 else ""
                            default_name = f"{source_name}{suffix}"
                        else:
                            suffix = f"_{idx+1}" if len(faces) > 1 else ""
                            default_name = f"{source_name}{suffix}"

                        st.session_state["faces"].append({
                            "source": uf.name,
                            "source_idx": idx,
                            "confidence": face["confidence"],
                            "raw_crop": raw_crop,
                            "passport": passport,
                            "name": default_name,
                            "saved_path": None,
                        })
                        code_counter += 1

            st.success(f"✅ Detected **{len(st.session_state['faces'])}** face(s) across **{len(all_uploaded)}** image(s).")


# ─── Results Gallery ──────────────────────────────────────────────────────────
if st.session_state["faces"]:
    st.markdown("---")

    with st.container(border=True):
        st.markdown(f"### 🖼️ Detected Faces — Passport Photo Gallery")
        st.markdown(
            "Review each face below. Edit the name, then click **Save** to write it to disk. "
            "Use **Save All** to batch-save everything at once."
        )

        # ── Output Folder Picker ───────────────────────────────────────────
        st.markdown("#### 📂 Save Location")
        col_path, col_path_btn = st.columns([5, 1])
        with col_path:
            folder_input = st.text_input(
                "Output folder path",
                value=st.session_state["output_folder"],
                placeholder=r"e.g.  C:\Users\Anagha\Desktop\ID Photos",
                help=(
                    "Type or paste the full folder path where you want passport photos saved.\n"
                    "The folder will be created automatically if it does not exist."
                ),
                label_visibility="collapsed",
                key="folder_path_input",
            )
        with col_path_btn:
            if st.button("✅ Set Folder", use_container_width=True, key="set_folder_btn"):
                folder_input = folder_input.strip()
                if folder_input:
                    try:
                        os.makedirs(folder_input, exist_ok=True)
                        st.session_state["output_folder"] = folder_input
                        st.success(f"Folder set!")
                    except Exception as e:
                        st.error(f"Invalid path: {e}")
                else:
                    st.warning("Please enter a folder path first.")

        # Show the active folder
        active_folder = st.session_state["output_folder"]
        st.markdown(
            f'<p style="font-size:0.82rem;color:#475569;margin-top:-6px;">'
            f'📁 Active save folder: <code>{active_folder}</code></p>',
            unsafe_allow_html=True
        )
        st.markdown("---")

        # ── Save All Button ────────────────────────────────────────────────
        col_sa1, col_sa2, col_sa3 = st.columns([2, 2, 3])
        with col_sa1:
            save_all_btn = st.button("💾 Save ALL Passport Photos", use_container_width=True)
        with col_sa2:
            # Download saved files
            saved_paths = [f["saved_path"] for f in st.session_state["faces"] if f.get("saved_path")]
            if saved_paths:
                zip_bytes = id_engine.build_zip(saved_paths)
                st.download_button(
                    label="📦 Download Saved Photos",
                    data=zip_bytes,
                    file_name=f"passport_photos_{datetime.date.today()}.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

        if save_all_btn:
            save_folder = st.session_state["output_folder"]
            try:
                os.makedirs(save_folder, exist_ok=True)
            except Exception as e:
                st.error(f"Cannot create folder '{save_folder}': {e}")
                st.stop()
            count = 0
            for i, face_data in enumerate(st.session_state["faces"]):
                if not face_data.get("saved_path"):
                    raw_name = face_data["name"].strip() or f"FACE_{i+1:03d}"
                    safe_name = id_engine.sanitise(raw_name)
                    path = id_engine.save_passport_photo(face_data["passport"], safe_name, folder=save_folder)
                    st.session_state["faces"][i]["saved_path"] = path
                    count += 1
            if count:
                st.success(f"💾 Saved **{count}** new passport photo(s) to `{save_folder}`")
            else:
                st.info("All photos are already saved!")
            st.rerun()

        st.markdown("---")

        # ── Grid: 4 cards per row ──────────────────────────────────────────
        NUM_COLS = 4
        faces = st.session_state["faces"]
        rows = [faces[i:i+NUM_COLS] for i in range(0, len(faces), NUM_COLS)]

        for row in rows:
            cols = st.columns(NUM_COLS)
            for col_idx, (face_data, col) in enumerate(zip(row, cols)):
                global_idx = faces.index(face_data)
                with col:
                    # ── Passport photo preview ──────────────────────────
                    st.image(
                        face_data["passport"],
                        caption=f"📷 {face_data['source']} · Face {face_data['source_idx']+1}",
                        use_container_width=True,
                    )

                    # ── Confidence badge ────────────────────────────────
                    conf_pct = int(face_data["confidence"] * 100)
                    st.markdown(
                        f'<p style="text-align:center;font-size:0.78rem;color:#64748b;">Confidence: <b>{conf_pct}%</b></p>',
                        unsafe_allow_html=True
                    )

                    # ── Name input ──────────────────────────────────────
                    new_name = st.text_input(
                        "Name / ID",
                        value=face_data["name"],
                        key=f"name_{global_idx}",
                        placeholder="Enter name or code",
                        label_visibility="collapsed",
                    )
                    st.session_state["faces"][global_idx]["name"] = new_name

                    # ── Status + Save button ────────────────────────────
                    if face_data.get("saved_path"):
                        st.markdown(
                            f'<p style="text-align:center;"><span class="pill-saved">✅ Saved</span></p>',
                            unsafe_allow_html=True
                        )
                        # Still let user re-save with updated name
                        if st.button("Re-save", key=f"resave_{global_idx}", use_container_width=True):
                            safe_name = id_engine.sanitise(new_name.strip() or f"FACE_{global_idx+1:03d}")
                            sf = st.session_state["output_folder"]
                            os.makedirs(sf, exist_ok=True)
                            path = id_engine.save_passport_photo(face_data["passport"], safe_name, folder=sf)
                            st.session_state["faces"][global_idx]["saved_path"] = path
                            st.rerun()
                    else:
                        st.markdown(
                            '<p style="text-align:center;"><span class="pill-pending">⏳ Pending</span></p>',
                            unsafe_allow_html=True
                        )
                        if st.button("💾 Save", key=f"save_{global_idx}", use_container_width=True):
                            safe_name = id_engine.sanitise(new_name.strip() or f"FACE_{global_idx+1:03d}")
                            sf = st.session_state["output_folder"]
                            os.makedirs(sf, exist_ok=True)
                            path = id_engine.save_passport_photo(face_data["passport"], safe_name, folder=sf)
                            st.session_state["faces"][global_idx]["saved_path"] = path
                            st.success(f"Saved -> {os.path.basename(path)}")
                            st.rerun()

                    # ── Individual download ─────────────────────────────
                    buf = io.BytesIO()
                    face_data["passport"].save(buf, "JPEG", quality=95)
                    st.download_button(
                        label="⬇️ Download",
                        data=buf.getvalue(),
                        file_name=f"{id_engine.sanitise(new_name)}.jpg",
                        mime="image/jpeg",
                        key=f"dl_{global_idx}",
                        use_container_width=True,
                    )

    # ── Output folder path info ────────────────────────────────────────────
    st.info(f"📂 All passport photos are saved to: `{st.session_state['output_folder']}`")

else:
    # Empty state
    st.markdown("""
    <div style="text-align:center;padding:60px 20px;">
        <div style="font-size:4rem;">🪪</div>
        <h3 style="color:#0f172a;font-weight:700;">No faces detected yet</h3>
        <p style="color:#475569;">Upload photos above and click <b>Detect Faces</b> to get started.</p>
    </div>
    """, unsafe_allow_html=True)
