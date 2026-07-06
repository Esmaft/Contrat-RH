"""
Service Signature — Détection de signatures via YOLOv8 + Analyse pixels
API FastAPI indépendante sur port 8002
"""
import os
import tempfile
import platform
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from ultralytics import YOLO
from pdf2image import convert_from_path

POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin" if platform.system() == "Windows" else None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(BASE_DIR, "models", "best.pt")

print("Chargement du modèle YOLOv8...")
model = YOLO(MODEL_PATH)
print("Modèle signature prêt.")

app = FastAPI(title="Service Signature", version="1.0")


def analyser_zone_signature(chemin_image):
    """
    Analyse la densité de pixels noirs dans le bas de page (zone signature)
    Retourne True si signature probable, False sinon
    """
    image = cv2.imread(chemin_image, cv2.IMREAD_GRAYSCALE)
    hauteur, largeur = image.shape

    # Zone signature = 25% bas de page
    zone = image[int(hauteur * 0.75):, :]

    # Pixels sombres = encre
    _, binaire = cv2.threshold(zone, 150, 255, cv2.THRESH_BINARY_INV)
    densite = np.sum(binaire > 0) / zone.size

    print(f"Densité pixels zone signature : {densite:.4f}")
    return densite


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

    try:
        # Convertir PDF — seulement la dernière page
        pages = convert_from_path(chemin_tmp, poppler_path=POPPLER_PATH)
        derniere_page = pages[-1]

        chemin_page = chemin_tmp + "_signature.jpg"
        derniere_page.save(chemin_page)

        # Étape 1 — YOLOv8
        results = model(chemin_page, conf=0.3, verbose=False)
        nb = len(results[0].boxes)
        methode = "YOLOv8"

        # Étape 2 — Si YOLOv8 ne détecte pas → analyse pixels
        if nb == 0:
            densite = analyser_zone_signature(chemin_page)
            if densite > 0.02:  # seuil à calibrer
                nb = 1
                methode = "Analyse pixels"
                print(f"Signature détectée par analyse pixels (densité={densite:.4f})")
            else:
                print(f"Aucune signature (densité={densite:.4f})")

        signatures_totales = nb
        pages_avec_signature = [len(pages)] if nb > 0 else []

        os.unlink(chemin_page)

        return JSONResponse(content={
            "success": True,
            "signature_detectee": signatures_totales > 0,
            "nb_signatures": signatures_totales,
            "pages_avec_signature": pages_avec_signature,
            "methode_detection": methode,
            "message": f"{signatures_totales} signature(s) détectée(s) via {methode}" if signatures_totales > 0 else "Aucune signature détectée — contrat non signé"
        })

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )
    finally:
        os.unlink(chemin_tmp)