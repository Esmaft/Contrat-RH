"""
Module Identification des Signataires
=======================================

Determine automatiquement, pour chaque signature detectee sur un contrat,
a quel role elle correspond (employe, representant de l'entreprise, ou
tout autre role additionnel declare -- garant, temoin, etc.) -- sans
saisie manuelle : les noms attendus proviennent tous de donnees_rh.

Strategie a DEUX NIVEAUX (ajoutee suite a un test sur un contrat reel
IMRASOFT dont le bloc de signature ne repete jamais le nom du signataire,
seulement des libelles generiques "L'EMPLOYEUR" / "LE/LA SALARIE(E)") :

  Niveau 1 -- Matching par NOM (methode principale, la plus fiable) :
    cherche le nom de la personne (full_name, representer, etc.) le plus
    proche geometriquement de la signature.

  Niveau 2 -- Matching par LIBELLE DE ROLE (filet de secours) :
    n'est utilise QUE si AUCUN texte ressemblant a un nom n'a ete trouve
    du tout a proximite de la signature (aucun role n'atteint meme un
    score de similarite faible). Dans ce cas seulement, on cherche un
    libelle generique associe au role ("Employeur", "Salarie(e)").

    IMPORTANT (correction suite a regression detectee lors des tests) :
    si un texte ressemblant a un nom EXISTE a proximite mais ne
    correspond a AUCUN nom attendu (ex: mauvais nom, personne differente),
    le Niveau 2 est desactive pour CETTE signature -- on ne bascule pas
    sur un libelle generique juste parce que le nom trouve est incorrect.
    Sans cette regle, un document contenant a la fois un nom errone ET
    un libelle de role ("Salarie", "Employeur") aurait ete valide a tort,
    le libelle rescue masquant le vrai probleme (mauvaise personne).

Limite assumee : si un document ne contient NI nom NI libelle de role a
proximite d'une signature (signature totalement anonyme), il est
techniquement impossible de determiner a qui elle appartient a partir du
contenu du document seul.
"""

from rapidfuzz import fuzz
import unicodedata

RAYON_RECHERCHE = 0.15
SEUIL_SIMILARITE = 65
SEUIL_TOKEN = 65
SEUIL_SCORE_FORT = 80
SEUIL_LIBELLE_ROLE = 70
SEUIL_PRESENCE_NOM = 60  # au-dela, on considere qu'un texte "ressemblant a un nom" existe deja
TOLERANCE_SOUS_SIGNATURE = 0.015
TOLERANCE_SOUS_SIGNATURE_TOKEN = 0.05

ROLE_OBLIGATOIRE = "employe"

LIBELLES_PAR_ROLE = {
    "employe": [
        "salarie", "salariee", "le salarie", "la salariee",
        "le/la salarie", "employe", "employee",
    ],
    "entreprise": [
        "employeur", "l'employeur", "societe", "gerant",
        "directeur general", "representant",
    ],
    "garant": [
        "garant", "caution", "le garant",
    ],
}


def normaliser_texte(texte):
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


def _match_libelle_role(mots_proches_norm, role):
    libelles = LIBELLES_PAR_ROLE.get(role, [])
    if not libelles or not mots_proches_norm:
        return False, None, 0
    meilleur_score, meilleur_libelle = 0, None
    for libelle in libelles:
        for mot in mots_proches_norm:
            score = fuzz.partial_ratio(mot, normaliser_texte(libelle))
            if score > meilleur_score:
                meilleur_score, meilleur_libelle = score, libelle
    return meilleur_score >= SEUIL_LIBELLE_ROLE, meilleur_libelle, meilleur_score


def identifier_signataires(signatures, mots_positions, roles_attendus,
                            rayon_max=RAYON_RECHERCHE, seuil_similarite=SEUIL_SIMILARITE,
                            seuil_token=SEUIL_TOKEN):
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

        # Etape A : calcule le matching par NOM pour tous les roles d'abord,
        # sans encore decider d'activer le filet de secours.
        resultats_bruts = {}
        for role, nom_norm in roles_normalises.items():
            texte, score, dist, brut = _meilleur_match(proches, nom_norm, seuil_similarite)
            couverture = _couverture_tous_tokens(mots_proches_norm, nom_norm, seuil_token)
            match_nom = brut and (couverture or score >= SEUIL_SCORE_FORT)
            resultats_bruts[role] = {
                "texte": texte, "score": score, "dist": dist, "match_nom": match_nom,
            }

        # Un texte "ressemblant a un nom" existe-t-il a proximite, meme si
        # il ne correspond a AUCUN nom attendu ? Si oui, on desactive le
        # filet de secours pour CETTE signature (evite qu'un mauvais nom
        # soit "rattrape" a tort par un libelle generique).
        meilleur_score_nom_global = max((r["score"] for r in resultats_bruts.values()), default=0)
        nom_present_a_proximite = meilleur_score_nom_global >= SEUIL_PRESENCE_NOM

        scores_par_role = {}
        for role, res in resultats_bruts.items():
            if res["match_nom"]:
                scores_par_role[role] = {
                    "nom_trouve": res["texte"], "distance": res["dist"], "score": res["score"],
                    "correspond": True, "methode": "nom",
                }
                continue

            if nom_present_a_proximite:
                # Un nom (meme incorrect) est present -> pas de filet de
                # secours, on reste sur un rejet honnete pour ce role.
                scores_par_role[role] = {
                    "nom_trouve": res["texte"], "distance": res["dist"], "score": res["score"],
                    "correspond": False, "methode": "aucun",
                }
                continue

            # Niveau 2 -- aucun nom du tout trouve a proximite -> filet de
            # secours par libelle de role generique.
            match_libelle, libelle_trouve, score_libelle = _match_libelle_role(mots_proches_norm, role)
            scores_par_role[role] = {
                "nom_trouve": libelle_trouve if match_libelle else res["texte"],
                "distance": res["dist"],
                "score": score_libelle if match_libelle else res["score"],
                "correspond": match_libelle,
                "methode": "libelle_role" if match_libelle else "aucun",
            }

        roles_matches = [r for r, v in scores_par_role.items() if v["correspond"]]
        if roles_matches:
            roles_par_nom = [r for r in roles_matches if scores_par_role[r]["methode"] == "nom"]
            candidats_role = roles_par_nom or roles_matches
            role_retenu = min(candidats_role, key=lambda r: scores_par_role[r]["distance"] or 0)
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
                    "methode": v["methode"],
                }
                for role, v in scores_par_role.items()
            },
        })

    for role in roles_a_verifier:
        role_trouve = any(
            d["matches_par_role"].get(role, {}).get("correspond") for d in detail
        )
        if not role_trouve:
            libelle = "l'employe" if role == ROLE_OBLIGATOIRE else f"du role '{role}'"
            return False, f"Signature de {libelle} manquante ou non identifiee", detail

    return True, None, detail