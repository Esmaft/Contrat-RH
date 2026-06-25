"""
Module Comparaison — Comparaison des champs OCR avec les données RH
Utilise RapidFuzz pour la comparaison floue des champs textuels
"""

import unicodedata
from rapidfuzz import fuzz


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

    Trois types de comparaison selon le champ :
    - Exacts      : dates, CIN, CNSS, type de contrat → comparaison stricte
    - Tolérants   : adresse, représentant, capital → RapidFuzz ou tolérance %
    - Textuels    : nom salarié, nom société → token_sort_ratio ≥ 95%

    Retourne un dictionnaire de résultats par champ.
    """
    resultats = {}
    champs_exacts = ["start_date", "end_date", "birth_date", "cin", "cnss", "contract_type"]
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

        # Champs exacts — comparaison stricte (dates, CIN, CNSS, type contrat)
        elif champ in champs_exacts:
            if champ == "contract_type":
                conforme = str(valeur_ocr).strip().upper() == str(valeur_rh).strip().upper()
            else:
                # Toutes les dates comparées de façon stricte
                # Si l'OCR lit mal une date → le contrat doit être ressoumis
                conforme = str(valeur_ocr) == str(valeur_rh)
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
