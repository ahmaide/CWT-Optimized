# GUI.py

from nicegui import ui, app
import asyncio
import time

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────
SCALES = [2, 4, 8, 16, 32]
TOTAL_IMAGES = 2000

# ──────────────────────────────────────────────────────────────
# State
# ──────────────────────────────────────────────────────────────
state = {
    "running": False,
    "current_index": 0,
    "elapsed": 0,
    "task": None,
}


# ──────────────────────────────────────────────────────────────
# Custom CSS
# ──────────────────────────────────────────────────────────────
CUSTOM_CSS = """
<style>
    body {
        background-color: #0d1117 !important;
    }

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
        transition: all 0.3s ease;
    }

    .image-frame-active {
        border-color: #58a6ff !important;
        box-shadow: 0 0 20px rgba(88, 166, 255, 0.2);
    }

    .image-frame-processing {
        border-color: #d29922 !important;
        box-shadow: 0 0 15px rgba(210, 153, 34, 0.2);
    }

    .image-frame-done {
        border-color: #3fb950 !important;
        box-shadow: 0 0 15px rgba(63, 185, 80, 0.15);
    }

    .image-frame-center {
        border-color: #58a6ff !important;
        box-shadow: 0 0 25px rgba(88, 166, 255, 0.3);
        transform: scale(1.08);
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
    }

    .badge-purple {
        background: #bc8cff;
    }

    .badge-green {
        background: #3fb950;
    }

    .timer-box {
        background: #1c2333;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 6px 14px;
        font-family: 'Consolas', monospace;
    }

    .counter-box {
        background: #1c2333;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 6px 14px;
        font-family: 'Consolas', monospace;
    }

    .section-bar {
        width: 4px;
        height: 28px;
        border-radius: 2px;
        display: inline-block;
    }

    .arrow-down {
        color: #58a6ff;
        font-size: 22px;
        text-align: center;
    }

    .status-dot-pending {
        color: #484f58;
        font-family: 'Consolas', monospace;
        font-size: 12px;
    }

    .status-dot-processing {
        color: #d29922;
        font-family: 'Consolas', monospace;
        font-size: 12px;
    }

    .status-dot-done {
        color: #3fb950;
        font-family: 'Consolas', monospace;
        font-size: 12px;
    }

    .progress-bar-container {
        background: #161b22;
        height: 6px;
        width: 100%;
        border-radius: 0;
    }

    .status-bar {
        background: #161b22;
        border-top: 1px solid #30363d;
        padding: 8px 24px;
        font-family: 'Consolas', monospace;
        font-size: 12px;
    }
</style>
"""


def create_page():
    # Inject custom CSS
    ui.html(CUSTOM_CSS)

    # ══════════════════════════════════════════════════════════
    # TOP BAR
    # ══════════════════════════════════════════════════════════
    with ui.row().classes("top-bar w-full items-center justify-between"):

        # Left: Title
        with ui.row().classes("items-center gap-3"):
            ui.label("CWT × YOLO").style(
                "font-size: 22px; font-weight: bold; color: #e6edf3;"
            )
            ui.label("Multi-Scale Analysis Pipeline").style(
                "font-size: 13px; color: #8b949e; padding-top: 4px;"
            )

        # Right: Controls
        with ui.row().classes("items-center gap-3"):

            # Timer
            with ui.row().classes("timer-box items-center gap-2"):
                ui.label("⏱").style("font-size: 14px;")
                timer_label = ui.label("00:00:00").style(
                    "font-size: 18px; font-weight: bold; color: #58a6ff;"
                )

            # Counter
            with ui.row().classes("counter-box items-center gap-2"):
                ui.label("IMG").style(
                    "font-size: 10px; font-weight: bold; color: #484f58;"
                )
                counter_label = ui.label("0000 / 2000").style(
                    "font-size: 14px; font-weight: bold; color: #e6edf3;"
                )

            # Start/Pause Button
            start_btn = ui.button("▶  Start", on_click=lambda: toggle_run()).style(
                "background-color: #3fb950; color: #0d1117; font-weight: bold; "
                "border-radius: 8px; padding: 8px 20px; font-size: 13px;"
            )

            # Reset Button
            ui.button("↺  Reset", on_click=lambda: reset()).style(
                "background-color: #1c2333; color: #8b949e; font-weight: bold; "
                "border: 1px solid #30363d; border-radius: 8px; "
                "padding: 8px 16px; font-size: 13px;"
            )

    # ══════════════════════════════════════════════════════════
    # MAIN CONTENT
    # ══════════════════════════════════════════════════════════
    with ui.column().classes("w-full items-center").style("padding: 20px 24px; gap: 8px;"):

        # ──────────────────────────────────────────────────────
        # SECTION 1: IMAGE CAROUSEL
        # ──────────────────────────────────────────────────────
        with ui.column().classes("section-card w-full"):

            # Header
            with ui.row().classes("items-center gap-3"):
                ui.html('<div class="section-bar" style="background:#58a6ff;"></div>')
                with ui.column().style("gap: 2px;"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label("📂").style("font-size: 16px;")
                        ui.label("Image Carousel").style(
                            "font-size: 15px; font-weight: bold; color: #e6edf3;"
                        )
                    ui.label(
                        "Source images slide through — center image is selected for analysis"
                    ).style("font-size: 11px; color: #8b949e; padding-left: 26px;")

            # Carousel Images
            with ui.row().classes("w-full justify-center items-end gap-4").style(
                "padding-top: 16px; padding-bottom: 8px;"
            ):
                carousel_frames = []
                sizes = [
                    (90, 72, False),
                    (110, 88, False),
                    (148, 120, True),   # center
                    (110, 88, False),
                    (90, 72, False),
                ]

                for i, (w, h, is_center) in enumerate(sizes):
                    with ui.column().classes("items-center gap-1"):
                        if is_center:
                            with ui.element("div").classes("glow-wrapper"):
                                frame = ui.column().classes(
                                    "image-frame image-frame-center items-center justify-center"
                                ).style(f"width: {w}px; height: {h}px;")
                                with frame:
                                    icon = ui.label("🖼").style(
                                        "font-size: 28px; color: #484f58;"
                                    )
                                    lbl = ui.label(f"img_0001.png").style(
                                        "font-size: 10px; color: #8b949e;"
                                    )
                            ui.label("▲ SELECTED").style(
                                "font-size: 9px; font-weight: bold; color: #58a6ff; "
                                "font-family: Consolas, monospace;"
                            )
                        else:
                            frame = ui.column().classes(
                                "image-frame items-center justify-center"
                            ).style(f"width: {w}px; height: {h}px;")
                            with frame:
                                icon = ui.label("🖼").style(
                                    "font-size: 22px; color: #484f58;"
                                )
                                lbl = ui.label(f"img_{(i+1):04d}.png").style(
                                    "font-size: 9px; color: #8b949e;"
                                )

                        carousel_frames.append({"frame": frame, "icon": icon, "label": lbl})

        # Arrow Down
        ui.label("▼").classes("arrow-down").style("padding: 2px 0;")

        # ──────────────────────────────────────────────────────
        # SECTION 2: CWT SCALES
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
                        "Selected image decomposed at scales: 2×  4×  8×  16×  32×"
                    ).style("font-size: 11px; color: #8b949e; padding-left: 26px;")

            with ui.row().classes("w-full justify-center items-start gap-5").style(
                "padding-top: 16px; padding-bottom: 8px;"
            ):
                scale_items = []
                for scale in SCALES:
                    with ui.column().classes("items-center gap-1"):
                        frame = ui.column().classes(
                            "image-frame items-center justify-center"
                        ).style("width: 140px; height: 108px; position: relative;")
                        with frame:
                            ui.html(
                                f'<span class="badge badge-purple" '
                                f'style="position:absolute;top:6px;right:6px;">{scale}×</span>'
                            )
                            icon = ui.label("🖼").style(
                                "font-size: 26px; color: #484f58;"
                            )
                            ui.label(f"Scale {scale}×").style(
                                "font-size: 10px; color: #8b949e;"
                            )

                        dot = ui.label("○ pending").classes("status-dot-pending")
                        scale_items.append({"frame": frame, "icon": icon, "dot": dot})

        # Arrow Down
        ui.label("▼").classes("arrow-down").style("padding: 2px 0;")

        # ──────────────────────────────────────────────────────
        # SECTION 3: YOLO RESULTS
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
                        "Object detection applied to each CWT-scaled image"
                    ).style("font-size: 11px; color: #8b949e; padding-left: 26px;")

            with ui.row().classes("w-full justify-center items-start gap-5").style(
                "padding-top: 16px; padding-bottom: 8px;"
            ):
                result_items = []
                for scale in SCALES:
                    with ui.column().classes("items-center gap-1"):
                        frame = ui.column().classes(
                            "image-frame items-center justify-center"
                        ).style("width: 140px; height: 108px;")
                        with frame:
                            ui.html(
                                f'<span class="badge badge-green" '
                                f'style="position:absolute;top:6px;right:6px;">{scale}×</span>'
                            )
                            icon = ui.label("🖼").style(
                                "font-size: 26px; color: #484f58;"
                            )
                            ui.label(f"YOLO @ {scale}×").style(
                                "font-size: 10px; color: #8b949e;"
                            )

                        det = ui.label("— detections").classes("status-dot-pending")
                        result_items.append({"frame": frame, "icon": icon, "det": det})

    # ══════════════════════════════════════════════════════════
    # PROGRESS BAR
    # ══════════════════════════════════════════════════════════
    progress = ui.linear_progress(value=0, show_value=False).style(
        "height: 6px; margin: 0;"
    ).props("color=#58a6ff track-color=#161b22")

    # ══════════════════════════════════════════════════════════
    # STATUS BAR
    # ══════════════════════════════════════════════════════════
    with ui.row().classes("status-bar w-full items-center justify-between"):
        status_label = ui.label("● Ready").style("color: #3fb950;")
        progress_text = ui.label("0 / 2000 images processed").style("color: #8b949e;")

    # ══════════════════════════════════════════════════════════
    # LOGIC
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
            state["task"] = asyncio.create_task(run_pipeline())
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
        counter_label.text = "0000 / 2000"
        progress.value = 0
        start_btn.text = "▶  Start"
        start_btn.style(
            "background-color: #3fb950; color: #0d1117; font-weight: bold; "
            "border-radius: 8px; padding: 8px 20px; font-size: 13px;"
        )
        status_label.text = "● Ready"
        status_label.style("color: #3fb950;")
        progress_text.text = "0 / 2000 images processed"

        for item in scale_items:
            item["frame"]._classes = [
                c for c in item["frame"]._classes
                if "processing" not in c and "done" not in c
            ]
            item["icon"].text = "🖼"
            item["dot"].text = "○ pending"
            item["dot"]._classes = ["status-dot-pending"]
            item["dot"].update()
            item["frame"].update()

        for item in result_items:
            item["icon"].text = "🖼"
            item["det"].text = "— detections"
            item["det"]._classes = ["status-dot-pending"]
            item["det"].update()

    async def run_pipeline():
        while state["running"] and state["current_index"] < TOTAL_IMAGES:
            idx = state["current_index"]

            # Update counter & progress
            counter_label.text = f"{idx+1:04d} / {TOTAL_IMAGES}"
            progress.value = (idx + 1) / TOTAL_IMAGES
            progress_text.text = f"{idx+1} / {TOTAL_IMAGES} images processed"

            # Update timer
            state["elapsed"] += 1
            h = state["elapsed"] // 3600
            m = (state["elapsed"] % 3600) // 60
            s = state["elapsed"] % 60
            timer_label.text = f"{h:02d}:{m:02d}:{s:02d}"

            # Process each scale
            for i, item in enumerate(scale_items):
                if not state["running"]:
                    return

                # Mark processing
                item["dot"].text = "● processing"
                item["dot"]._classes = ["status-dot-processing"]
                item["dot"].update()
                item["icon"].text = "⏳"

                await asyncio.sleep(0.15)

                # Mark done
                item["dot"].text = "✓ complete"
                item["dot"]._classes = ["status-dot-done"]
                item["dot"].update()
                item["icon"].text = "✅"

                # YOLO result
                result_items[i]["icon"].text = "✅"
                result_items[i]["det"].text = "✓ detected"
                result_items[i]["det"]._classes = ["status-dot-done"]
                result_items[i]["det"].update()

            await asyncio.sleep(0.4)

            # Reset frames for next image
            for item in scale_items:
                item["icon"].text = "🖼"
                item["dot"].text = "○ pending"
                item["dot"]._classes = ["status-dot-pending"]
                item["dot"].update()

            for item in result_items:
                item["icon"].text = "🖼"
                item["det"].text = "— detections"
                item["det"]._classes = ["status-dot-pending"]
                item["det"].update()

            state["current_index"] += 1

        if state["current_index"] >= TOTAL_IMAGES:
            state["running"] = False
            start_btn.text = "✓  Done"
            start_btn.style(
                "background-color: #3fb950; color: #0d1117; font-weight: bold; "
                "border-radius: 8px; padding: 8px 20px; font-size: 13px;"
            )
            status_label.text = "● Complete!"
            status_label.style("color: #3fb950;")


# ──────────────────────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────────────────────
create_page()

ui.run(
    title="CWT × YOLO — Multi-Scale Analysis",
    port=8080,
    reload=False,
    dark=True,
)