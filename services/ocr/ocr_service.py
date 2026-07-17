"""
Service OCR -- Extraction de texte via DocTR
==============================================
API FastAPI independante, port 8001.

Recoit un PDF, convertit toutes ses pages en images, et retourne :
- le texte complet reconnu (filtre par confiance moyenne par ligne)
- la position normalisee (0 a 1) de chaque mot, utilisee par le module
  d'identification des signataires pour localiser les noms sur la page.

Optimisations appliquees (voir historique du projet) :
- Inference sur GPU si disponible (division du temps de traitement par
  environ 9 par rapport au CPU sur les documents de test).
- Traitement en un seul batch (toutes les pages en une inference).
- Aucun pretraitement d'image manuel (DocTR gere deja son propre
  pretraitement en interne).

Robustesse concurrence :
- Chaque requete traite ses images dans un sous-dossier unique (UUID),
  evitant toute collision de nom de fichier si plusieurs requetes
  arrivent simultanement (auparavant : noms fixes "page_1.jpg" partages
  dans un seul dossier, risque d'ecrasement entre requetes concurrentes).
- Un `asyncio.Semaphore` serialise les appels d'inference GPU (un seul a
  la fois pour ce service), evitant toute contention/instabilite memoire
  si plusieurs requetes arrivent simultanement sur le meme GPU partage
  avec les autres services (Signature, Ollama).
"""

import asyncio
import logging
import os
import platform
import shutil
import tempfile
import uuid

import torch
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
from pdf2image import convert_from_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ocr_service")

POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin" if platform.system() == "Windows" else None
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOSSIER_IMAGES_RACINE = os.path.join(BASE_DIR, "images_pretraitees")
os.makedirs(DOSSIER_IMAGES_RACINE, exist_ok=True)

DPI_CONVERSION = 200
CONFIANCE_LIGNE_MIN = 0.5

# Nombre d'inferences GPU autorisees en parallele pour ce service.
MAX_INFERENCES_PARALLELES = int(os.getenv("OCR_MAX_PARALLEL", "1"))
semaphore_gpu = asyncio.Semaphore(MAX_INFERENCES_PARALLELES)

logger.info("Chargement du modele OCR (DocTR)...")
ocr_model = ocr_predictor(pretrained=True, assume_straight_pages=True, detect_orientation=False)

if torch.cuda.is_available():
    ocr_model = ocr_model.cuda()
    logger.info("DocTR sur GPU : %s", torch.cuda.get_device_name(0))
else:
    logger.warning("GPU non disponible, DocTR tourne sur CPU (plus lent)")

ocr_model = ocr_model.eval()
logger.info("Modele OCR pret.")

app = FastAPI(title="Service OCR", version="1.3")


@app.get("/")
def health_check():
    return {"status": "Service OCR en ligne", "version": "1.3"}


@app.post("/extract")
async def extraire_texte(fichier: UploadFile = File(...)):
    suffix = os.path.splitext(fichier.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contenu = await fichier.read()
        tmp.write(contenu)
        chemin_tmp = tmp.name

    # Sous-dossier unique pour cette requete -- evite toute collision si
    # une autre requete est traitee en parallele au meme moment.
    id_requete = uuid.uuid4().hex
    dossier_requete = os.path.join(DOSSIER_IMAGES_RACINE, id_requete)
    os.makedirs(dossier_requete, exist_ok=True)

    chemins_images = []

    try:
        pages = convert_from_path(chemin_tmp, poppler_path=POPPLER_PATH, dpi=DPI_CONVERSION)

        for i, page in enumerate(pages):
            chemin = os.path.join(dossier_requete, f"page_{i + 1}.jpg")
            page.save(chemin)
            chemins_images.append(chemin)

        doc = DocumentFile.from_images(chemins_images)

        # Un seul appel d'inference GPU a la fois pour ce service.
        async with semaphore_gpu:
            with torch.no_grad():
                result = ocr_model(doc)

        texte_complet = ""
        confiances = []
        mots_avec_positions = []

        for num_page, page_r in enumerate(result.pages):
            for block in page_r.blocks:
                for line in block.lines:
                    confs_ligne = [w.confidence for w in line.words]
                    if confs_ligne and sum(confs_ligne) / len(confs_ligne) > CONFIANCE_LIGNE_MIN:
                        texte_complet += " ".join(w.value for w in line.words) + "\n"
                        confiances.extend(confs_ligne)

                    for word in line.words:
                        (x_min, y_min), (x_max, y_max) = word.geometry
                        mots_avec_positions.append({
                            "mot": word.value,
                            "x_center": round((x_min + x_max) / 2, 4),
                            "y_center": round((y_min + y_max) / 2, 4),
                            "page": num_page,
                        })

        confiance_globale = sum(confiances) / len(confiances) if confiances else 0

        return JSONResponse(content={
            "success": True,
            "texte": texte_complet,
            "confiance": round(confiance_globale, 2),
            "mots_positions": mots_avec_positions,
        })

    except Exception as e:
        logger.exception("Erreur lors de l'extraction OCR")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

    finally:
        os.unlink(chemin_tmp)
        shutil.rmtree(dossier_requete, ignore_errors=True)