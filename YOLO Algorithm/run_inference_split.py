import argparse
import os
from ultralytics import YOLO


def run_inference(model_path, source_folder, output_root, conf=None, imgsz=640, device="0"):
    dir_detections = os.path.join(output_root, "Detections")
    dir_no_detections = os.path.join(output_root, "NoDetections")

    os.makedirs(dir_detections, exist_ok=True)
    os.makedirs(dir_no_detections, exist_ok=True)

    print(f"Processing: {source_folder}")
    print(f"Saving DETECTIONS to: {dir_detections}")
    print(f"Saving NO DETECTIONS to: {dir_no_detections}")

    model = YOLO(model_path)

    predict_kwargs = {
        "source": source_folder,
        "stream": True,
        "imgsz": imgsz,
        "device": device,
    }
    if conf is not None:
        predict_kwargs["conf"] = conf

    results = model.predict(**predict_kwargs)

    detections_count = 0
    no_detections_count = 0

    for result in results:
        filename = os.path.basename(result.path)

        if len(result.boxes) > 0:
            save_path = os.path.join(dir_detections, filename)
            result.save(filename=save_path)
            detections_count += 1
        else:
            save_path = os.path.join(dir_no_detections, filename)
            result.save(filename=save_path)
            no_detections_count += 1

    print("Processing complete.")
    print(f"Number of images with detections: {detections_count}")
    print(f"Number of images without detections: {no_detections_count}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run YOLO inference and split images into Detections/NoDetections."
    )
    parser.add_argument(
        "--model",
        default=(
            "/home/jacgonzalez/project/code/Classification/YOLO/draft_model1/runs/"
            "detect/yolo11n-allTraining-eval6/weights/best.pt"
        ),
        help="Path to trained YOLO .pt model.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source directory containing images.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output root directory where Detections/ and NoDetections/ are created.",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=None,
        help="Optional confidence threshold (for example 0.5).",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Inference image size (default: 640).",
    )
    parser.add_argument(
        "--device",
        default="0",
        help="Device to use, notebook-style default is GPU 0 (use 'cpu' if needed).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_inference(
        model_path=args.model,
        source_folder=args.source,
        output_root=args.output,
        conf=args.conf,
        imgsz=args.imgsz,
        device=args.device,
    )
