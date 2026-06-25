"""
Module Pipeline — Orchestration principale du module de vérification de contrats RH
IMRASOFT — PFA 2026

Flux de traitement :
1. Chargement du document PDF                    (ocr.py)
2. Prétraitement image OpenCV                    (ocr.py)
3. Extraction texte DocTR                        (ocr.py)
4. Extraction champs LLM Qwen 2.5 7B            (llm.py)
5. Comparaison avec donnees RH fournies          (comparaison.py)
6. Calcul score et decision metier               (scoring.py)
7. Mise a jour statut API RH                     (api_rh.py)
"""

import ssl
import time

from ocr import charger_document, pretraiter_image, extraire_texte_ocr
from llm import extraire_champs_llm
from comparaison import comparer_champs
from scoring import calculer_score
from api_rh import mettre_a_jour_statut

ssl._create_default_https_context = ssl._create_unverified_context

# Champs critiques universels — toujours presents dans tout type de contrat
CHAMPS_CRITIQUES_UNIVERSELS = [
    "full_name", "cin", "salary",
    "start_date", "company_name",
    "representer", "representer_job"
]


def verifier_contrat_avec_donnees(id_contrat, texte_ocr, champs_rh):
    """
    Verifie le contrat avec les donnees RH fournies directement par la plateforme.
    Pas d'appel GET a l'API RH — les donnees arrivent en parametre.

    Etapes :
    1. Extraction des champs via LLM
    2. Verification des champs illisibles
    3. Comparaison champ par champ
    4. Calcul du score et decision
    5. Mise a jour du statut dans l'API RH

    Retourne dict {statut, score_global, motif}
    """
    contract_type = champs_rh.get("contract_type", "inconnu")

    # Extraction des champs via LLM
    champs_ocr = extraire_champs_llm(texte_ocr)

    # Verification des champs critiques universels illisibles
    champs_illisibles = [
        c for c in CHAMPS_CRITIQUES_UNIVERSELS
        if c not in champs_ocr or champs_ocr[c] in [None, ""]
    ]

    if champs_illisibles:
        decision = {
            "statut": "En revision",
            "score_global": 0,
            "motif": (
                f"Champs illisibles sur le scan : {', '.join(champs_illisibles)}. "
                f"Merci de re-soumettre un scan de meilleure qualite."
            )
        }
        mettre_a_jour_statut(id_contrat, decision["statut"], decision["motif"])
        return decision

    # Comparaison champ par champ
    resultats = comparer_champs(champs_ocr, champs_rh)

    print("\n=== CHAMPS EXTRAITS PAR LE LLM ===")
    for cle, valeur in champs_ocr.items():
        print(f"  {cle}: {valeur}")

    print("\n=== COMPARAISON CHAMP PAR CHAMP ===")
    for champ, detail in resultats.items():
        statut = "OK" if detail["conforme"] else "NON CONFORME"
        print(f"  [{statut}] {champ}: ocr='{detail['valeur_ocr']}' | "
              f"rh='{detail['valeur_rh']}' | score={detail['score']:.1f}%")

    # Calcul du score et decision
    decision = calculer_score(resultats, contract_type)

    # Mise a jour du statut dans l'API RH
    mettre_a_jour_statut(id_contrat, decision["statut"], decision["motif"])

    return decision


def pipeline_complet_avec_donnees(chemin_fichier, id_contrat, champs_rh):
    """
    Pipeline complet de verification d'un contrat RH scanne.
    Les donnees RH sont fournies directement par la plateforme.

    Parametres :
        chemin_fichier : chemin vers le PDF ou l'image du contrat scanne
        id_contrat     : identifiant du contrat dans le systeme RH
        champs_rh      : dictionnaire des donnees RH envoyees par la plateforme

    Retourne : dict {statut, score_global, motif}
    """
    debut = time.time()

    # Etape 1 — Chargement du document
    images = charger_document(chemin_fichier)
    if images is None:
        return {
            "statut": "Rejeté",
            "score_global": 0,
            "motif": "Format de fichier non supporte"
        }

    # Etape 2 — Pretraitement + OCR
    texte_complet = ""
    confiances = []

    for image in images:
        image_pretraitee = pretraiter_image(image)
        texte_page, conf = extraire_texte_ocr(image_pretraitee)
        texte_complet += texte_page
        if conf > 0:
            confiances.append(conf)

    # Etape 3 — Evaluation de la qualite OCR
    confiance_globale = sum(confiances) / len(confiances) if confiances else 0
    print(f"Confiance OCR globale : {confiance_globale:.2f}")

    if confiance_globale < 0.45 or len(texte_complet.strip()) < 50:
        decision = {
            "statut": "Rejeté",
            "score_global": 0,
            "motif": "Scan inexploitable — qualite de lecture insuffisante, veuillez resoumettre un meilleur scan"
        }
        print(f"\nResultat final :")
        print(f"Statut : {decision['statut']}")
        print(f"Motif  : {decision['motif']}")
        duree = time.time() - debut
        print(f"\nDuree totale : {duree:.2f} secondes")
        return decision

    # Etape 4 — Verification des champs
    decision = verifier_contrat_avec_donnees(id_contrat, texte_complet, champs_rh)

    # Affichage du resultat final
    print(f"\nResultat final :")
    print(f"Statut       : {decision['statut']}")
    print(f"Score global : {decision['score_global']}%")
    if decision["motif"]:
        print(f"Motif        : {decision['motif']}")

    duree = time.time() - debut
    print(f"\nDuree totale de traitement : {duree:.2f} secondes")
    return decision