"""
Service API principal -- Orchestration de la verification de contrats RH
===========================================================================
Port 8000.

SIMPLIFICATION MAJEURE (suite proposition encadrant) :
--------------------------------------------------------
La verification de signature repose maintenant UNIQUEMENT sur le nombre
de signatures detectees par rapport au nombre attendu, fourni directement
par la plateforme RH (nombre_signatures_attendu dans donnees_rh) -- qui
connait deja cette information via son propre template de contrat.

Le module d'identification par nom/libelle (identification_signataires.py)
est retire de la decision : les scores de similarite de texte se sont
averes trop fragiles en conditions reelles (un score de 76.9 au lieu de
80 pouvait faire basculer a tort un contrat valide vers un rejet). Compter
les signatures est une verification beaucoup plus robuste et stable.

Pipeline (ordre optimise pour la performance) :
  1. Detection de signature (rapide) -> rejet immediat si absente
  2. Verification du NOMBRE de signatures par rapport a l'attendu
  3. OCR (texte + positions)
  4. Extraction des champs via LLM
  5. Verification des champs illisibles
  6. Comparaison avec donnees_rh et scoring final
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("api_principale")

OCR_SERVICE_URL = os.getenv("OCR_SERVICE_URL", "http://localhost:8001")
SIGNATURE_SERVICE_URL = os.getenv("SIGNATURE_SERVICE_URL", "http://localhost:8002")

CHAMPS_CRITIQUES_UNIVERSELS = [
    "full_name", "cin", "salary", "start_date",
    "company_name", "representer",
]
CONFIANCE_OCR_MIN = 0.45
LONGUEUR_TEXTE_MIN = 50
NOMBRE_SIGNATURES_PAR_DEFAUT = 1  # repli si la plateforme RH ne fournit pas cette info

app = FastAPI(title="API Verification Contrats RH", version="1.4")


@app.get("/")
def health_check():
    return {"status": "API en ligne", "version": "1.4"}


def _rejet(id_contrat, motif, temps_debut, **extra):
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
        nombre_signatures_attendu = champs_rh.get(
            "nombre_signatures_attendu", NOMBRE_SIGNATURES_PAR_DEFAUT
        )

        t0 = time.time()

        # --- Etape 1 : detection de signature ---
        with open(chemin_tmp, "rb") as f:
            sig_response = requests.post(
                f"{SIGNATURE_SERVICE_URL}/detect",
                files={"fichier": (fichier.filename, f, "application/pdf")},
            )
        sig_result = sig_response.json()
        signatures = sig_result.get("signatures", [])
        nombre_detecte = len(signatures)
        t1 = time.time()
        logger.info("Signature : %.2fs (%d detectee(s), %d attendue(s))",
                    t1 - t0, nombre_detecte, nombre_signatures_attendu)

        if nombre_detecte == 0:
            return _rejet(id_contrat, "Aucune signature detectee -- contrat non signe", t0)

        # --- Etape 2 : verification du NOMBRE de signatures attendu ---
        if nombre_detecte < nombre_signatures_attendu:
            motif = (
                f"Nombre de signatures insuffisant : {nombre_detecte} detectee(s) "
                f"sur {nombre_signatures_attendu} attendue(s)"
            )
            return _rejet(id_contrat, motif, t0, signatures_detail=signatures)

        # --- Etape 3 : OCR ---
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

        if confiance < CONFIANCE_OCR_MIN or len(texte_ocr.strip()) < LONGUEUR_TEXTE_MIN:
            return _rejet(id_contrat, "Scan inexploitable -- resoumettre un meilleur scan", t0)

        # --- Etape 4 : extraction des champs via LLM ---
        champs_ocr = extraire_champs_llm(texte_ocr)
        logger.info("Salaire extrait par le LLM : %s", champs_ocr.get("salary"))
        t3 = time.time()
        logger.info("LLM : %.2fs | Total : %.2fs", t3 - t2, t3 - t0)

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
            "signatures_detail": {
                "nombre_detecte": nombre_detecte,
                "nombre_attendu": nombre_signatures_attendu,
                "signatures": signatures,
            },
            "temps_traitement": round(time.time() - t0, 2),
        })

    except Exception as e:
        logger.exception("Erreur lors de la verification du contrat")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

    finally:
        os.unlink(chemin_tmp)