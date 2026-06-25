from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from fastapi import HTTPException

app = FastAPI()

# Base de données simulée des contrats RH
contrats_db = {
    "001": {
    "id_contrat": "001",
    "contract_type": "CDD",
    "company_name": "IMRASOFT SARL",
    "company_capital": "100000",
    "representer": "Mohammed Bennani",
    "representer_job": "Gérant",
    "full_name": "Ahmed Alami",
    "cin": "AB123456",
    "cin_address": "Rue des Fleurs, Agadir",
    "cnss": "123456789",
    "birth_date": "12/03/1990",
    "salary": 8500,
    "start_date": "01/09/2024",
    "end_date": "01/03/2025",
    "statut": "En attente"
},
    "002": {
        "id_contrat": "002",
        "company_name": "IMRASOFT SARL",
        "company_capital": "100000",
        "representer": "Mohammed Bennani",
        "representer_job": "Gérant",
        "full_name": "Ahmed Alami",
        "cin": "CD789012",
        "cin_address": "Avenue Hassan II, Agadir",
        "cnss": "987654321",
        "birth_date": "25/06/1995",
        "salary": 8500,
        "start_date": "01/06/2024",
        "end_date": "01/06/2025",
        "statut": "En attente"
    },
"003": {
    "id_contrat": "003",
    "contract_type": "CDD",
    "company_name": "NORDIS TEXTILE SARL",
    "company_capital": "1200000",
    "representer": "Hicham Benabdellah",
    "representer_job": "Directeur General",
    "full_name": "Youssef Idrissi",
    "cin": "T412095",
    "cin_address": "9, Rue Ibn Battouta, Quartier Mesnana, 90020 Tanger",
    "cnss": "4471236590",
    "birth_date": "22/09/1999",
    "salary": 3750,
    "start_date": "01/07/2026",
    "end_date": "31/12/2026",
    "statut": "En attente"
},
"004": {
    "id_contrat": "004",
    "contract_type": "CDI",
    "company_name": "ATLAS DIGITAL SOLUTIONS SARL",
    "company_capital": "500000",
    "representer": "Karim Benchekroun",
    "representer_job": "Gerant",
    "full_name": "Salma El Ouazzani",
    "cin": "EA582147",
    "cin_address": "17, Rue des Orangers, Résidence Al Manar, Appartement 4, 40000 Marrakech",
    "cnss": "3357821094",
    "birth_date": "14/03/1996",
    "salary": 12500,
    "start_date": "01/07/2026",
    "end_date": None,
    "statut": "En attente"
},
"005": {
    "id_contrat": "005",
    "contract_type": "stage",
    "company_name": "TECHNOVA CONSULTING SARL",
    "company_capital": None,
    "representer": "Adil Mansouri",
    "representer_job": "associé gérant",
    "full_name": "Mehdi Tazi",
    "cin": "BK294613",
    "cin_address": "12, Rue Oued Sebou, Agdal, 10090 Rabat",
    "cnss": None,
    "birth_date": "08/02/2002",
    "salary": 2500,
    "start_date": "01/07/2026",
    "end_date": "31/08/2026",
    "statut": "En attente"
},
"006": {
    "id_contrat": "006",
    "contract_type": "CDD",
    "company_name": "SOFTECH MAROC SARL",
    "company_capital": "500000",
    "representer": "Rachid Benali",
    "representer_job": "Directeur General",
    "full_name": "Khalid Ouali",
    "cin": "BJ847293",
    "cin_address": "23, Rue Al Massira, Gueliz, 40000 Marrakech",
    "cnss": "7834521096",
    "birth_date": "15/03/1995",
    "salary": 6500,
    "start_date": "01/07/2026",
    "end_date": "03/01/2027",
    "statut": "En attente"
}
}

# Modèle pour la mise à jour du statut
class StatutUpdate(BaseModel):
    id_contrat: str
    statut: str
    motif: Optional[str] = None

# API 1 — Récupérer les données du contrat par ID

@app.get("/api/version1/contrat/{id_contrat}")
def get_contrat(id_contrat: str):
    if id_contrat in contrats_db:
        return {"success": True, "data": contrats_db[id_contrat]}
    raise HTTPException(status_code=404, detail=f"Contrat non trouvé : {id_contrat}")

# API 2 — Mettre à jour le statut du contrat
@app.patch("/version1/contrats/statut")
@app.patch("/version1/contrats/statut")
def update_statut(update: StatutUpdate):
    print("\n=== MISE A JOUR RECUE ===")
    print(f"Contrat : {update.id_contrat}")
    print(f"Statut  : {update.statut}")
    print(f"Motif   : {update.motif}")

    if update.id_contrat in contrats_db:
        contrats_db[update.id_contrat]["statut"] = update.statut
        contrats_db[update.id_contrat]["motif"] = update.motif

        print("✓ Statut mis à jour")

        return {
            "success": True,
            "message": f"Statut mis à jour : {update.statut}",
            "id_contrat": update.id_contrat
        }

    print("✗ Contrat introuvable")

    return {
        "success": False,
        "message": f"Contrat non trouvé : {update.id_contrat}"
    }

# API 3 — Lister tous les contrats (pour debug)
@app.get("/api/version1/contrats")
def get_all_contrats():
    return {"success": True, "data": contrats_db}

