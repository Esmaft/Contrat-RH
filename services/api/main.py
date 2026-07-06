"""
Service API — Point d'entrée principal
Reçoit le PDF + données RH et orchestre les services OCR et LLM
"""

import os
import json
import tempfile
import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
import traceback

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "modules"))

from comparaison import comparer_champs
from scoring import calculer_score
from api_rh import mettre_a_jour_statut
from llm import extraire_champs_llm

OCR_SERVICE_URL = os.getenv("OCR_SERVICE_URL", "http://localhost:8001")
SIGNATURE_SERVICE_URL = os.getenv("SIGNATURE_SERVICE_URL", "http://localhost:8002")  # ← NOUVEAU

app = FastAPI(title="API Verification Contrats RH", version="1.0")

CHAMPS_CRITIQUES_UNIVERSELS = [
    "full_name", "cin", "salary",
    "start_date", "company_name",
    "representer", "representer_job"
]


@app.get("/")
def health_check():
    return {"status": "API en ligne", "version": "1.0"}


@app.post("/api/version1/verify")
async def verifier_contrat(
    fichier: UploadFile = File(...),
    donnees_rh: str = Form(...)
):
    # Sauvegarder le PDF temporairement
    suffix = os.path.splitext(fichier.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contenu = await fichier.read()
        tmp.write(contenu)
        chemin_tmp = tmp.name

    try:
        champs_rh = json.loads(donnees_rh)
        id_contrat = champs_rh.get("id_contrat", "inconnu")
        contract_type = champs_rh.get("contract_type", "inconnu")

        # Étape 1 — Appel service OCR
        with open(chemin_tmp, "rb") as f:
            ocr_response = requests.post(
                f"{OCR_SERVICE_URL}/extract",
                files={"fichier": (fichier.filename, f, "application/pdf")}
            )

        ocr_result = ocr_response.json()

        if not ocr_result["success"]:
            return JSONResponse(status_code=500, content={
                "success": False,
                "error": ocr_result.get("error", "Erreur OCR")
            })

        texte_ocr = ocr_result["texte"]
        confiance = ocr_result["confiance"]

        # Étape 2 — Vérification qualité OCR
        if confiance < 0.45 or len(texte_ocr.strip()) < 50:
            return JSONResponse(content={
                "success": True,
                "id_contrat": id_contrat,
                "statut": "Rejete",
                "score_global": 0,
                "motif": "Scan inexploitable — resoumettre un meilleur scan"
            })
        
        # Étape 3 — Vérification signature (avant LLM !) ← NOUVEAU
        with open(chemin_tmp, "rb") as f:
            sig_response = requests.post(
                f"{SIGNATURE_SERVICE_URL}/detect",
                files={"fichier": (fichier.filename, f, "application/pdf")}
            )
        sig_result = sig_response.json()
        signature_detectee = sig_result.get("signature_detectee", False)

        if not signature_detectee:
            decision = {
                "statut": "Rejete",
                "score_global": 0,
                "motif": "Aucune signature détectée — contrat non signé"
            }
            mettre_a_jour_statut(id_contrat, decision["statut"], decision["motif"])
            return JSONResponse(content={
                "success": True,
                "id_contrat": id_contrat,
                **decision
            })
        # Étape 4 — Extraction champs via LLM
        champs_ocr = extraire_champs_llm(texte_ocr)

        # Étape 5 — Vérification champs illisibles
        champs_illisibles = [
            c for c in CHAMPS_CRITIQUES_UNIVERSELS
            if c not in champs_ocr or champs_ocr[c] in [None, ""]
        ]

        if champs_illisibles:
            decision = {
                "statut": "En revision",
                "score_global": 0,
                "motif": f"Champs illisibles : {', '.join(champs_illisibles)}. Resoumettre un meilleur scan."
            }
            mettre_a_jour_statut(id_contrat, decision["statut"], decision["motif"])
            return JSONResponse(content={
                "success": True,
                "id_contrat": id_contrat,
                **decision
            })

        # Étape 6 — Comparaison et scoring
        resultats = comparer_champs(champs_ocr, champs_rh)
        decision = calculer_score(resultats, contract_type)
        mettre_a_jour_statut(id_contrat, decision["statut"], decision["motif"])

        return JSONResponse(content={
            "success": True,
            "id_contrat": id_contrat,
            "statut": decision["statut"],
            "score_global": decision["score_global"],
            "motif": decision["motif"]
        })

    except Exception as e:
        print(traceback.format_exc())  
        return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(e)}
    )
    finally:
        os.unlink(chemin_tmp)