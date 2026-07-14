"""
Service OCR — API FastAPI indépendante
Reçoit un PDF et retourne le texte extrait
"""

import os
import platform
import tempfile
import time
import torch
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
from pdf2image import convert_from_path

POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin" if platform.system() == "Windows" else None
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOSSIER_IMAGES = os.path.join(BASE_DIR, "images_pretraitees")
os.makedirs(DOSSIER_IMAGES, exist_ok=True)

print("Chargement du modèle OCR (DocTR)...")
ocr_model = ocr_predictor(
    pretrained=True,
    assume_straight_pages=True,
    detect_orientation=False,
)

if torch.cuda.is_available():
    try:
        ocr_model = ocr_model.cuda()
        print(f"DocTR sur GPU : {torch.cuda.get_device_name(0)}")
        vram_utilisee = torch.cuda.memory_allocated(0) / 1024**3
        print(f"VRAM utilisée par DocTR : {vram_utilisee:.2f} GB")
    except RuntimeError as e:
        print(f"⚠️ Échec GPU, fallback CPU : {e}")
else:
    print("⚠️ GPU non disponible, DocTR reste sur CPU")

ocr_model = ocr_model.eval()

print("Modèle OCR prêt (GPU).")
app = FastAPI(title="Service OCR", version="1.0")

NB_PAGES_MAX = 1
DPI_CONVERSION = 150  # suffisant pour du texte imprimé net, réduit le coût de conversion + inférence


@app.get("/")
def health_check():
    return {"status": "Service OCR en ligne", "version": "1.0"}


@app.post("/extract")
async def extraire_texte(fichier: UploadFile = File(...)):
    suffix = os.path.splitext(fichier.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contenu = await fichier.read()
        tmp.write(contenu)
        chemin_tmp = tmp.name

    chemins_images = []

    try:
        t0 = time.time()
        pages = convert_from_path(chemin_tmp, poppler_path=POPPLER_PATH, dpi=DPI_CONVERSION)
        pages_a_traiter = pages  # au lieu de pages[:NB_PAGES_MAX]

        for i, page in enumerate(pages_a_traiter):
            nom = os.path.join(DOSSIER_IMAGES, f"page_{i+1}.jpg")
            page.save(nom)
            chemins_images.append(nom)

        t1 = time.time()
        print(f"[OCR-TIMING] Conversion PDF->image : {t1 - t0:.2f}s")

        # Traitement en UN SEUL batch, aucun prétraitement manuel
        doc = DocumentFile.from_images(chemins_images)
        t2 = time.time()
        print(f"[OCR-TIMING] Chargement images DocTR : {t2 - t1:.2f}s")

        with torch.no_grad():  # désactive le calcul de gradient, gain de vitesse et mémoire
            result = ocr_model(doc)

        t3 = time.time()
        print(f"[OCR-TIMING] Inférence OCR : {t3 - t2:.2f}s")

        texte_complet = ""
        confiances = []

        for page_r in result.pages:
            for block in page_r.blocks:
                for line in block.lines:
                    ligne = " ".join([w.value for w in line.words])
                    confs = [w.confidence for w in line.words]
                    if confs and sum(confs) / len(confs) > 0.5:
                        texte_complet += ligne + "\n"
                        confiances.extend(confs)

        confiance_globale = sum(confiances) / len(confiances) if confiances else 0
        return JSONResponse(content={
            "success": True,
            "texte": texte_complet,
            "confiance": round(confiance_globale, 2)
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )
    finally:
        os.unlink(chemin_tmp)
        for chemin in chemins_images:
            if os.path.exists(chemin):
                os.unlink(chemin)