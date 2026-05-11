# GUI.py

from nicegui import ui, app
import asyncio
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# Constants & Paths
# ──────────────────────────────────────────────────────────────
SCALES = [2, 4, 8, 16, 32]
BASE_DIR = Path("/media/mueenlab/extradrive1/ahmaide/cwt_results_png")
YOLO_DIR = Path("/media/mueenlab/extradrive1/ahmaide/CWT_YOLO_May2026")
SCALE_DIRS = {s: BASE_DIR / f"sigma_{s}" for s in SCALES}
YOLO_DIRS = {s: YOLO_DIR / f"sigma_{s}" for s in SCALES}

TOTAL_IMAGES = 0
IMAGE_LIST = []


def discover_images():
    global TOTAL_IMAGES, IMAGE_LIST

    sigma32_dir = SCALE_DIRS[32]
    if not sigma32_dir.exists():
        print(f"ERROR: Directory not found: {sigma32_dir}")
        return

    files = sorted([
        f.name for f in sigma32_dir.iterdir()
        if f.suffix == ".png"
    ])

    for fname in files:
        base = fname.replace("_sigma32.png", "")
        IMAGE_LIST.append({
            "base_name": base,
            "filename_32": fname,
            "paths": {},
            "yolo_paths": {}
        })
        for s in SCALES:
            scale_fname = f"{base}_sigma{s}.png"
            scale_path = SCALE_DIRS[s] / scale_fname
            IMAGE_LIST[-1]["paths"][s] = scale_path
            
            # YOLO files: base_sigma{s}_Y.png or base_sigma{s}_N.png
            yolo_y_path = YOLO_DIRS[s] / f"{base}_sigma{s}_Y.png"
            yolo_n_path = YOLO_DIRS[s] / f"{base}_sigma{s}_N.png"
            
            if yolo_y_path.exists():
                IMAGE_LIST[-1]["yolo_paths"][s] = (yolo_y_path, True)  # True = Detected
            elif yolo_n_path.exists():
                IMAGE_LIST[-1]["yolo_paths"][s] = (yolo_n_path, False)  # False = Not detected
            else:
                IMAGE_LIST[-1]["yolo_paths"][s] = (None, False)

    TOTAL_IMAGES = len(IMAGE_LIST)
    print(f"Discovered {TOTAL_IMAGES} images")

    if TOTAL_IMAGES > 0:
        first = IMAGE_LIST[0]
        print(f"  First image base: {first['base_name']}")
        for s in SCALES:
            p = first["paths"][s]
            exists = "✓" if p.exists() else "✗ MISSING"
            print(f"    sigma_{s}: {p.name}  [{exists}]")


discover_images()

# ──────────────────────────────────────────────────────────────
# State
# ──────────────────────────────────────────────────────────────
state = {
    "running": False,
    "current_index": 0,
    "elapsed": 0,
}

# ──────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────
CUSTOM_CSS = """
<style>
    body { background-color: #0d1117 !important; }
    .top-bar {
        background: #161b22;
        border-bottom: 1px solid #30363d;
        padding: 12px 24px;
    }
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
    .glow-wrapper {
        background: linear-gradient(135deg, #1f6feb33, #58a6ff22);
        border-radius: 14px;
        padding: 3px;
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
    .badge-red    { background: #f85149; }
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
    .placeholder-text {
        font-size: 26px; color: #484f58;
    }
    .earthquake-alert {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(248, 81, 73, 0.95);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
        animation: pulse 0.5s ease-in-out;
    }
    .earthquake-text {
        font-size: 72px;
        font-weight: bold;
        color: white;
        text-shadow: 0 0 40px rgba(0,0,0,0.5);
        font-family: 'Segoe UI', sans-serif;
    }
    @keyframes pulse {
        0% { opacity: 0; }
        50% { opacity: 1; }
        100% { opacity: 1; }
    }
</style>
"""


def get_carousel_indices(current, total):
    """Get 3 indices centered on current for the carousel."""
    if total == 0:
        return [0, 0, 0]
    indices = []
    for offset in [-1, 0, 1]:
        idx = current + offset
        if idx < 0:
            idx = 0
        elif idx >= total:
            idx = total - 1
        indices.append(idx)
    return indices


def create_page():
    ui.html(CUSTOM_CSS)

    # Serve image directories
    for s in SCALES:
        app.add_static_files(f"/images/sigma_{s}", str(SCALE_DIRS[s]))
        app.add_static_files(f"/yolo/sigma_{s}", str(YOLO_DIRS[s]))

    # ══════════════════════════════════════════════════════════
    # EARTHQUAKE ALERT (hidden by default)
    # ══════════════════════════════════════════════════════════
    earthquake_alert = ui.element("div").classes("earthquake-alert").style(
        "display: none;"
    )
    with earthquake_alert:
        ui.html('<div class="earthquake-text">🌍 EARTHQUAKE DETECTED 🌍</div>')

    # ══════════════════════════════════════════════════════════
    # TOP BAR
    # ══════════════════════════════════════════════════════════
    with ui.row().classes("top-bar w-full items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.label("CWT × YOLO").style(
                "font-size: 22px; font-weight: bold; color: #e6edf3;"
            )
            ui.label("Multi-Scale Analysis Pipeline").style(
                "font-size: 13px; color: #8b949e; padding-top: 4px;"
            )

        with ui.row().classes("items-center gap-3"):
            with ui.row().classes("timer-box items-center gap-2"):
                ui.label("⏱").style("font-size: 14px;")
                timer_label = ui.label("00:00:00").style(
                    "font-size: 18px; font-weight: bold; color: #58a6ff;"
                )

            with ui.row().classes("counter-box items-center gap-2"):
                ui.label("IMG").style(
                    "font-size: 10px; font-weight: bold; color: #484f58;"
                )
                counter_label = ui.label(f"0000 / {TOTAL_IMAGES}").style(
                    "font-size: 14px; font-weight: bold; color: #e6edf3;"
                )

            start_btn = ui.button("▶  Start", on_click=lambda: toggle_run()).style(
                "background-color: #3fb950; color: #0d1117; font-weight: bold; "
                "border-radius: 8px; padding: 8px 20px; font-size: 13px;"
            )

            ui.button("↺  Reset", on_click=lambda: reset()).style(
                "background-color: #1c2333; color: #8b949e; font-weight: bold; "
                "border: 1px solid #30363d; border-radius: 8px; "
                "padding: 8px 16px; font-size: 13px;"
            )

    # ══════════════════════════════════════════════════════════
    # MAIN CONTENT
    # ══════════════════════════════════════════════════════════
    with ui.column().classes("w-full items-center").style(
        "padding: 20px 24px; gap: 8px;"
    ):

        # ──────────────────────────────────────────────────────
        # SECTION 1: CAROUSEL (3 images, larger)
        # ──────────────────────────────────────────────────────
        with ui.column().classes("section-card w-full"):
            with ui.row().classes("items-center gap-3"):
                ui.html('<div class="section-bar" style="background:#58a6ff;"></div>')
                with ui.column().style("gap: 2px;"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label("📂").style("font-size: 16px;")
                        ui.label("Image Carousel").style(
                            "font-size: 15px; font-weight: bold; color: #e6edf3;"
                        )
                    ui.label(
                        "Sigma-32 source images — center image is selected for multi-scale analysis"
                    ).style("font-size: 11px; color: #8b949e; padding-left: 26px;")

            with ui.row().classes("w-full justify-center items-end gap-8").style(
                "padding-top: 16px; padding-bottom: 8px;"
            ):
                carousel_items = []
                sizes = [
                    (200, 160, False),
                    (280, 220, True),   # center - larger
                    (200, 160, False),
                ]

                for i, (w, h, is_center) in enumerate(sizes):
                    with ui.column().classes("items-center gap-1"):
                        if is_center:
                            with ui.element("div").classes("glow-wrapper"):
                                container = ui.element("div").classes(
                                    "image-frame image-frame-center"
                                ).style(f"width: {w}px; height: {h}px;")
                                with container:
                                    placeholder = ui.label("🖼").classes("placeholder-text")
                                    img = ui.image("").style(
                                        "max-width:100%; max-height:100%; "
                                        "object-fit:contain; display:none;"
                                    )
                            name_lbl = ui.label("waiting...").classes("filename-label").style(
                                "max-width: 280px;"
                            )
                            ui.label("▲ SELECTED").style(
                                "font-size: 9px; font-weight: bold; color: #58a6ff; "
                                "font-family: Consolas, monospace;"
                            )
                        else:
                            container = ui.element("div").classes("image-frame").style(
                                f"width: {w}px; height: {h}px; opacity: 0.6;"
                            )
                            with container:
                                placeholder = ui.label("🖼").classes("placeholder-text")
                                img = ui.image("").style(
                                    "max-width:100%; max-height:100%; "
                                    "object-fit:contain; display:none;"
                                )
                            name_lbl = ui.label("—").classes("filename-label")

                        carousel_items.append({
                            "container": container,
                            "img": img,
                            "placeholder": placeholder,
                            "name_lbl": name_lbl,
                        })

        ui.label("▼").classes("arrow-down").style("padding: 2px 0;")

        # ──────────────────────────────────────────────────────
        # SECTION 2: CWT SCALES (larger)
        # ──────────────────────────────────────────────────────
        with ui.column().classes("section-card w-full"):
            with ui.row().classes("items-center gap-3"):
                ui.html('<div class="section-bar" style="background:#bc8cff;"></div>')
                with ui.column().style("gap: 2px;"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label("🔬").style("font-size: 16px;")
                        ui.label("CWT Multi-Scale Decomposition").style(
                            "font-size: 15px; font-weight: bold; color: #e6edf3;"
                        )
                    ui.label(
                        "Same image at all 5 CWT scales: σ=2, σ=4, σ=8, σ=16, σ=32"
                    ).style("font-size: 11px; color: #8b949e; padding-left: 26px;")

            current_name_label = ui.label("").style(
                "font-family: Consolas, monospace; font-size: 12px; "
                "color: #58a6ff; padding-left: 26px; padding-top: 4px;"
            )

            with ui.row().classes("w-full justify-center items-start gap-5").style(
                "padding-top: 12px; padding-bottom: 8px;"
            ):
                scale_items = []
                for scale in SCALES:
                    with ui.column().classes("items-center gap-1"):
                        container = ui.element("div").classes("image-frame").style(
                            "width: 200px; height: 160px; position: relative;"
                        )
                        with container:
                            ui.html(
                                f'<span class="badge badge-purple">σ={scale}</span>'
                            )
                            placeholder = ui.label("🖼").classes("placeholder-text")
                            img = ui.image("").style(
                                "max-width:100%; max-height:100%; "
                                "object-fit:contain; padding:4px; display:none;"
                            )
                        dot = ui.label("○ pending").classes("status-dot-pending")
                        scale_items.append({
                            "container": container,
                            "img": img,
                            "placeholder": placeholder,
                            "dot": dot,
                            "scale": scale,
                        })

        ui.label("▼").classes("arrow-down").style("padding: 2px 0;")

        # ──────────────────────────────────────────────────────
        # SECTION 3: YOLO RESULTS (larger, with detection indicator)
        # ──────────────────────────────────────────────────────
        with ui.column().classes("section-card w-full"):
            with ui.row().classes("items-center gap-3"):
                ui.html('<div class="section-bar" style="background:#3fb950;"></div>')
                with ui.column().style("gap: 2px;"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label("🎯").style("font-size: 16px;")
                        ui.label("YOLO Detection Results").style(
                            "font-size: 15px; font-weight: bold; color: #e6edf3;"
                        )
                    ui.label(
                        "Object detection applied to each CWT-scaled image — Red = Detected"
                    ).style("font-size: 11px; color: #8b949e; padding-left: 26px;")

            with ui.row().classes("w-full justify-center items-start gap-5").style(
                "padding-top: 16px; padding-bottom: 8px;"
            ):
                result_items = []
                for scale in SCALES:
                    with ui.column().classes("items-center gap-1"):
                        container = ui.element("div").classes("image-frame").style(
                            "width: 200px; height: 160px; position: relative;"
                        )
                        with container:
                            ui.html(
                                f'<span class="badge badge-green">σ={scale}</span>'
                            )
                            placeholder = ui.label("🖼").classes("placeholder-text")
                            img = ui.image("").style(
                                "max-width:100%; max-height:100%; "
                                "object-fit:contain; padding:4px; display:none;"
                            )
                        det = ui.label("— detections").classes("status-dot-pending")
                        result_items.append({
                            "container": container,
                            "img": img,
                            "placeholder": placeholder,
                            "det": det,
                        })

    # ══════════════════════════════════════════════════════════
    # PROGRESS BAR & STATUS
    # ══════════════════════════════════════════════════════════
    progress = ui.linear_progress(value=0, show_value=False).style(
        "height: 6px; margin: 0;"
    ).props("color=#58a6ff track-color=#161b22")

    with ui.row().classes("status-bar w-full items-center justify-between"):
        status_label = ui.label("● Ready — press Start to begin").style("color: #3fb950;")
        progress_text = ui.label(f"0 / {TOTAL_IMAGES} images processed").style(
            "color: #8b949e;"
        )

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════
    def show_image(item, src):
        item["placeholder"].style("display: none;")
        item["img"].set_source(src)
        item["img"].style(
            "max-width:100%; max-height:100%; object-fit:contain; "
            "padding:4px; display:block;"
        )

    def hide_image(item):
        item["placeholder"].style("display: block;")
        item["img"].set_source("")
        item["img"].style(
            "max-width:100%; max-height:100%; object-fit:contain; "
            "padding:4px; display:none;"
        )

    def update_carousel(center_index):
        indices = get_carousel_indices(center_index, TOTAL_IMAGES)
        for slot, idx in enumerate(indices):
            item = carousel_items[slot]
            if TOTAL_IMAGES > 0 and 0 <= idx < TOTAL_IMAGES:
                img_data = IMAGE_LIST[idx]
                fname = img_data["filename_32"]
                show_image(item, f"/images/sigma_32/{fname}")
                display_name = img_data["base_name"]
                if len(display_name) > 28:
                    display_name = display_name[:28] + "…"
                item["name_lbl"].text = display_name
            else:
                hide_image(item)
                item["name_lbl"].text = "—"

    def update_scales(image_index):
        if image_index < 0 or image_index >= TOTAL_IMAGES:
            return
        img_data = IMAGE_LIST[image_index]
        current_name_label.text = f"📎 {img_data['base_name']}"

        for item in scale_items:
            s = item["scale"]
            fname = f"{img_data['base_name']}_sigma{s}.png"
            src = f"/images/sigma_{s}/{fname}"

            if img_data["paths"][s].exists():
                show_image(item, src)
                item["dot"].text = "✓ loaded"
                item["dot"]._classes = ["status-dot-done"]
            else:
                hide_image(item)
                item["dot"].text = "✗ missing"
                item["dot"]._classes = ["status-dot-pending"]
            item["dot"].update()

    def update_yolo(image_index):
        """Load YOLO results and check for detections."""
        if image_index < 0 or image_index >= TOTAL_IMAGES:
            return
        
        img_data = IMAGE_LIST[image_index]
        earthquake_detected = False

        for i, item in enumerate(result_items):
            s = SCALES[i]
            yolo_data = img_data["yolo_paths"].get(s)
            
            if yolo_data and yolo_data[0]:
                yolo_path, is_detected = yolo_data
                fname = yolo_path.name
                src = f"/yolo/sigma_{s}/{fname}"
                
                show_image(item, src)
                
                if is_detected:
                    item["det"].text = "🔴 DETECTED"
                    item["det"]._classes = ["status-dot-detected"]
                    earthquake_detected = True
                else:
                    item["det"].text = "🟢 clear"
                    item["det"]._classes = ["status-dot-done"]
            else:
                hide_image(item)
                item["det"].text = "— no data"
                item["det"]._classes = ["status-dot-pending"]
            
            item["det"].update()

        return earthquake_detected

    def clear_all():
        """Reset all frames to placeholder state."""
        for item in carousel_items:
            hide_image(item)
            item["name_lbl"].text = "—"

        for item in scale_items:
            hide_image(item)
            item["dot"].text = "○ pending"
            item["dot"]._classes = ["status-dot-pending"]
            item["dot"].update()

        for item in result_items:
            hide_image(item)
            item["det"].text = "— detections"
            item["det"]._classes = ["status-dot-pending"]
            item["det"].update()

        current_name_label.text = ""
        earthquake_alert.style("display: none;")

    # ══════════════════════════════════════════════════════════
    # CONTROL LOGIC
    # ══════════════════════════════════════════════════════════
    async def toggle_run():
        if not state["running"]:
            state["running"] = True
            start_btn.style(
                "background-color: #d29922; color: #0d1117; font-weight: bold; "
                "border-radius: 8px; padding: 8px 20px; font-size: 13px;"
            )
            start_btn.text = "⏸  Pause"
            status_label.text = "● Processing..."
            status_label.style("color: #d29922;")
            asyncio.create_task(run_pipeline())
        else:
            state["running"] = False
            start_btn.style(
                "background-color: #3fb950; color: #0d1117; font-weight: bold; "
                "border-radius: 8px; padding: 8px 20px; font-size: 13px;"
            )
            start_btn.text = "▶  Resume"
            status_label.text = "● Paused"
            status_label.style("color: #d29922;")

    def reset():
        state["running"] = False
        state["current_index"] = 0
        state["elapsed"] = 0

        timer_label.text = "00:00:00"
        counter_label.text = f"0000 / {TOTAL_IMAGES}"
        progress.value = 0
        start_btn.text = "▶  Start"
        start_btn.style(
            "background-color: #3fb950; color: #0d1117; font-weight: bold; "
            "border-radius: 8px; padding: 8px 20px; font-size: 13px;"
        )
        status_label.text = "● Ready — press Start to begin"
        status_label.style("color: #3fb950;")
        progress_text.text = f"0 / {TOTAL_IMAGES} images processed"

        clear_all()

    async def run_pipeline():
        asyncio.create_task(run_timer())

        while state["running"] and state["current_index"] < TOTAL_IMAGES:
            idx = state["current_index"]

            # Update counter & progress
            counter_label.text = f"{idx+1:04d} / {TOTAL_IMAGES}"
            progress.value = (idx + 1) / TOTAL_IMAGES
            progress_text.text = f"{idx+1} / {TOTAL_IMAGES} images processed"

            # ── Step 1: Load carousel ──
            update_carousel(idx)
            await asyncio.sleep(0.8)  # Increased from 0.2

            if not state["running"]:
                break

            # ── Step 2: Load scales ──
            img_data = IMAGE_LIST[idx]
            current_name_label.text = f"📎 {img_data['base_name']}"

            for i, item in enumerate(scale_items):
                if not state["running"]:
                    break

                s = item["scale"]
                item["dot"].text = "● loading..."
                item["dot"]._classes = ["status-dot-processing"]
                item["dot"].update()

                await asyncio.sleep(0.5)  # Increased from 0.15

                fname = f"{img_data['base_name']}_sigma{s}.png"
                src = f"/images/sigma_{s}/{fname}"

                if img_data["paths"][s].exists():
                    show_image(item, src)
                    item["dot"].text = "✓ loaded"
                    item["dot"]._classes = ["status-dot-done"]
                else:
                    hide_image(item)
                    item["dot"].text = "✗ missing"
                    item["dot"]._classes = ["status-dot-pending"]
                item["dot"].update()

            if not state["running"]:
                break

            await asyncio.sleep(1.0)  # Increased from 0.2

            # ── Step 3: Load YOLO results ──
            earthquake_detected = update_yolo(idx)

            # Show earthquake alert if detected
            if earthquake_detected:
                earthquake_alert.style("display: flex;")
                await asyncio.sleep(3.5)  # Increased from 2.0
                earthquake_alert.style("display: none;")

            if not state["running"]:
                break

            # Hold for viewing
            await asyncio.sleep(3.5)  # Increased from 0.8

            # ── Reset results for next image ──
            for item in result_items:
                hide_image(item)
                item["det"].text = "— detections"
                item["det"]._classes = ["status-dot-pending"]
                item["det"].update()

            # Reset scale placeholders
            for item in scale_items:
                hide_image(item)
                item["dot"].text = "○ pending"
                item["dot"]._classes = ["status-dot-pending"]
                item["dot"].update()

            state["current_index"] += 1

        # Done or paused
        state["running"] = False

        if state["current_index"] >= TOTAL_IMAGES:
            start_btn.text = "✓  Done"
            start_btn.style(
                "background-color: #3fb950; color: #0d1117; font-weight: bold; "
                "border-radius: 8px; padding: 8px 20px; font-size: 13px;"
            )
            status_label.text = "● Complete!"
            status_label.style("color: #3fb950;")

    async def run_timer():
        """Independent timer that ticks every second while running."""
        while state["running"]:
            await asyncio.sleep(1)
            if state["running"]:
                state["elapsed"] += 1
                h = state["elapsed"] // 3600
                m = (state["elapsed"] % 3600) // 60
                s = state["elapsed"] % 60
                timer_label.text = f"{h:02d}:{m:02d}:{s:02d}"


create_page()

ui.run(
    title="CWT × YOLO — Multi-Scale Analysis",
    port=8080,
    reload=False,
    dark=True,
)