"""
Module Identification des Signataires
=======================================

Determine automatiquement, pour chaque signature detectee sur un contrat,
a quel role elle correspond (employe, representant de l'entreprise, ou
tout autre role additionnel declare -- garant, temoin, etc.) -- sans
saisie manuelle : les noms attendus proviennent tous de donnees_rh.

Principe general
-----------------
1. Le service Signature (YOLOv8) fournit la position (x, y) normalisee de
   chaque signature detectee, ainsi que le numero de page ou elle se trouve.
2. Le service OCR (DocTR) fournit la position (x, y) normalisee de chaque
   mot reconnu sur le document.
3. Pour chaque signature, on cherche geometriquement le nom le plus proche
   (fenetre glissante de 2 mots), puis on verifie que ce texte correspond
   suffisamment a chacun des noms attendus (RapidFuzz), et on retient le
   role dont le nom correspond le mieux.
4. Verification renforcee : chaque token du nom (prenom ET nom de famille)
   doit etre retrouve individuellement a proximite, pour eviter les faux
   positifs par simple coincidence de sous-chaine.

Roles et regle d'acceptation
------------------------------
Les roles attendus sont fournis sous forme d'un dictionnaire
{nom_du_role: nom_de_la_personne}, par exemple :
    {"employe": "Youssef Idrissi", "entreprise": "Hicham Benabdellah",
     "garant": "Amine Ziani"}

- Le role "employe" est TOUJOURS obligatoire.
- Tout autre role n'est obligatoire QUE SI son nom est non vide dans le
  dictionnaire -- ainsi, un contrat sans garant declare (champ absent ou
  vide dans donnees_rh) n'exigera pas de signature de garant, mais un
  contrat qui en declare un verra cette signature verifiee comme les
  autres, automatiquement, sans saisie manuelle supplementaire.

Limites connues (documentees, non resolues par design)
--------------------------------------------------------
- Si l'encre d'une signature manuscrite recouvre physiquement une partie
  du nom imprime, l'OCR peut echouer a lire ce mot correctement. Un score
  de similarite globale tres eleve (>= SEUIL_SCORE_FORT) sert alors de
  filet de secours, meme sans couverture complete des tokens. Ce seuil a
  ete calibre sur un nombre limite d'exemples reels et pourrait necessiter
  un ajustement avec davantage de donnees.
"""

from rapidfuzz import fuzz
import unicodedata

RAYON_RECHERCHE = 0.15
SEUIL_SIMILARITE = 65
SEUIL_TOKEN = 65
SEUIL_SCORE_FORT = 80
TOLERANCE_SOUS_SIGNATURE = 0.015
TOLERANCE_SOUS_SIGNATURE_TOKEN = 0.05

ROLE_OBLIGATOIRE = "employe"  


def normaliser_texte(texte):
    """Minuscules et suppression des accents, pour une comparaison robuste."""
    texte = str(texte).lower().strip()
    texte = unicodedata.normalize('NFD', texte)
    return ''.join(c for c in texte if unicodedata.category(c) != 'Mn')


def _distance(x1, y1, x2, y2):
    return ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5


def _fenetres_de_mots(mots_positions, taille_fenetre=2):
    candidats = []
    n = len(mots_positions)
    if n < taille_fenetre:
        return candidats
    for i in range(n - taille_fenetre + 1):
        fenetre = mots_positions[i:i + taille_fenetre]
        if len({m["page"] for m in fenetre}) > 1:
            continue
        candidats.append({
            "texte": " ".join(m["mot"] for m in fenetre),
            "x_center": sum(m["x_center"] for m in fenetre) / len(fenetre),
            "y_center": sum(m["y_center"] for m in fenetre) / len(fenetre),
            "page": fenetre[0]["page"]
        })
    return candidats


def _fenetres_proches(x_sig, y_sig, page_sig, fenetres, rayon_max,
                       tolerance_dessous=TOLERANCE_SOUS_SIGNATURE):
    proches = []
    for f in fenetres:
        if f["page"] != page_sig or f["y_center"] > y_sig + tolerance_dessous:
            continue
        d = _distance(x_sig, y_sig, f["x_center"], f["y_center"])
        if d <= rayon_max:
            proches.append((d, f))
    proches.sort(key=lambda t: t[0])
    return proches


def _mots_individuels_proches(x_sig, y_sig, page_sig, mots_positions, rayon_max,
                               tolerance_dessous=TOLERANCE_SOUS_SIGNATURE_TOKEN):
    proches = []
    for m in mots_positions:
        if m["page"] != page_sig or m["y_center"] > y_sig + tolerance_dessous:
            continue
        if _distance(x_sig, y_sig, m["x_center"], m["y_center"]) <= rayon_max:
            proches.append(normaliser_texte(m["mot"]))
    return proches


def _couverture_tous_tokens(mots_proches_norm, nom_cible_norm, seuil_token=SEUIL_TOKEN):
    tokens = [t for t in nom_cible_norm.split() if len(t) >= 2]
    if not tokens or not mots_proches_norm:
        return False
    for tok in tokens:
        meilleur = max((fuzz.ratio(tok, m) for m in mots_proches_norm), default=0)
        if meilleur < seuil_token:
            return False
    return True


def _meilleur_match(proches, nom_cible_norm, seuil_similarite):
    meilleur_texte, meilleur_score, meilleure_distance = None, 0, None
    for d, candidat in proches:
        score = fuzz.partial_ratio(normaliser_texte(candidat["texte"]), nom_cible_norm)
        if score >= seuil_similarite:
            return candidat["texte"], score, d, True
        if score > meilleur_score:
            meilleur_texte, meilleur_score, meilleure_distance = candidat["texte"], score, d
    return meilleur_texte, meilleur_score, meilleure_distance, False


def identifier_signataires(signatures, mots_positions, roles_attendus,
                            rayon_max=RAYON_RECHERCHE, seuil_similarite=SEUIL_SIMILARITE,
                            seuil_token=SEUIL_TOKEN):
    """
    Identifie, pour chaque signature detectee, a quel role elle correspond
    parmi ceux fournis dans roles_attendus.

    Args:
        signatures: liste de dicts {"x_center", "y_center", "confidence", "page"}
        mots_positions: liste de dicts {"mot", "x_center", "y_center", "page"}
        roles_attendus: dict {nom_du_role: nom_de_la_personne}, ex:
            {"employe": "Youssef Idrissi", "entreprise": "Hicham Benabdellah"}
            Un role dont le nom est vide/absent n'est pas exige (sauf
            ROLE_OBLIGATOIRE, toujours requis).

    Returns:
        (bool, str|None, list[dict]): (validite, motif de rejet, detail par signature)
    """
    if not signatures:
        return False, "Aucune signature detectee sur le document", []

    roles_a_verifier = {
        role: nom for role, nom in roles_attendus.items()
        if str(nom).strip() or role == ROLE_OBLIGATOIRE
    }

    fenetres = _fenetres_de_mots(mots_positions)
    roles_normalises = {role: normaliser_texte(nom) for role, nom in roles_a_verifier.items()}

    detail = []
    for sig in signatures:
        page_sig = sig.get("page", max((m["page"] for m in mots_positions), default=0))

        proches = _fenetres_proches(sig["x_center"], sig["y_center"], page_sig, fenetres, rayon_max)
        mots_proches_norm = _mots_individuels_proches(
            sig["x_center"], sig["y_center"], page_sig, mots_positions, rayon_max + 0.05
        )

        # Calcule le match de cette signature contre CHAQUE role attendu,
        # et retient celui dont le nom correspond le mieux (score le plus haut).
        scores_par_role = {}
        for role, nom_norm in roles_normalises.items():
            texte, score, dist, brut = _meilleur_match(proches, nom_norm, seuil_similarite)
            couverture = _couverture_tous_tokens(mots_proches_norm, nom_norm, seuil_token)
            match = brut and (couverture or score >= SEUIL_SCORE_FORT)
            scores_par_role[role] = {
                "nom_trouve": texte, "distance": dist, "score": score,
                "couverture_tokens": couverture, "correspond": match,
            }

        roles_matches = [r for r, v in scores_par_role.items() if v["correspond"]]
        if roles_matches:
            role_retenu = min(roles_matches, key=lambda r: scores_par_role[r]["distance"] or 0)
        else:
            role_retenu = "inconnu"

        detail.append({
            **sig,
            "role": role_retenu,
            "matches_par_role": {
                role: {
                    "nom_trouve": v["nom_trouve"],
                    "distance": round(v["distance"], 4) if v["distance"] is not None else None,
                    "score": round(v["score"], 1),
                    "correspond": v["correspond"],
                }
                for role, v in scores_par_role.items()
            },
        })

    # Chaque role a verifier doit etre matche par AU MOINS une signature.
    for role in roles_a_verifier:
        role_trouve = any(
            d["matches_par_role"].get(role, {}).get("correspond") for d in detail
        )
        if not role_trouve:
            libelle = "l'employe" if role == ROLE_OBLIGATOIRE else f"du role '{role}'"
            return False, f"Signature de {libelle} manquante ou non identifiee", detail

    return True, None, detail