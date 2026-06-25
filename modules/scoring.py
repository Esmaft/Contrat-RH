"""
Module Scoring — Moteur de décision et calcul du score global
Applique les règles métier pour décider : Validé / Rejeté / En révision
"""

from comparaison import verifier_coherence_representant


def calculer_score(resultats, contract_type="CDD"):
    """
    Calcule le score global et détermine le statut du contrat.

    Logique de décision (par priorité) :
    1. Champ critique non conforme  → Rejeté  (score 0)
    2. Incohérence représentant     → Rejeté  (score 0)
    3. Champ non critique divergent → En révision
    4. Tout conforme                → Validé

    Champs critiques universels (tous types de contrats) :
        full_name, cin, birth_date, salary, start_date,
        cnss, company_name, contract_type, representer

    Champs critiques supplémentaires pour CDD et stage :
        end_date
    """
    champs_critiques = [
        "full_name", "cin", "birth_date", "salary",
        "start_date", "cnss", "company_name",
        "contract_type", "representer"
    ]
    if contract_type in ["CDD", "stage"]:
        champs_critiques.append("end_date")

    # 1. Champs critiques non conformes → Rejeté
    champs_critiques_non_conformes = [
        champ for champ in champs_critiques
        if champ in resultats and not resultats[champ]["conforme"]
    ]
    if champs_critiques_non_conformes:
        return {
            "statut": "Rejeté",
            "score_global": 0,
            "motif": f"Champs critiques non conformes : {', '.join(champs_critiques_non_conformes)}"
        }

    # 2. Incohérence représentant → Rejeté
    coherence = verifier_coherence_representant(resultats)
    if coherence["incoherence"]:
        return {
            "statut": "Rejeté",
            "score_global": 0,
            "motif": coherence["motif"]
        }

    # 3. Divergences non critiques → En révision
    champs_non_critiques_non_conformes = [
        champ for champ, detail in resultats.items()
        if champ not in champs_critiques and not detail["conforme"]
    ]
    score_global = sum(d["score"] for d in resultats.values()) / len(resultats)

    if champs_non_critiques_non_conformes:
        return {
            "statut": "En révision",
            "score_global": round(score_global, 2),
            "motif": f"Vérification manuelle requise — divergences sur : {', '.join(champs_non_critiques_non_conformes)}"
        }

    # 4. Tout conforme → Validé
    return {
        "statut": "valide",
        "score_global": round(score_global, 2),
        "motif": None
    }
