# UNIFIED_PIPELINE_PARALLEL_FINAL_CLEAN_UI.py

import asyncio
import os
import threading
from pathlib import Path
from datetime import datetime, timedelta
import time
import numpy as np
import h5py
import cupy as cp
import gc
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import shutil
from nicegui import ui, app
from ultralytics import YOLO
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ──────────────────────────────────────────────────────────────
# ⚙️ CONFIGURATION
# ──────────────────────────────────────────────────────────────

H5_DIR = Path("/media/mueenlab/seismology/Worker3/jacgonzalez/Imperial_Valley")
CWT_OUTPUT_DIR = Path("/media/mueenlab/extradrive1/ahmaide/CWT_results_unified")
YOLO_OUTPUT_DIR = Path("/media/mueenlab/extradrive1/ahmaide/YOLO_results_unified")
YOLO_MODEL = Path("YOLO Algorithm/best.pt")

SAVE_NPY = False
SAVE_PNG = True
SAVE_YOLO = True

SCALES = [2, 4, 8, 16, 32]
CWT_COLORMAP = "plasma"
CWT_DPI = 150

YOLO_CONF_THRESHOLD = 0.5
YOLO_IMG_SIZE = 640
YOLO_DEVICE = "0"

BATCH_SIZE = 1

# ──────────────────────────────────────────────────────────────
# AUTO-SETUP
# ──────────────────────────────────────────────────────────────

CWT_SCALES_DIRS = {s: CWT_OUTPUT_DIR / f"sigma_{s}" for s in SCALES}
CWT_NPY_DIRS = {s: CWT_OUTPUT_DIR / "npy" / f"sigma_{s}" for s in SCALES}
YOLO_SCALES_DIRS = {s: YOLO_OUTPUT_DIR / f"sigma_{s}" for s in SCALES}

for s in SCALES:
    if SAVE_PNG:
        CWT_SCALES_DIRS[s].mkdir(parents=True, exist_ok=True)
    if SAVE_NPY:
        CWT_NPY_DIRS[s].mkdir(parents=True, exist_ok=True)
    if SAVE_YOLO:
        YOLO_SCALES_DIRS[s].mkdir(parents=True, exist_ok=True)

if not H5_DIR.exists():
    print(f"❌ ERROR: H5 directory not found: {H5_DIR}")
if not YOLO_MODEL.exists():
    print(f"⚠️  WARNING: YOLO model not found: {YOLO_MODEL}")

try:
    mempool = cp.get_default_memory_pool()
    print(f"GPU: {cp.cuda.runtime.getDeviceProperties(0)['name'].decode()}")
except Exception as e:
    print(f"GPU Error: {e}")

# ──────────────────────────────────────────────────────────────
# PIPELINE QUEUES & STATE
# ──────────────────────────────────────────────────────────────

h5_queue = Queue(maxsize=3)
cwt_queue = Queue(maxsize=3)
yolo_queue = Queue(maxsize=3)
ui_event_queue = Queue()

state = {
    "running": False,
    "elapsed": 0,
    "total_files": 0,
    "processed_files": 0,
    "current_filename": None,
    "files": [],
}

# ──────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────

def load_h5_files():
    h5_files = sorted(list(H5_DIR.glob("*.h5")))
    if not h5_files:
        print(f"No H5 files found in {H5_DIR}")
    return [{"path": str(f), "dataset": "Acoustic"} for f in h5_files]


def load_one_file(file_info):
    with h5py.File(file_info["path"], "r") as f:
        arr = f[file_info["dataset"]][()]
    return arr.T.astype(np.float32)


def save_npy_file(coeff_slice, scale, file_name):
    path = CWT_NPY_DIRS[scale] / f"{file_name}_sigma{scale}.npy"
    np.save(path, coeff_slice)


def save_png_file(coeff_slice, scale, file_name):
    mag = np.abs(coeff_slice).astype(np.float32)
    viz = np.log1p(mag)
    vmin, vmax = np.percentile(viz, (1, 99))

    fig, ax = plt.subplots(figsize=(12, 6))
    im = ax.imshow(viz, origin="lower", aspect="auto",
                   vmin=vmin, vmax=vmax, cmap=CWT_COLORMAP)
    fig.colorbar(im, ax=ax, label="log(1+|coeff|)")
    ax.set_title(f"{file_name} — σ={scale}")
    ax.set_xlabel("Time")
    ax.set_ylabel("Channel")
    fig.tight_layout()

    path = CWT_SCALES_DIRS[scale] / f"{file_name}_sigma{scale}.png"
    fig.savefig(path, dpi=CWT_DPI)
    plt.close(fig)
    del mag, viz


def cwt_2d_gpu_batch(batch_np, sigmas):
    X_gpu = cp.asarray(batch_np, dtype=cp.float32)
    
    N, H, W = X_gpu.shape
    
    F = cp.fft.rfft2(X_gpu, axes=(-2, -1))
    del X_gpu
    mempool.free_all_blocks()
    
    ky = (2 * cp.pi) * cp.fft.fftfreq(H).astype(cp.float32)
    kx = (2 * cp.pi) * cp.fft.rfftfreq(W).astype(cp.float32)
    k2 = ky[:, None] ** 2 + kx[None, :] ** 2
    
    psi_hat = cp.empty_like(k2)
    Ff = cp.empty_like(F)
    
    results = {}
    
    for s in sigmas:
        s_f = float(s)
        
        cp.multiply(-0.5 * s_f * s_f, k2, out=psi_hat)
        cp.exp(psi_hat, out=psi_hat)
        cp.multiply(k2, psi_hat, out=psi_hat)
        cp.multiply(F, psi_hat[None, :, :], out=Ff)
        
        coeff = cp.fft.irfft2(Ff, s=(H, W), axes=(-2, -1))
        cp.cuda.Stream.null.synchronize()
        
        results[s] = cp.asnumpy(coeff)
        del coeff
        mempool.free_all_blocks()
    
    del F, k2, psi_hat, Ff, ky, kx
    mempool.free_all_blocks()
    
    return results


# ──────────────────────────────────────────────────────────────
# PIPELINE WORKER THREADS
# ──────────────────────────────────────────────────────────────

def reader_thread():
    files = state["files"]
    total = len(files)
    
    for idx, file_info in enumerate(files):
        if not state["running"]:
            break
        
        filename = Path(file_info["path"]).stem
        print(f"[READER] {idx+1}/{total}: Loading {filename}...")
        
        try:
            arr = load_one_file(file_info)
            h5_queue.put((idx, filename, file_info, arr), timeout=10)
        except Exception as e:
            print(f"[ERROR] Reader failed for {filename}: {e}")
            ui_event_queue.put({"type": "error", "filename": filename, "stage": "reader"})
    
    h5_queue.put(None)
    print("[READER] All files queued")


def gpu_worker_thread():
    while state["running"]:
        batch_arrays = []
        batch_info = []
        
        for _ in range(BATCH_SIZE):
            item = h5_queue.get()
            if item is None:
                if batch_arrays:
                    batch_np = np.stack(batch_arrays)
                    cwt_results_list = cwt_2d_gpu_batch(batch_np, SCALES)
                    
                    for j, (idx, filename, file_info) in enumerate(batch_info):
                        cwt_results = {s: cwt_results_list[s][j] for s in SCALES}
                        cwt_queue.put((idx, filename, file_info, cwt_results), timeout=10)
                
                cwt_queue.put(None)
                break
            
            idx, filename, file_info, arr = item
            batch_arrays.append(arr)
            batch_info.append((idx, filename, file_info))
        
        if item is None:
            break
        
        if batch_arrays:
            print(f"[GPU] Processing batch of {len(batch_arrays)} files...")
            try:
                batch_np = np.stack(batch_arrays)
                cwt_results_list = cwt_2d_gpu_batch(batch_np, SCALES)
                
                for j, (idx, filename, file_info) in enumerate(batch_info):
                    cwt_results = {s: cwt_results_list[s][j] for s in SCALES}
                    cwt_queue.put((idx, filename, file_info, cwt_results), timeout=10)
                
            except Exception as e:
                print(f"[ERROR] GPU batch processing failed: {e}")
    
    print("[GPU] Done")


def png_saver_thread():
    npy_pool = ThreadPoolExecutor(max_workers=4)
    png_pool = ThreadPoolExecutor(max_workers=4)
    
    while state["running"]:
        item = cwt_queue.get()
        
        if item is None:
            yolo_queue.put(None)
            npy_pool.shutdown()
            png_pool.shutdown()
            break
        
        idx, filename, file_info, cwt_results = item
        
        print(f"[SAVER] Saving for {filename}...")
        try:
            npy_futures = []
            png_futures = []
            
            for s in SCALES:
                coeff = cwt_results[s]
                
                if SAVE_NPY:
                    npy_futures.append(npy_pool.submit(save_npy_file, coeff, s, filename))
                if SAVE_PNG:
                    png_futures.append(png_pool.submit(save_png_file, coeff, s, filename))
            
            for fut in npy_futures:
                fut.result()
            for fut in png_futures:
                fut.result()
            
            print(f"[SAVER] {filename} saved")
            
            ui_event_queue.put({
                "type": "cwt_complete",
                "filename": filename,
                "idx": idx,
            })
            
            yolo_queue.put((idx, filename, file_info), timeout=10)
            
        except Exception as e:
            print(f"[ERROR] Saver failed for {filename}: {e}")
            ui_event_queue.put({"type": "error", "filename": filename, "stage": "saver"})
    
    print("[SAVER] Done")


def yolo_worker_thread():
    model = YOLO(str(YOLO_MODEL))
    
    while state["running"]:
        item = yolo_queue.get()
        
        if item is None:
            break
        
        idx, filename, file_info = item
        
        print(f"[YOLO] Processing {filename}...")
        detected = False
        
        try:
            for s in SCALES:
                input_path = CWT_SCALES_DIRS[s] / f"{filename}_sigma{s}.png"
                
                if not input_path.exists():
                    print(f"[YOLO] Skipping (missing): σ={s}")
                    continue
                
                results = model.predict(
                    source=str(input_path),
                    conf=YOLO_CONF_THRESHOLD,
                    imgsz=YOLO_IMG_SIZE,
                    device=YOLO_DEVICE,
                    verbose=False
                )
                
                for result in results:
                    has_detections = len(result.boxes) > 0
                    suffix = "_Y" if has_detections else "_N"
                    
                    output_path = YOLO_SCALES_DIRS[s] / f"{filename}_sigma{s}{suffix}.png"
                    
                    shutil.copy(input_path, output_path)
                    
                    if has_detections:
                        detected = True
                        print(f"[YOLO] DETECTED at σ={s}")
                    else:
                        print(f"[YOLO] Clear at σ={s}")
            
            print(f"[YOLO] {filename} complete")
            
            ui_event_queue.put({
                "type": "yolo_complete",
                "filename": filename,
                "idx": idx,
                "detected": detected,
            })
            
            state["processed_files"] += 1
            
        except Exception as e:
            print(f"[ERROR] YOLO failed for {filename}: {e}")
            ui_event_queue.put({"type": "error", "filename": filename, "stage": "yolo"})
    
    print("[YOLO] Done")


# ──────────────────────────────────────────────────────────────
# UI CSS
# ──────────────────────────────────────────────────────────────

CUSTOM_CSS = """
<style>
    body { background-color: #0d1117 !important; }
    .top-bar {
        background: #161b22;
        border-bottom: 1px solid #30363d;
        padding: 12px 24px;
    }
    .detection-banner {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        background: linear-gradient(90deg, rgba(248, 81, 73, 0.15), rgba(248, 81, 73, 0.1));
        border-bottom: 3px solid #f85149;
        padding: 12px 24px;
        z-index: 1000;
        display: none;
        align-items: center;
        justify-content: center;
        animation: slide-down 0.3s ease-out;
    }
    .detection-banner.active { display: flex; }
    @keyframes slide-down {
        from { transform: translateY(-100%); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
    }
    .detection-banner-text {
        font-size: 24px;
        font-weight: bold;
        color: #f85149;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
        letter-spacing: 2px;
    }
    .page-overlay {
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(248, 81, 73, 0.08);
        display: none;
        z-index: 999;
        pointer-events: none;
    }
    .page-overlay.active { display: block; }
    .section-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 20px;
    }
    .image-frame {
        background: #1c2333;
        border: 2px solid #30363d;
        border-radius: 10px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        transition: all 0.3s ease;
    }
    .image-frame-center {
        border-color: #58a6ff !important;
        box-shadow: 0 0 25px rgba(88, 166, 255, 0.3);
    }
    .badge {
        background: #58a6ff;
        color: #0d1117;
        font-family: 'Consolas', monospace;
        font-size: 11px;
        font-weight: bold;
        padding: 2px 8px;
        border-radius: 6px;
        position: absolute;
        top: 6px;
        right: 6px;
        z-index: 10;
    }
    .badge-purple { background: #bc8cff; }
    .badge-green  { background: #3fb950; }
    .timer-box, .counter-box {
        background: #1c2333;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 6px 14px;
        font-family: 'Consolas', monospace;
    }
    .section-bar {
        width: 4px; height: 28px;
        border-radius: 2px;
        display: inline-block;
    }
    .arrow-down { color: #58a6ff; font-size: 22px; text-align: center; }
    .status-dot-pending    { color: #484f58; font-family: 'Consolas', monospace; font-size: 12px; }
    .status-dot-processing { color: #d29922; font-family: 'Consolas', monospace; font-size: 12px; }
    .status-dot-done       { color: #3fb950; font-family: 'Consolas', monospace; font-size: 12px; }
    .status-dot-detected   { color: #f85149; font-family: 'Consolas', monospace; font-size: 12px; font-weight: bold; }
    .status-bar {
        background: #161b22;
        border-top: 1px solid #30363d;
        padding: 8px 24px;
        font-family: 'Consolas', monospace;
        font-size: 12px;
    }
    .filename-label {
        font-size: 9px; color: #8b949e;
        font-family: 'Consolas', monospace;
        max-width: 150px; overflow: hidden;
        text-overflow: ellipsis; white-space: nowrap;
        text-align: center;
    }
    .placeholder-text { font-size: 26px; color: #484f58; }
</style>
"""


def create_ui():
    ui.html(CUSTOM_CSS)
    
    # Serve static files
    if SAVE_PNG:
        for s in SCALES:
            app.add_static_files(f"/cwt/sigma_{s}", str(CWT_SCALES_DIRS[s]))
    if SAVE_YOLO:
        for s in SCALES:
            app.add_static_files(f"/yolo/sigma_{s}", str(YOLO_SCALES_DIRS[s]))
    
    detection_banner = ui.element("div").classes("detection-banner")
    with detection_banner:
        ui.html('<div class="detection-banner-text">DETECTION FOUND</div>')
    
    page_overlay = ui.element("div").classes("page-overlay")
    
    # Top bar
    with ui.row().classes("top-bar w-full items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.label("CWT x YOLO").style(
                "font-size: 22px; font-weight: bold; color: #e6edf3;"
            )
            ui.label("Real-Time Processing Pipeline").style(
                "font-size: 13px; color: #8b949e; padding-top: 4px;"
            )
        
        with ui.row().classes("items-center gap-3"):
            with ui.row().classes("timer-box items-center gap-2"):
                ui.label("TIME").style("font-size: 11px; color: #8b949e;")
                timer_label = ui.label("00:00:00").style(
                    "font-size: 16px; font-weight: bold; color: #58a6ff;"
                )
            
            with ui.row().classes("counter-box items-center gap-2"):
                ui.label("FILE").style("font-size: 11px; color: #8b949e;")
                counter_label = ui.label("0 / 0").style(
                    "font-size: 16px; font-weight: bold; color: #e6edf3;"
                )
            
            start_btn = ui.button("Start", on_click=lambda: toggle_run()).style(
                "background-color: #3fb950; color: #0d1117; font-weight: bold; "
                "border-radius: 6px; padding: 6px 16px; font-size: 12px;"
            )
            
            ui.button("Reset", on_click=lambda: reset_all()).style(
                "background-color: #1c2333; color: #8b949e; font-weight: bold; "
                "border: 1px solid #30363d; border-radius: 6px; "
                "padding: 6px 16px; font-size: 12px;"
            )
    
    # Main content
    with ui.column().classes("w-full").style("padding: 20px 24px; gap: 8px;"):
        
        # SECTION 1: CURRENT FILE (SINGLE IMAGE)
        with ui.column().classes("section-card w-full"):
            with ui.row().classes("items-center gap-3"):
                ui.html('<div class="section-bar" style="background:#58a6ff;"></div>')
                ui.label("Current File (σ=32)").style(
                    "font-size: 14px; font-weight: bold; color: #e6edf3;"
                )
            
            with ui.row().classes("w-full justify-center items-center gap-3").style(
                "padding-top: 12px;"
            ):
                carousel_container = ui.element("div").classes("image-frame").style(
                    "width: 400px; height: 300px;"
                )
                with carousel_container:
                    carousel_placeholder = ui.label("Image").classes("placeholder-text")
                    carousel_img = ui.image("").style(
                        "max-width:100%; max-height:100%; object-fit:contain; display:none;"
                    )
            
            carousel_name = ui.label("Waiting...").classes("filename-label").style(
                "margin-top: 8px;"
            )
        
        ui.label("▼").classes("arrow-down").style("padding: 2px 0;")
        
        # SECTION 2: CWT SCALES
        with ui.column().classes("section-card w-full"):
            with ui.row().classes("items-center gap-3"):
                ui.html('<div class="section-bar" style="background:#bc8cff;"></div>')
                ui.label("CWT Multi-Scale Decomposition").style(
                    "font-size: 14px; font-weight: bold; color: #e6edf3;"
                )
            
            scale_name_label = ui.label("").style(
                "font-family: Consolas, monospace; font-size: 11px; "
                "color: #58a6ff; padding-left: 26px; padding-top: 4px;"
            )
            
            with ui.row().classes("w-full justify-center items-start gap-3").style(
                "padding-top: 12px;"
            ):
                scale_items = []
                for s in SCALES:
                    with ui.column().classes("items-center gap-2"):
                        container = ui.element("div").classes("image-frame").style(
                            "width: 200px; height: 150px; position: relative;"
                        )
                        with container:
                            ui.html(f'<span class="badge badge-purple">σ={s}</span>')
                            placeholder = ui.label("Image").classes("placeholder-text")
                            img = ui.image("").style(
                                "max-width:100%; max-height:100%; "
                                "object-fit:contain; display:none;"
                            )
                        dot = ui.label("pending").classes("status-dot-pending").style(
                            "font-size: 10px;"
                        )
                        scale_items.append({
                            "container": container,
                            "img": img,
                            "placeholder": placeholder,
                            "dot": dot,
                            "scale": s,
                        })
        
        ui.label("▼").classes("arrow-down").style("padding: 2px 0;")
        
        # SECTION 3: YOLO RESULTS
        with ui.column().classes("section-card w-full"):
            with ui.row().classes("items-center gap-3"):
                ui.html('<div class="section-bar" style="background:#3fb950;"></div>')
                ui.label("YOLO Detection Results").style(
                    "font-size: 14px; font-weight: bold; color: #e6edf3;"
                )
            
            with ui.row().classes("w-full justify-center items-start gap-3").style(
                "padding-top: 12px;"
            ):
                result_items = []
                for s in SCALES:
                    with ui.column().classes("items-center gap-2"):
                        container = ui.element("div").classes("image-frame").style(
                            "width: 200px; height: 150px; position: relative;"
                        )
                        with container:
                            ui.html(f'<span class="badge badge-green">σ={s}</span>')
                            placeholder = ui.label("Image").classes("placeholder-text")
                            img = ui.image("").style(
                                "max-width:100%; max-height:100%; "
                                "object-fit:contain; display:none;"
                            )
                        det = ui.label("pending").classes("status-dot-pending").style(
                            "font-size: 10px;"
                        )
                        result_items.append({
                            "container": container,
                            "img": img,
                            "placeholder": placeholder,
                            "det": det,
                            "scale": s,
                        })
    
    # Status bar
    progress = ui.linear_progress(value=0).style("height: 4px; margin: 0;").props("color=#58a6ff")
    
    with ui.row().classes("status-bar w-full items-center justify-between"):
        status_label = ui.label("Ready").style("color: #3fb950;")
        progress_text = ui.label("0 / 0 files").style("color: #8b949e;")
    
    # ──────────────────────────────────────────────────────────────
    # UI HELPERS
    # ──────────────────────────────────────────────────────────────
    
    def show_image(item, src):
        item["placeholder"].style("display: none;")
        item["img"].set_source(src)
        item["img"].style("display: block;")
    
    def hide_image(item):
        item["placeholder"].style("display: block;")
        item["img"].set_source("")
        item["img"].style("display: none;")
    
    async def process_file_events():
        while state["running"]:
            try:
                event = ui_event_queue.get(timeout=0.5)
            except:
                await asyncio.sleep(0.1)
                continue
            
            filename = event.get("filename")
            event_type = event.get("type")
            
            if event_type == "cwt_complete":
                # Update carousel
                sigma32_path = CWT_SCALES_DIRS[32] / f"{filename}_sigma32.png"
                if sigma32_path.exists():
                    show_image({"placeholder": carousel_placeholder, "img": carousel_img}, 
                              f"/cwt/sigma_32/{filename}_sigma32.png")
                    carousel_name.text = filename
                
                # Update scales
                scale_name_label.text = filename
                for item in scale_items:
                    s = item["scale"]
                    png_path = CWT_SCALES_DIRS[s] / f"{filename}_sigma{s}.png"
                    if png_path.exists():
                        show_image(item, f"/cwt/sigma_{s}/{filename}_sigma{s}.png")
                        item["dot"].text = "ready"
                        item["dot"]._classes = ["status-dot-done"]
                    else:
                        item["dot"].text = "processing"
                        item["dot"]._classes = ["status-dot-processing"]
                    item["dot"].update()
            
            elif event_type == "yolo_complete":
                detected = event.get("detected", False)
                
                for item in result_items:
                    s = item["scale"]
                    yolo_y = YOLO_SCALES_DIRS[s] / f"{filename}_sigma{s}_Y.png"
                    yolo_n = YOLO_SCALES_DIRS[s] / f"{filename}_sigma{s}_N.png"
                    
                    if yolo_y.exists():
                        show_image(item, f"/yolo/sigma_{s}/{filename}_sigma{s}_Y.png")
                        item["det"].text = "● detected"
                        item["det"]._classes = ["status-dot-detected"]
                    elif yolo_n.exists():
                        show_image(item, f"/yolo/sigma_{s}/{filename}_sigma{s}_N.png")
                        item["det"].text = "● clear"
                        item["det"]._classes = ["status-dot-done"]
                    else:
                        hide_image(item)
                        item["det"].text = "pending"
                        item["det"]._classes = ["status-dot-processing"]
                    item["det"].update()
                
                # Show detection banner
                if detected:
                    detection_banner.add_class("active")
                    page_overlay.add_class("active")
                    await asyncio.sleep(3)
                    detection_banner.remove_class("active")
                    page_overlay.remove_class("active")
                
                # Update progress
                counter_label.text = f"{state['processed_files']} / {state['total_files']}"
                progress.value = state['processed_files'] / state['total_files'] if state['total_files'] > 0 else 0
                progress_text.text = f"{state['processed_files']} / {state['total_files']} files processed"
    
    async def toggle_run():
        if not state["running"]:
            state["running"] = True
            start_btn.text = "Running"
            start_btn.style("background-color: #d29922;")
            status_label.text = "Processing..."
            status_label.style("color: #d29922;")
            
            state["files"] = load_h5_files()
            state["total_files"] = len(state["files"])
            state["processed_files"] = 0
            counter_label.text = f"0 / {state['total_files']}"
            
            threading.Thread(target=reader_thread, daemon=True).start()
            threading.Thread(target=gpu_worker_thread, daemon=True).start()
            threading.Thread(target=png_saver_thread, daemon=True).start()
            threading.Thread(target=yolo_worker_thread, daemon=True).start()
            
            asyncio.create_task(process_file_events())
            asyncio.create_task(run_timer())
        else:
            state["running"] = False
            start_btn.text = "Resume"
            start_btn.style("background-color: #3fb950;")
            status_label.text = "Paused"
            status_label.style("color: #d29922;")
    
    def reset_all():
        state["running"] = False
        state["elapsed"] = 0
        state["processed_files"] = 0
        
        start_btn.text = "Start"
        start_btn.style("background-color: #3fb950;")
        status_label.text = "Ready"
        status_label.style("color: #3fb950;")
        timer_label.text = "00:00:00"
        counter_label.text = "0 / 0"
        progress.value = 0
        progress_text.text = "0 / 0 files"
        
        hide_image({"placeholder": carousel_placeholder, "img": carousel_img})
        carousel_name.text = "Waiting..."
        scale_name_label.text = ""
        
        for item in scale_items:
            hide_image(item)
            item["dot"].text = "pending"
            item["dot"]._classes = ["status-dot-pending"]
            item["dot"].update()
        
        for item in result_items:
            hide_image(item)
            item["det"].text = "pending"
            item["det"]._classes = ["status-dot-pending"]
            item["det"].update()
        
        detection_banner.remove_class("active")
        page_overlay.remove_class("active")
    
    async def run_timer():
        while state["running"]:
            await asyncio.sleep(1)
            if state["running"]:
                state["elapsed"] += 1
                h = state["elapsed"] // 3600
                m = (state["elapsed"] % 3600) // 60
                s = state["elapsed"] % 60
                timer_label.text = f"{h:02d}:{m:02d}:{s:02d}"


create_ui()

ui.run(
    title="CWT x YOLO",
    port=8080,
    reload=False,
    dark=True,
)