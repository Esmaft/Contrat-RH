"""
Service API principal -- Orchestration de la verification de contrats RH
===========================================================================
Port 8000.

Ce service est appele DIRECTEMENT par la plateforme RH IMRASOFT, qui
envoie le contrat (PDF) et les donnees RH attendues (donnees_rh), puis
recoit le statut final directement dans la reponse JSON de cet endpoint
(statut, score_global, motif). Aucun appel retour (callback/PATCH) vers
la plateforme n'est necessaire : la reponse HTTP EST le canal de
communication du statut.

Pipeline (ordre optimise pour la performance) :
  1. Detection de signature (rapide) -> rejet immediat si absente
  2. OCR (texte + position des mots)
  3. Identification des signataires (employe / representant / roles additionnels)
  4. Extraction des champs via LLM (uniquement si signature confirmee)
  5. Verification des champs illisibles
  6. Comparaison avec donnees_rh et scoring final

Cet ordre evite de lancer l'OCR complet et le LLM (etapes les plus
couteuses) sur un document qui sera de toute facon rejete faute de
signature valide.
"""

import json
import logging
import os
import tempfile
import time

import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "modules"))

from comparaison import comparer_champs
from scoring import calculer_score
from llm import extraire_champs_llm
from identification_signataires import identifier_signataires

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("api_principale")

OCR_SERVICE_URL = os.getenv("OCR_SERVICE_URL", "http://localhost:8001")
SIGNATURE_SERVICE_URL = os.getenv("SIGNATURE_SERVICE_URL", "http://localhost:8002")

CHAMPS_CRITIQUES_UNIVERSELS = [
    "full_name", "cin", "salary", "start_date",
    "company_name", "representer", "representer_job",
]
CONFIANCE_OCR_MIN = 0.45
LONGUEUR_TEXTE_MIN = 50

app = FastAPI(title="API Verification Contrats RH", version="1.3")


@app.get("/")
def health_check():
    return {"status": "API en ligne", "version": "1.3"}


def _rejet(id_contrat, motif, temps_debut, **extra):
    """Construit une reponse de rejet standardisee, retournee directement
    a la plateforme RH appelante (pas d'appel separe necessaire)."""
    return JSONResponse(content={
        "success": True,
        "id_contrat": id_contrat,
        "statut": "Rejete",
        "score_global": 0,
        "motif": motif,
        "temps_traitement": round(time.time() - temps_debut, 2),
        **extra,
    })


@app.post("/api/version1/verify")
async def verifier_contrat(fichier: UploadFile = File(...), donnees_rh: str = Form(...)):
    suffix = os.path.splitext(fichier.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contenu = await fichier.read()
        tmp.write(contenu)
        chemin_tmp = tmp.name

    try:
        champs_rh = json.loads(donnees_rh)
        id_contrat = champs_rh.get("id_contrat", "inconnu")
        contract_type = champs_rh.get("contract_type", "inconnu")
        nom_employe = champs_rh.get("full_name", "")
        nom_representant = champs_rh.get("representer", "")
        nom_garant = champs_rh.get("garant", "")  # optionnel, verifie seulement si renseigne

        roles_attendus = {
            "employe": nom_employe,
            "entreprise": nom_representant,
        }
        if str(nom_garant).strip():
            roles_attendus["garant"] = nom_garant

        t0 = time.time()

        # --- Etape 1 : detection de signature ---
        with open(chemin_tmp, "rb") as f:
            sig_response = requests.post(
                f"{SIGNATURE_SERVICE_URL}/detect",
                files={"fichier": (fichier.filename, f, "application/pdf")},
            )
        sig_result = sig_response.json()
        signatures = sig_result.get("signatures", [])
        t1 = time.time()
        logger.info("Signature : %.2fs", t1 - t0)

        if not signatures:
            return _rejet(id_contrat, "Aucune signature detectee -- contrat non signe", t0)

        # --- Etape 2 : OCR ---
        with open(chemin_tmp, "rb") as f:
            ocr_response = requests.post(
                f"{OCR_SERVICE_URL}/extract",
                files={"fichier": (fichier.filename, f, "application/pdf")},
            )
        ocr_result = ocr_response.json()
        t2 = time.time()
        logger.info("OCR : %.2fs", t2 - t1)

        if not ocr_result["success"]:
            return JSONResponse(status_code=500, content={
                "success": False, "error": ocr_result.get("error", "Erreur OCR")
            })

        texte_ocr = ocr_result["texte"]
        confiance = ocr_result["confiance"]
        mots_positions = ocr_result.get("mots_positions", [])

        if confiance < CONFIANCE_OCR_MIN or len(texte_ocr.strip()) < LONGUEUR_TEXTE_MIN:
            return _rejet(id_contrat, "Scan inexploitable -- resoumettre un meilleur scan", t0)

        # --- Etape 3 : identification des signataires ---
        signatures_ok, motif_signature, detail_signatures = identifier_signataires(
            signatures, mots_positions, roles_attendus
        )
        t3 = time.time()
        logger.info("Identification signataires : %.2fs", t3 - t2)

        if not signatures_ok:
            return _rejet(id_contrat, motif_signature, t0, signatures_detail=detail_signatures)

        # --- Etape 4 : extraction des champs via LLM ---
        champs_ocr = extraire_champs_llm(texte_ocr)
        t4 = time.time()
        logger.info("LLM : %.2fs | Total : %.2fs", t4 - t3, t4 - t0)

        champs_illisibles = [
            c for c in CHAMPS_CRITIQUES_UNIVERSELS
            if c not in champs_ocr or champs_ocr[c] in (None, "")
        ]
        if champs_illisibles:
            motif = f"Champs illisibles : {', '.join(champs_illisibles)}. Resoumettre un meilleur scan."
            return JSONResponse(content={
                "success": True,
                "id_contrat": id_contrat,
                "statut": "En revision",
                "score_global": 0,
                "motif": motif,
                "temps_traitement": round(time.time() - t0, 2),
            })

        # --- Etape 5 : comparaison et scoring ---
        resultats = comparer_champs(champs_ocr, champs_rh)
        decision = calculer_score(resultats, contract_type)

        return JSONResponse(content={
            "success": True,
            "id_contrat": id_contrat,
            "statut": decision["statut"],
            "score_global": decision["score_global"],
            "motif": decision["motif"],
            "signatures_detail": detail_signatures,
            "temps_traitement": round(time.time() - t0, 2),
        })

    except Exception as e:
        logger.exception("Erreur lors de la verification du contrat")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

    finally:
        os.unlink(chemin_tmp)