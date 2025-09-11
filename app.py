# app.py (Space publik)
import os
from huggingface_hub import snapshot_download
import sys

# ---- 1) Set ENV sebelum Streamlit jalan (W A J I B) ----
# HOME yang writable (agar tidak tulis ke '/.streamlit')
os.environ.setdefault("HOME", "/home/user")
# Matikan XSRF/CORS + naikan limit upload
os.environ.setdefault("STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION", "false")
os.environ.setdefault("STREAMLIT_SERVER_ENABLE_CORS", "false")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_SERVER_MAX_UPLOAD_SIZE", "1024")

# (opsional) siapkan config.toml sebagai backup
try:
    cfg_dir = os.path.join(os.environ["HOME"], ".streamlit")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg_path = os.path.join(cfg_dir, "config.toml")
    if not os.path.exists(cfg_path):
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(
                "[server]\n"
                "enableXsrfProtection = false\n"
                "enableCORS = false\n"
                "maxUploadSize = 1024\n"
                "\n[browser]\n"
                "gatherUsageStats = false\n"
            )
except Exception:
    pass

# ---- 2) Download Space privat ----
LOCAL_DIR = snapshot_download(
    repo_id="zenefil/veo",        # <== pastikan benar
    repo_type="space",
    use_auth_token=os.getenv("HF_TOKEN"),
)

# ---- 3) Jalankan streamlit script dari Space privat ----
streamlit_script = os.path.join(LOCAL_DIR, "src", "streamlit_app.py")
if not os.path.exists(streamlit_script):
    print(f"File tidak ditemukan: {streamlit_script}")
    sys.exit(1)

os.execvp(
    "streamlit",
    [
        "streamlit",
        "run",
        streamlit_script,
        "--server.address", "0.0.0.0",
        "--server.port", os.getenv("PORT", "7860"),
    ],
)
