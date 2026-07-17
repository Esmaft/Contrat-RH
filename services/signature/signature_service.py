"""
Service Signature -- Detection de signatures manuscrites via YOLOv8
=====================================================================
API FastAPI independante, port 8002.

Reçoit un PDF, convertit sa derniere page en image, detecte les
signatures presentes et retourne leur position normalisee (0 a 1) ainsi
que leur score de confiance -- utilise ensuite par le service
d'identification des signataires (voir modules/identification_signataires.py).

Gestion de la concurrence GPU :
-------------------------------
Un seul GPU est partage entre ce service, le service OCR et Ollama (LLM).
Si plusieurs requetes arrivent simultanement, un `asyncio.Semaphore`
serialise les appels d'inference GPU (un seul a la fois pour CE service),
evitant toute contention/instabilite memoire (VRAM) qui pourrait survenir
si Ultralytics recevait plusieurs appels d'inference paralleles sur le
meme modele charge en memoire. Les requetes en exces attendent leur tour
au lieu d'echouer -- au prix d'une latence accrue en cas de forte charge
(le dimensionnement de l'infrastructure -- ex: plusieurs GPU/instances
en parallele -- releve du deploiement, pas du code applicatif).
"""

import asyncio
import logging
import os
import platform
import tempfile

import cv2
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from pdf2image import convert_from_path
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("signature_service")

POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin" if platform.system() == "Windows" else None
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_PATH = os.path.join(BASE_DIR, "models", "yolov8s_signature_final.pt")

CONFIDENCE_THRESHOLD = 0.20
IOU_THRESHOLD = 0.3
DPI_CONVERSION = 200

# Nombre d'inferences GPU autorisees en parallele pour ce service.
# 1 = le plus sur (evite toute contention GPU), ajustable via variable
# d'environnement si le serveur de production dispose de plus de VRAM.
MAX_INFERENCES_PARALLELES = int(os.getenv("SIGNATURE_MAX_PARALLEL", "1"))
semaphore_gpu = asyncio.Semaphore(MAX_INFERENCES_PARALLELES)

logger.info("Chargement du modele YOLOv8...")
model = YOLO(MODEL_PATH)
logger.info("Modele signature pret.")

app = FastAPI(title="Service Signature", version="1.3")


@app.get("/")
def health_check():
    return {"status": "Service Signature en ligne", "version": "1.3"}


@app.post("/detect")
async def detecter_signature(fichier: UploadFile = File(...)):
    suffix = os.path.splitext(fichier.filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contenu = await fichier.read()
        tmp.write(contenu)
        chemin_tmp = tmp.name

    chemin_page = None

    try:
        pages = convert_from_path(chemin_tmp, poppler_path=POPPLER_PATH, dpi=DPI_CONVERSION)
        if not pages:
            return JSONResponse(status_code=400, content={
                "success": False, "error": "PDF vide ou illisible"
            })

        derniere_page = pages[-1]
        index_page_zero = len(pages) - 1  # convention 0-indexee, alignee avec le service OCR

        chemin_page = chemin_tmp + "_signature.jpg"
        derniere_page.save(chemin_page)

        image = cv2.imread(chemin_page)
        hauteur_img, largeur_img = image.shape[:2]

        # Un seul appel d'inference GPU a la fois pour ce service.
        async with semaphore_gpu:
            results = model(chemin_page, conf=CONFIDENCE_THRESHOLD, iou=IOU_THRESHOLD, verbose=False)

        signatures_info = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            signatures_info.append({
                "confidence": round(box.conf.item(), 3),
                "x_center": round(((x1 + x2) / 2) / largeur_img, 4),
                "y_center": round(((y1 + y2) / 2) / hauteur_img, 4),
                "page": index_page_zero,
            })

        nb_signatures = len(signatures_info)
        signature_presente = nb_signatures > 0

        return JSONResponse(content={
            "success": True,
            "signature_detectee": signature_presente,
            "nombre_signatures": nb_signatures,
            "page_analysee": len(pages),
            "signatures": signatures_info,
            "message": (
                f"Contrat signe -- {nb_signatures} signature(s) detectee(s)"
                if signature_presente else "Aucune signature detectee -- contrat non signe"
            ),
        })

    except Exception as e:
        logger.exception("Erreur lors de la detection de signature")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

    finally:
        if chemin_page and os.path.exists(chemin_page):
            os.unlink(chemin_page)
        if os.path.exists(chemin_tmp):
            os.unlink(chemin_tmp)