import sys
import os
import tempfile
import json

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse

sys.path.append(os.path.join(os.path.dirname(__file__), "modules"))
from pipeline import pipeline_complet_avec_donnees

app = FastAPI(title="API Verification Contrats RH", version="1.0")


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

        # Extraire l'id_contrat depuis les donnees RH
        id_contrat = champs_rh.get("id_contrat", "inconnu")

        resultat = pipeline_complet_avec_donnees(chemin_tmp, id_contrat, champs_rh)
        return JSONResponse(content={
            "success": True,
            "id_contrat": id_contrat,
            "statut": resultat["statut"],
            "score_global": resultat["score_global"],
            "motif": resultat["motif"]
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )
    finally:
        os.unlink(chemin_tmp)


@app.get("/")
def health_check():
    return {"status": "API en ligne", "version": "1.0"}