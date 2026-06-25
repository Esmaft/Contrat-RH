"""
Module LLM — Extraction des champs du contrat via Qwen 2.5 7B (Ollama)
Utilise un LLM local pour extraire les données structurées depuis le texte OCR
"""

import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODELE_LLM = "qwen2.5:7b"


def extraire_champs_llm(texte_ocr):
    """
    Envoie le texte OCR au LLM Qwen et extrait les champs du contrat.
    Retourne un dictionnaire des champs extraits et nettoyés.
    """
    prompt = f"""Tu es un assistant d'extraction de données de contrats de travail marocains.
Lis attentivement le contrat et extrais TOUS les champs suivants. Cherche bien dans tout le texte.

- contract_type : "CDI", "CDD" ou "stage" (déduis-le du titre)
- company_name : nom de la société
- company_capital : capital social (nombre uniquement, ou null)
- representer : nom de la personne qui représente la société, SANS civilité.
  Cherche après : "représentée par", "représentée aux fins des présentes par",
  "Représentée par :", "représentant légal :", "Signature de l'employeur"
- representer_job : fonction du représentant, SANS civilité.
  Cherche après : "en qualité de", "agissant en qualité de",
  "En qualité de :", "qualité :", "en sa qualité de"
- full_name : nom et prénom du salarié ou stagiaire, SANS la civilité "Monsieur"/"Madame"/"M."
- cin : numéro de carte d'identité nationale (après "Carte Nationale d'Identité" ou "CIN")
- cin_address : adresse du domicile du salarié.
  Cherche après : "demeurant au", "demeurant à",
  "Adresse CIN de salarié :", "Adress CIN de salarié :", "domicilié au"
- cnss : numéro CNSS DU SALARIÉ uniquement (PAS celui de la société). Mets null si absent.
- birth_date : date de naissance au format JJ/MM/AAAA (cherche après "né le" ou "née le")
- salary : salaire ou indemnité total mensuel brut (nombre uniquement).
  ATTENTION : prendre le TOTAL (ex: 8500), pas les composantes individuelles.
  "2 500,00" = 2500, "12 500,00" = 12500, "3 750,00" = 3750.
- start_date : date de début au format JJ/MM/AAAA
- end_date : date de fin au format JJ/MM/AAAA (ou null si CDI)

IMPORTANT : cherche chaque champ dans tout le texte. Mets null UNIQUEMENT si vraiment absent.

Contrat :
{texte_ocr}

Réponds uniquement avec le JSON."""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODELE_LLM,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "seed": 42}
        }
    )

    resultat = response.json()["response"]
    champs = json.loads(resultat)
    return _nettoyer_champs(champs)


def _nettoyer_champs(champs):
    """
    Nettoie et normalise les champs extraits par le LLM :
    - Corrige les clés mal orthographiées
    - Nettoie les valeurs numériques (salary, company_capital)
    - Supprime les civilités des noms
    """
    corrections_cles = {
        "representeur_job": "representer_job",
        "representant_job": "representer_job",
        "representer_poste": "representer_job",
        "representeur": "representer",
        "representant": "representer",
    }

    champs_propres = {}
    for cle, valeur in champs.items():
        cle = corrections_cles.get(cle, cle)

        if valeur is not None and valeur != "":
            if cle in ["salary", "company_capital"]:
                valeur_nettoyee = str(valeur).replace(" ", "").replace(".", "").split(",")[0]
                valeur_nettoyee = "".join(c for c in valeur_nettoyee if c.isdigit())
                if valeur_nettoyee:
                    champs_propres[cle] = int(valeur_nettoyee)
            elif cle in ["full_name", "representer"]:
                nom = str(valeur)
                for civilite in ["Monsieur ", "Madame ", "M. ", "Mme ", "Mlle "]:
                    nom = nom.replace(civilite, "")
                champs_propres[cle] = nom.strip()
            else:
                champs_propres[cle] = valeur

    return champs_propres
