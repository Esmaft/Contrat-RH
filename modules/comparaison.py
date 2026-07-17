"""
Module Comparaison — Comparaison des champs OCR avec les données RH
Utilise RapidFuzz pour la comparaison floue des champs textuels
"""

import re
import unicodedata
from datetime import datetime
from rapidfuzz import fuzz


MOIS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12
}

CHAMPS_DATE = ["start_date", "end_date", "birth_date"]


def normaliser_date(date_str):
    """
    Convertit différents formats de date (ISO, JJ/MM/AAAA, ou français en toutes lettres)
    en objet date comparable. Retourne None si le format n'est pas reconnu.
    """
    if not date_str:
        return None

    date_str = str(date_str).strip().lower()

    # Formats numériques courants
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # Format français en toutes lettres : "1er juillet 2026", "26 juin 2026"
    match = re.match(r"(\d{1,2})(?:er)?\s+(\w+)\s+(\d{4})", date_str)
    if match:
        jour, mois_nom, annee = match.groups()
        mois_num = MOIS_FR.get(mois_nom)
        if mois_num:
            try:
                return datetime(int(annee), mois_num, int(jour)).date()
            except ValueError:
                pass

    return None


def dates_identiques(date_rh, date_ocr):
    """
    Compare deux dates en les normalisant d'abord. Si l'une des deux ne peut pas
    être parsée (format inconnu), retourne False — préfère un rejet explicite
    plutôt qu'une comparaison de string trompeuse.
    """
    d1 = normaliser_date(date_rh)
    d2 = normaliser_date(date_ocr)
    if d1 is None or d2 is None:
        return False
    return d1 == d2


def normaliser_texte(texte):
    """
    Supprime les accents et met en minuscules pour une comparaison robuste.
    Exemple : "Directeur Général" → "directeur general"
    """
    texte = str(texte).lower().strip()
    texte = unicodedata.normalize('NFD', texte)
    texte = ''.join(c for c in texte if unicodedata.category(c) != 'Mn')
    return texte


def comparer_champs(champs_ocr, champs_rh):
    """
    Compare les champs extraits par OCR/LLM avec les données du système RH.

    Types de comparaison selon le champ :
    - Dates       : start_date, end_date, birth_date → normalisation puis comparaison stricte
    - Exacts      : CIN, CNSS, type de contrat → comparaison stricte de texte
    - Tolérants   : adresse, représentant, capital → RapidFuzz ou tolérance %
    - Textuels    : nom salarié, nom société → token_sort_ratio ≥ 95%

    Retourne un dictionnaire de résultats par champ.
    """
    resultats = {}
    champs_exacts_texte = ["cin", "cnss", "contract_type"]
    champs_tolerants = ["cin_address", "representer", "representer_job", "company_capital"]

    for champ, valeur_ocr in champs_ocr.items():
        if champ not in champs_rh:
            continue
        valeur_rh = champs_rh[champ]

        # Salaire — comparaison exacte (pas de tolérance)
        if champ == "salary":
            try:
                conforme = int(valeur_ocr) == int(valeur_rh)
            except (ValueError, TypeError):
                conforme = str(valeur_ocr) == str(valeur_rh)
            score = 100 if conforme else 0

        # Dates — normalisation avant comparaison (corrige le bug de format)
        elif champ in CHAMPS_DATE:
            conforme = dates_identiques(valeur_rh, valeur_ocr)
            score = 100 if conforme else 0

        # Champs exacts texte — CIN, CNSS, type de contrat
        elif champ in champs_exacts_texte:
            if champ == "contract_type":
                conforme = str(valeur_ocr).strip().upper() == str(valeur_rh).strip().upper()
            else:
                conforme = str(valeur_ocr).strip() == str(valeur_rh).strip()
            score = 100 if conforme else 0

        # Champs tolérants — similarité partielle ou comparaison numérique
        elif champ in champs_tolerants:
            if champ == "company_capital":
                try:
                    val_ocr = int(str(valeur_ocr).replace(" ", "").replace(",", "").split(".")[0])
                    val_rh = int(str(valeur_rh).replace(" ", "").replace(",", "").split(".")[0])
                    diff_pct = abs(val_ocr - val_rh) / max(val_rh, 1) * 100
                    conforme = diff_pct <= 5  # tolérance 5% sur le capital
                    score = 100 if conforme else 0
                except (ValueError, TypeError):
                    score = fuzz.partial_ratio(str(valeur_ocr).lower(), str(valeur_rh).lower())
                    conforme = score >= 80

            elif champ in ["representer", "representer_job"]:
                # token_sort_ratio avec normalisation des accents
                # Évite les faux positifs sur prénom commun (ex: Hicham Raai ≠ Hicham Benabdellah)
                score = fuzz.token_sort_ratio(
                    normaliser_texte(valeur_ocr),
                    normaliser_texte(valeur_rh)
                )
                conforme = score >= 85

            else:
                # cin_address — partial_ratio pour les adresses longues
                score = fuzz.partial_ratio(
                    normaliser_texte(valeur_ocr),
                    normaliser_texte(valeur_rh)
                )
                conforme = score >= 80

        # Nom salarié, nom société — token_sort_ratio strict
        else:
            score = fuzz.token_sort_ratio(
                normaliser_texte(valeur_ocr),
                normaliser_texte(valeur_rh)
            )
            conforme = score >= 95

        resultats[champ] = {
            "valeur_ocr": valeur_ocr,
            "valeur_rh": valeur_rh,
            "score": score,
            "conforme": conforme
        }

    return resultats


def verifier_coherence_representant(resultats):
    """
    Vérifie la cohérence du représentant :
    Même nom + fonction différente → incohérence → Rejeté.
    Les variations de formulation tolérées par RapidFuzz ne déclenchent pas d'incohérence.
    """
    if "representer" in resultats and "representer_job" in resultats:
        nom_conforme = resultats["representer"]["conforme"]
        job_conforme = resultats["representer_job"]["conforme"]
        if nom_conforme and not job_conforme:
            return {
                "incoherence": True,
                "motif": (
                    f"Incohérence : le représentant '{resultats['representer']['valeur_ocr']}' "
                    f"a la fonction '{resultats['representer_job']['valeur_ocr']}' dans le contrat "
                    f"mais '{resultats['representer_job']['valeur_rh']}' dans le système RH"
                )
            }
    return {"incoherence": False, "motif": None}