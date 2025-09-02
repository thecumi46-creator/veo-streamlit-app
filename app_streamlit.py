import streamlit as st
import os, json, time, tempfile, platform, subprocess
from pathlib import Path

# Optional: import google genai if available
try:
    import google.genai as genai
    from google.genai import types
except Exception:
    genai = None
    types = None

st.set_page_config(page_title="Veo Streamlit Suite", layout="wide")

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

API_FILE = Path("apikey.json")

# ---------- Helpers ----------
def save_api_key(key: str):
    with open(API_FILE, "w") as f:
        json.dump({"api_key": key}, f)

def load_api_key():
    if API_FILE.exists():
        try:
            return json.load(open(API_FILE)).get("api_key","")
        except Exception:
            return ""
    return ""

def init_client(key: str = None):
    if genai is None:
        st.error("google-genai SDK belum terpasang in this environment. Install 'google-genai' in requirements.")
        return None
    k = key or load_api_key()
    if not k:
        st.error("API key belum disetel. Masukkan API key di sidebar.")
        return None
    return genai.Client(api_key=k)

def save_bytes_to_file(bts: bytes, filename: Path):
    with open(filename, "wb") as f:
        f.write(bts)
    return filename

def save_video_from_operation(client, op, out_prefix):
    saved = []
    # Strategy A: generated_videos
    try:
        gvs = getattr(op.response, "generated_videos", None) or (op.response.get("generated_videos") if isinstance(op.response, dict) else None)
        if gvs:
            for i, video_obj in enumerate(gvs):
                try:
                    if hasattr(video_obj, "video") and hasattr(video_obj.video, "save"):
                        fname = OUTPUT_DIR / f"{out_prefix}_{i+1}.mp4"
                        try:
                            client.files.download(file=video_obj.video)
                        except Exception:
                            pass
                        try:
                            video_obj.video.save(str(fname))
                            saved.append(str(fname))
                            continue
                        except Exception:
                            pass
                    raw = getattr(video_obj, "content", None) or getattr(video_obj, "data", None)
                    if raw and isinstance(raw, (bytes, bytearray)):
                        fname = OUTPUT_DIR / f"{out_prefix}_{i+1}.mp4"
                        with open(fname, "wb") as f:
                            f.write(raw)
                        saved.append(str(fname))
                        continue
                except Exception:
                    continue
    except Exception:
        pass
    # Strategy B: direct bytes
    try:
        v = getattr(op.response, "video", None) or (op.response.get("video") if isinstance(op.response, dict) else None)
        if v and isinstance(v, (bytes, bytearray)):
            fname = OUTPUT_DIR / f"{out_prefix}.mp4"
            with open(fname, "wb") as f:
                f.write(v)
            saved.append(str(fname))
            return saved
    except Exception:
        pass
    # Strategy C: recursive search
    try:
        def find_and_save(obj, prefix, counter=[1]):
            if hasattr(obj, "video") and hasattr(obj.video, "save"):
                fname = OUTPUT_DIR / f"{prefix}_{counter[0]}.mp4"
                try:
                    client.files.download(file=obj.video)
                except Exception:
                    pass
                try:
                    obj.video.save(str(fname))
                    saved.append(str(fname))
                    counter[0] += 1
                except Exception:
                    pass
            if isinstance(obj, dict):
                for k, v in obj.items():
                    find_and_save(v, prefix, counter)
            elif isinstance(obj, (list, tuple)):
                for v in obj:
                    find_and_save(v, prefix, counter)
        find_and_save(op.response, out_prefix)
    except Exception:
        pass
    return saved

def poll_and_save(client, op_name, out_prefix, progress_bar=None, status_text=None, sleep_s=3, max_steps=120):
    steps = 0
    last_percent = 0
    try:
        op = client.operations.get(op_name)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch operation: {e}")
    while True:
        done = getattr(op, "done", False)
        if done:
            if status_text: status_text.text("Finalizing...")
            saved = save_video_from_operation(client, op, out_prefix)
            return saved
        steps += 1
        # heuristic percent increase
        last_percent = min(95, last_percent + int(80 / max(1, max_steps)))
        if progress_bar:
            progress_bar.progress(last_percent)
        if status_text:
            status_text.text(f"Processing... step {steps}")
        time.sleep(sleep_s)
        try:
            op = client.operations.get(op_name)
        except Exception:
            if steps > max_steps:
                raise RuntimeError("Polling timeout")
            time.sleep(sleep_s)
            continue

# ---------- UI ----------
st.sidebar.title("Settings")
api_input = st.sidebar.text_input("Google API Key", value=load_api_key(), type="password")
if st.sidebar.button("Save API Key"):
    if not api_input.strip():
        st.sidebar.error("API key kosong")
    else:
        save_api_key(api_input.strip())
        st.sidebar.success("API key disimpan")
if st.sidebar.button("Clear API Key"):
    if API_FILE.exists(): API_FILE.unlink()
    st.sidebar.success("API key dihapus")

st.title("Veo Streamlit Suite (Web)")

client = init_client(api_input or None)

st.markdown("## Prompt → Video")
prompt = st.text_area("Masukkan prompt video:", height=120)
col1, col2 = st.columns(2)
with col1:
    if st.button("Generate Video from Prompt"):
        if client is None:
            st.error("Client belum siap. Set API key di sidebar.")
        elif not prompt.strip():
            st.error("Prompt kosong")
        else:
            with st.spinner("Submitting job..."):
                op = client.models.generate_videos(model="veo-1.5", prompt=prompt.strip(), config=types.GenerateVideosConfig(aspect_ratio="16:9"))
                (OUTPUT_DIR / "resume_prompt.json").write_text(json.dumps({"op_name": getattr(op, "name", str(op))}))
                st.success(f"Job submitted. Op: {getattr(op, 'name', str(op))}")
            # Poll
            p = st.progress(0)
            status = st.empty()
            try:
                saved = poll_and_save(client, getattr(op, "name", str(op)), "prompt", progress_bar=p, status_text=status)
                if saved:
                    st.success("Video ready:")
                    for f in saved:
                        st.video(f)
                        with open(f, "rb") as fh:
                            st.download_button("Download "+Path(f).name, fh.read(), file_name=Path(f).name)
                    # open folder locally if running locally
                    if platform.system()=="Windows":
                        os.startfile(str(OUTPUT_DIR))
                else:
                    st.info("No video file found in operation response.")
            except Exception as e:
                st.error(f"Polling failed: {e}")

with col2:
    st.markdown("### Image → Video (Upload)")
    up = st.file_uploader("Upload image", type=["png","jpg","jpeg","webp"])
    img_prompt = st.text_input("Optional prompt for image->video", value="Generate cinematic video from the provided image.")
    if st.button("Generate from Image"):
        if client is None:
            st.error("Client belum siap. Set API key in sidebar.")
        elif up is None:
            st.error("Upload gambar dulu.")
        else:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(up.name).suffix)
            tmp.write(up.read())
            tmp.flush()
            tmp.close()
            with st.spinner("Uploading image & creating job..."):
                img_file = client.files.upload(file=Path(tmp.name))
                op = client.models.generate_videos(model="veo-1.5", prompt=img_prompt.strip(), config=types.GenerateVideosConfig(aspect_ratio="16:9"), images=[img_file])
                (OUTPUT_DIR / "resume_img2vid.json").write_text(json.dumps({"op_name": getattr(op, "name", str(op))}))
                st.success(f"Job submitted. Op: {getattr(op, 'name', str(op))}")
            p = st.progress(0)
            status = st.empty()
            try:
                saved = poll_and_save(client, getattr(op, "name", str(op)), "image2video", progress_bar=p, status_text=status)
                if saved:
                    st.success("Video ready:")
                    for f in saved:
                        st.video(f)
                        with open(f, "rb") as fh:
                            st.download_button("Download "+Path(f).name, fh.read(), file_name=Path(f).name)
                    if platform.system()=="Windows":
                        os.startfile(str(OUTPUT_DIR))
                else:
                    st.info("No video file found in operation response.")
            except Exception as e:
                st.error(f"Polling failed: {e}")

st.markdown("---")
st.markdown("## Story → JSON → Video")
story = st.text_area("Masukkan ide cerita untuk JSON:", height=120)
if st.button("Create prompt.json from story"):
    if not story.strip():
        st.error("Isi ide cerita dulu.")
    else:
        out = OUTPUT_DIR / "prompt.json"
        out.write_text(json.dumps({"prompt": story.strip(), "aspect_ratio":"16:9"}, indent=2))
        st.success(f"prompt.json created at {out}")

if st.button("Generate Video from prompt.json"):
    if client is None:
        st.error("Client belum siap.")
    else:
        path = OUTPUT_DIR / "prompt.json"
        if not path.exists():
            st.error("prompt.json belum ada. Klik 'Create prompt.json from story' terlebih dahulu.")
        else:
            data = json.load(open(path))
            with st.spinner("Submitting job..."):
                op = client.models.generate_videos(model="veo-1.5", prompt=data["prompt"], config=types.GenerateVideosConfig(aspect_ratio=data.get("aspect_ratio","16:9")))
                (OUTPUT_DIR / "resume_json.json").write_text(json.dumps({"op_name": getattr(op, "name", str(op))}))
                st.success(f"Job submitted. Op: {getattr(op, 'name', str(op))}")
            p = st.progress(0); status = st.empty()
            try:
                saved = poll_and_save(client, getattr(op, "name", str(op)), "json", progress_bar=p, status_text=status)
                if saved:
                    st.success("Video ready:")
                    for f in saved:
                        st.video(f)
                        with open(f, "rb") as fh:
                            st.download_button("Download "+Path(f).name, fh.read(), file_name=Path(f).name)
                    if platform.system()=="Windows":
                        os.startfile(str(OUTPUT_DIR))
                else:
                    st.info("No video found in response.")
            except Exception as e:
                st.error(f"Polling failed: {e}")

st.markdown("---")
st.markdown("## Storyboard Generator (AI)")
idea = st.text_area("Masukkan ide cerita untuk storyboard:", height=120)
colA, colB, colC = st.columns(3)
with colA:
    style = st.selectbox("Visual style", ["cinematic","realistic","anime","noir","pixelart"])
with colB:
    genre = st.selectbox("Genre", ["action","romance","horror","comedy","drama","fantasy","sci-fi"])
with colC:
    character = st.selectbox("Character preset", ["Hero","Villain","Sidekick","Narrator"])
duration = st.number_input("Durasi per scene (detik)", min_value=3, max_value=60, value=7)
if st.button("Generate Storyboard (AI)"):
    if client is None:
        st.error("Client belum siap.")
    elif not idea.strip():
        st.error("Isi ide cerita.")
    else:
        with st.spinner("Asking text model to create storyboard..."):
            # try AI first
            try:
                resp = client.models.generate_content(
                    model="gemini-1.5-pro",
                    contents=[
                        {"role":"user","parts":[
                            "You are a storyboard generator. Output strict JSON with key 'storyboard' as list of scenes. Each scene: scene(int), description(str), duration(int), character, visual_style, genre. No extra commentary."
                        ]},
                        {"role":"user","parts":[f"Idea: {idea}\\nVisual style:{style}\\nGenre:{genre}\\nCharacter preset:{character}\\nScenes:5\\nDurationPerScene:{duration}\\nOutput: JSON only."]}
                    ],
                )
                text = getattr(resp, "text", None) or (resp.candidates[0].content.parts[0].text if getattr(resp, "candidates", None) else "")
                text = (text or "").strip()
                if text.startswith("```"):
                    text = text.strip("`")
                    if "\\n" in text:
                        text = text.split("\\n",1)[1]
                data = json.loads(text)
                out = OUTPUT_DIR / "storyboard.json"
                out.write_text(json.dumps(data, indent=2))
                st.success(f"Storyboard created: {out}")
                st.json(data)
            except Exception as e:
                # fallback simple split
                parts = [s.strip() for s in idea.replace("\\n"," ").split(".") if s.strip()][:5]
                scenes = []
                for i, p in enumerate(parts):
                    scenes.append({"scene": i+1, "description": p, "duration": duration, "character": character, "visual_style": style, "genre": genre})
                data = {"storyboard": scenes}
                out = OUTPUT_DIR / "storyboard.json"
                out.write_text(json.dumps(data, indent=2))
                st.success(f"Storyboard (fallback) created: {out}")
                st.json(data)

if st.button("Generate Video from Storyboard"):
    path = OUTPUT_DIR / "storyboard.json"
    if not path.exists():
        st.error("Belum ada storyboard.json. Generate storyboard dulu.")
    else:
        data = json.load(open(path))
        # convert to prompt
        parts = []
        for s in data.get("storyboard", []):
            parts.append(f"[Scene {s['scene']} | {s['duration']}s | {s['character']} | {s['visual_style']} | {s['genre']}] {s['description']}")
        prompt = "Create a cohesive short film following these scenes:\\n" + "\\n".join(parts)
        if client is None:
            st.error("Client belum siap.")
        else:
            with st.spinner("Submitting storyboard job..."):
                op = client.models.generate_videos(model="veo-1.5", prompt=prompt, config=types.GenerateVideosConfig(aspect_ratio="16:9"))
                (OUTPUT_DIR / "resume_storyboard.json").write_text(json.dumps({"op_name": getattr(op, "name", str(op))}))
                st.success(f"Job submitted. Op: {getattr(op, 'name', str(op))}")
            p = st.progress(0); status = st.empty()
            try:
                saved = poll_and_save(client, getattr(op, "name", str(op)), "storyboard", progress_bar=p, status_text=status)
                if saved:
                    st.success("Video ready:")
                    for f in saved:
                        st.video(f)
                        with open(f, "rb") as fh:
                            st.download_button("Download "+Path(f).name, fh.read(), file_name=Path(f).name)
                    if platform.system()=="Windows":
                        os.startfile(str(OUTPUT_DIR))
                else:
                    st.info("No video found in response.")
            except Exception as e:
                st.error(f"Polling failed: {e}")

st.markdown("---")
st.markdown("### Resume existing operation")
resume_file = st.selectbox("Pilih resume file", [str(p.name) for p in OUTPUT_DIR.glob("resume_*.json")] or [])
if resume_file and st.button("Resume & check"):
    data = json.load(open(OUTPUT_DIR / resume_file))
    op_name = data.get("op_name")
    if not op_name:
        st.error("Resume file invalid")
    else:
        if client is None:
            st.error("Client belum siap.")
        else:
            p = st.progress(0); status = st.empty()
            try:
                saved = poll_and_save(client, op_name, Path(resume_file).stem, progress_bar=p, status_text=status)
                if saved:
                    st.success("Video ready:")
                    for f in saved:
                        st.video(f)
                        with open(f, "rb") as fh:
                            st.download_button("Download "+Path(f).name, fh.read(), file_name=Path(f).name)
                    if platform.system()=="Windows":
                        os.startfile(str(OUTPUT_DIR))
                else:
                    st.info("No video found.")
            except Exception as e:
                st.error(f"Polling failed: {e}")
