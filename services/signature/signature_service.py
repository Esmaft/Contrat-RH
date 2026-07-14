"""
Service Signature — Détection de signatures via YOLOv8
API FastAPI indépendante sur port 8002
"""
import os
import tempfile
import platform
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from ultralytics import YOLO
from pdf2image import convert_from_path

POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin" if platform.system() == "Windows" else None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(BASE_DIR, "models", "yolov8s_signature_final.pt")

print("Chargement du modèle YOLOv8...")
model = YOLO(MODEL_PATH)
print("Modèle signature prêt.")

app = FastAPI(title="Service Signature", version="1.0")


@app.get("/")
def health_check():
    return {"status": "Service Signature en ligne", "version": "1.0"}


@app.post("/detect")
async def detecter_signature(fichier: UploadFile = File(...)):
    suffix = os.path.splitext(fichier.filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contenu = await fichier.read()
        tmp.write(contenu)
        chemin_tmp = tmp.name

    chemin_page = None

    try:
        # Convertir PDF — seulement la dernière page
        pages = convert_from_path(chemin_tmp, poppler_path=POPPLER_PATH)
        if not pages:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "PDF vide ou illisible"}
            )
        derniere_page = pages[-1]
        numero_derniere_page = len(pages)

        chemin_page = chemin_tmp + "_signature.jpg"
        derniere_page.save(chemin_page)

        # Détection YOLOv8 — laisser Ultralytics gérer son propre prétraitement
        results = model(chemin_page, conf=0.20, iou=0.3, verbose=False)
        nb_signatures = len(results[0].boxes)
        signature_presente = nb_signatures > 0

        # Détail des scores de confiance par signature détectée (utile pour debug/audit)
        confidences = [round(box.conf.item(), 3) for box in results[0].boxes]

        return JSONResponse(content={
            "success": True,
            "signature_detectee": signature_presente,
            "nombre_signatures": nb_signatures,
            "page_analysee": numero_derniere_page,
            "confidences": confidences,
            "message": (
                f"Contrat signé — {nb_signatures} signature(s) détectée(s)"
                if signature_presente
                else "Aucune signature détectée — contrat non signé"
            )
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )
    finally:
        if chemin_page and os.path.exists(chemin_page):
            os.unlink(chemin_page)
        if os.path.exists(chemin_tmp):
            os.unlink(chemin_tmp)