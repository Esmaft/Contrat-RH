"""
Module API RH — Communication avec la plateforme RH IMRASOFT
Gère uniquement la mise à jour du statut (PATCH)
Les données RH sont reçues directement depuis la plateforme — pas de GET nécessaire.
"""

import requests

API_BASE_URL = "http://127.0.0.1:8001"


def mettre_a_jour_statut(id_contrat, statut, motif=None):
    """
    Met à jour le statut d'un contrat dans le système RH.
    Statuts possibles : 'valide', 'Rejeté', 'En révision', 'Erreur'
    """
    
    payload = {
        "id_contrat": id_contrat,
        "statut": statut,
        "motif": motif
    }
    try:
        requests.patch(
            f"{API_BASE_URL}/version1/contrats/statut",
            json=payload
        )
    except Exception as e:
        pass  