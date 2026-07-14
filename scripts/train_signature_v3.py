from ultralytics import YOLO

if __name__ == "__main__":
    model = YOLO(r"C:\Users\asmae\Downloads\projet rh\models\yolov8s_fusion_v2\weights\best.pt")
    metrics = model.val(data=r"C:\Users\asmae\Downloads\projet rh\dataset_final\data.yaml", imgsz=640)

    print("====================")
    print("RÉSULTATS FINAUX best.pt")
    print("====================")
    print("Precision :", metrics.box.mp)
    print("Recall    :", metrics.box.mr)
    print("mAP50     :", metrics.box.map50)
    print("mAP50-95  :", metrics.box.map)