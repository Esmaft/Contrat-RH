"""
Service OCR — API FastAPI indépendante
Reçoit un PDF et retourne le texte extrait
"""

import cv2
import os
import platform
import tempfile
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
ocr_model = ocr_predictor(pretrained=True)
print("Modèle OCR prêt.")

app = FastAPI(title="Service OCR", version="1.0")


@app.get("/")
def health_check():
    return {"status": "Service OCR en ligne", "version": "1.0"}


@app.post("/extract")
async def extraire_texte(fichier: UploadFile = File(...)):
    """
    Reçoit un PDF et retourne le texte extrait + confiance OCR
    """
    suffix = os.path.splitext(fichier.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contenu = await fichier.read()
        tmp.write(contenu)
        chemin_tmp = tmp.name

    try:
        pages = convert_from_path(chemin_tmp, poppler_path=POPPLER_PATH)
        texte_complet = ""
        confiances = []

        for i, page in enumerate(pages):
            nom = os.path.join(DOSSIER_IMAGES, f"page_{i+1}.jpg")
            page.save(nom)

            # Prétraitement
            image = cv2.imread(nom)
            gris = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            debruite = cv2.fastNlMeansDenoising(gris, h=10)
            nom_pre = nom.replace(".jpg", "_pretraite.jpg")
            cv2.imwrite(nom_pre, debruite)

            # OCR
            doc = DocumentFile.from_images(nom_pre)
            result = ocr_model(doc)

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
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )
    finally:
        os.unlink(chemin_tmp)