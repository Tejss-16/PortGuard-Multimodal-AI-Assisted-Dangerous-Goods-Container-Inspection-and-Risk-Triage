from pathlib import Path
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = (
    PROJECT_ROOT / "models" / "container_damage_detector"
    / "weights" / "best.pt"
)

IMAGES_DIR = (
    PROJECT_ROOT / "data" / "test_images" / "imagesnew.jpeg"
)

OUTPUT_DIR = PROJECT_ROOT / "runs" / "detect" / "predictions"

CONFIDENCE_THRESHOLD = 0.25

def main():
    model = YOLO(MODEL_PATH)

    results = model.predict(
        source=IMAGES_DIR,
        conf=CONFIDENCE_THRESHOLD,
        save=True,
        project=OUTPUT_DIR,
        name="visualized",
        exist_ok=True,
    )

    print(f"Processed {len(results)} images.")
    print(f"Saved to: {OUTPUT_DIR}/visualized")

    for r in results:
        filename = Path(r.path).name
        detections = []
        for box in r.boxes:
            class_name = model.names[int(box.cls)]
            confidence = float(box.conf)
            detections.append(f"{class_name} ({confidence:.2f})")

        print(filename, detections if detections else "no damage detected")

if __name__ == "__main__":
    main()