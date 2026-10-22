"""
Run this ON YOUR MACHINE (or in Colab, recommended if no local GPU).

Fine-tunes a small YOLOv8 model on the container-damage dataset for your
CV module. Uses transfer learning (starts from COCO-pretrained weights,
not from scratch) — standard approach, much faster and more accurate on a
dataset this size (1,000s of images, not millions).

Setup:
    pip install ultralytics

Usage:
    python3 train_yolo.py
"""

from ultralytics import YOLO

# --- EDIT THIS to point at your merged dataset's data.yaml (from merge_datasets.py) ---
DATA_YAML_PATH = "merged_dataset/data.yaml"

# --- v3 settings: back to the LIGHTER config from v1, which actually
#     outperformed v2's heavier setup (mAP50 0.336 vs 0.297). Key lesson
#     carried forward: more augmentation/capacity isn't automatically better
#     on a small dataset — flipud especially was likely actively harmful
#     since containers are never seen upside-down in reality, so it's
#     removed entirely this time, not just toned down.
#
#     What's different from v1 (not just a repeat): more training data now
#     (merged dataset, +300-500 images), so a few more epochs are reasonable
#     since there's more to learn from without immediately overfitting.
EPOCHS = 80
IMG_SIZE = 640
BATCH_SIZE = 16
MODEL_SIZE = "yolov8n.pt"   # nano — this is what worked best, stick with it

AUGMENTATION = dict(
    degrees=5.0,       # mild rotation only
    translate=0.1,
    scale=0.5,
    shear=0.0,
    flipud=0.0,        # REMOVED — unrealistic for containers, likely hurt v2
    fliplr=0.5,         # horizontal flip is fine — a container can realistically face either way
    mixup=0.0,          # REMOVED — likely blurred subtle rust texture in v2
    mosaic=1.0,          # this one's a YOLO default and wasn't the suspected problem, kept as-is
)

def main():
    model = YOLO(MODEL_SIZE)  # loads COCO-pretrained weights automatically

    results = model.train(
        data=DATA_YAML_PATH,
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        batch=BATCH_SIZE,
        name="container_damage_detector_v3",
        patience=20,
        cos_lr=True,
        **AUGMENTATION,
    )

    print("\nTraining complete.")
    print(f"Best weights saved at: runs/detect/container_damage_detector_v3/weights/best.pt")
    print("Run evaluate_yolo.py next (update MODEL_PATH to the v3 folder above) to get final accuracy metrics.")


if __name__ == "__main__":
    main()
