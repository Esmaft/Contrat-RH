# Système de Vérification Automatique de Contrats RH

Projet de Fin d'Année (PFA) — Vérification automatisée de contrats RH par analyse de signature, OCR et extraction de champs via LLM.

**Auteur** : Asma EL FATIMI

---

## 1. Objectif du projet

Automatiser la vérification de contrats RH (PDF) en combinant :
- **Détection de signature** (YOLOv8s) — vérifie que le contrat est bien signé
- **Identification des signataires** — détermine automatiquement à qui appartient chaque signature (employé, représentant de l'entreprise, ou tout autre rôle contractuel déclaré, ex : garant)
- **OCR** (DocTR) — extrait le texte du document et la position de chaque mot
- **Extraction de champs** (LLM, Ollama/Qwen2.5) — structure les informations (nom, CIN, salaire, dates...)
- **Comparaison automatique** — confronte les champs extraits aux données du système RH et calcule un score de conformité

## 2. Architecture

Le système est organisé en microservices FastAPI indépendants :

```
Plateforme RH IMRASOFT
        |
        | POST /api/version1/verify (fichier PDF + donnees_rh)
        v
+-----------------------+
|   API Principale       |  (port 8000) -- Orchestration du pipeline
+-----------+-------------+
            |
   +--------+--------+------------------+
   v                 v                  v
+--------+      +--------+      +----------+
|Signature|      |  OCR   |      |  Ollama  |
| (8002)  |      | (8001) |      |  (11434) |
+--------+      +--------+      +----------+
```

Le module `modules/identification_signataires.py` n'est pas un service séparé : il est appelé directement par l'API principale, en croisant les résultats des services Signature et OCR.

### Pipeline de traitement (ordre optimisé pour la performance)

1. **Détection de signature** (rapide, ~5-10s) -- rejet immédiat si le contrat n'est pas signé, évite de lancer inutilement l'OCR/LLM
2. **OCR** -- extraction du texte et de la position de chaque mot
3. **Identification des signataires** -- détermine, pour chaque signature détectée, le rôle correspondant (employé / entreprise / rôle additionnel) en cherchant le nom le plus proche géométriquement
4. **Extraction des champs via LLM** -- structure les données du contrat
5. **Comparaison et scoring** -- compare aux données RH attendues, avec tolérance sur certains champs et normalisation des formats de date

La réponse HTTP de l'étape finale est le **seul** canal de communication du statut vers la plateforme RH -- aucun rappel (callback/PATCH) séparé n'est effectué.

## 3. Module d'identification des signataires

### Principe

Pour chaque signature détectée par YOLO (position x, y), le système cherche le nom le plus proche géométriquement parmi les mots reconnus par l'OCR, puis compare ce nom aux noms attendus (`full_name`, `representer`, et tout rôle additionnel présent dans `donnees_rh`).

**Aucune saisie manuelle requise** : tous les noms attendus proviennent déjà des données RH transmises à chaque requête.

### Règle d'acceptation

- La signature de l'**employé** est toujours obligatoire.
- Tout **rôle additionnel** (représentant, garant, etc.) devient obligatoire dès que son nom est renseigné dans `donnees_rh` -- son absence de signature entraîne un rejet explicite.
- Convention d'intégration : la plateforme RH ne doit transmettre un rôle que lorsque sa signature est effectivement requise pour ce contrat.

### Robustesse

- Fonctionne indépendamment de la mise en page (position gauche/droite des signataires)
- Tolère les imperfections OCR grâce à une comparaison floue (RapidFuzz) et une vérification de couverture par token (prénom + nom retrouvés individuellement, pas seulement une ressemblance globale)
- Filet de secours pour les cas où l'encre d'une signature recouvre partiellement le nom imprimé (score de similarité globale élevé accepté même sans couverture complète des tokens)

## 4. Modèle de détection de signature

- **Architecture** : YOLOv8s (Ultralytics)
- **Dataset** : fusion de sources annotées (Roboflow + Tobacco800), nettoyage des formats mixtes segmentation/detection, re-split train/val équilibré
- **Résultats finaux** (epoch 91) :

| Métrique | Score |
|---|---|
| Precision | 0.945 |
| Recall | 0.881 |
| mAP50 | 0.933 |
| mAP50-95 | 0.549 |

Modèle final : `models/yolov8s_signature_final.pt`

## 5. Installation et lancement

Deux modes de déploiement sont disponibles : exécution locale directe, ou conteneurisation Docker (recommandée pour la portabilité).

### 5.1 Déploiement Docker (recommandé)

**Prérequis** : Docker, Docker Compose, pilote NVIDIA + NVIDIA Container Toolkit pour l'accélération GPU.

```bash
cd docker
docker compose up --build -d
docker exec -it ollama_service ollama pull qwen2.5:7b
```

Les dépendances Python de chaque service sont installées directement dans leur `Dockerfile` respectif (pas de fichier `requirements.txt` séparé à maintenir). Voir `docker/README-DOCKER.md` pour le détail complet (structure attendue, commandes utiles, fonctionnement sans GPU).

La conteneurisation résout également la limite de portabilité Windows : `poppler-utils` est installé nativement dans les images Linux, éliminant la dépendance au chemin `POPPLER_PATH` codé en dur.

### 5.2 Exécution locale (développement)

**Prérequis**
- Python 3.10
- CUDA 12.x + GPU compatible (recommandé -- le pipeline est optimisé pour tourner sur GPU)
- [Poppler](https://github.com/oschwartz10612/poppler-windows) (conversion PDF -> image)
- [Ollama](https://ollama.com) avec le modèle `qwen2.5:7b`

Chaque service doit être lancé indépendamment (3 terminaux séparés) :

```bash
# Terminal 1 -- Service Signature (port 8002)
cd services/signature
uvicorn signature_service:app --host 0.0.0.0 --port 8002

# Terminal 2 -- Service OCR (port 8001)
cd services/ocr
uvicorn ocr_service:app --host 0.0.0.0 --port 8001

# Terminal 3 -- API principale (port 8000)
cd services/api
uvicorn main:app --host 0.0.0.0 --port 8000
```

Assure-toi qu'Ollama tourne aussi (`ollama serve`).

## 6. Utilisation de l'API

### Endpoint principal

```
POST http://localhost:8000/api/version1/verify
```

**Body (multipart/form-data)** :
- `fichier` : le PDF du contrat
- `donnees_rh` : JSON contenant les champs attendus (identité de l'employé, entreprise, représentant, et tout rôle contractuel additionnel le cas échéant)

**Réponse** : statut (`valide` / `Rejete` / `En revision`), score global, motif explicite en cas de rejet, détail par signature détectée (rôle identifié, score de correspondance par rôle), temps de traitement.

## 7. Robustesse et production

- **Fichiers temporaires** : chaque requête OCR utilise un sous-dossier unique (UUID), évitant toute collision entre requêtes concurrentes
- **Concurrence GPU** : un `asyncio.Semaphore` sérialise les appels d'inférence GPU dans les services Signature et OCR, évitant toute contention mémoire (VRAM) en cas de requêtes simultanées
- **Test de charge validé** : 3 requêtes simultanées traitées avec succès (100% de réussite), avec un temps de traitement croissant selon l'ordre de mise en file d'attente
- **Portabilité** : conteneurisation Docker disponible (voir section 5.1), éliminant la dépendance aux chemins Windows codés en dur

## 8. Choix techniques et limites connues

- **GPU obligatoire pour de bonnes performances** : les 3 modèles (YOLO, DocTR, Ollama) tournent sur le même GPU (8GB VRAM suffisant pour leur coexistence). Sur CPU seul, le temps de traitement OCR augmente fortement (~60-70s au lieu de ~7s).
- **Cold start** : la première requête après une période d'inactivité est plus lente (Ollama recharge le modèle en VRAM après expiration du `keep_alive`).
- **Nombre de signatures requises** : dérivé du nombre de rôles renseignés dans `donnees_rh`, pas d'une analyse de la structure physique du document (pas de détection des zones de signature vides).
- **Chevauchement encre/texte** : si une signature manuscrite recouvre le nom imprimé, l'OCR peut échouer à le lire ; un filet de secours basé sur un score de similarité élevé atténue ce risque sans le garantir totalement.
- **mAP50-95 modéré (0.549)** : lié à la conversion approximative polygone->bounding box sur une partie du dataset (sources Roboflow/Tobacco800 annotées à l'origine en segmentation).

## 9. Pistes d'amélioration futures

- Détection des zones de signature vides (2e classe YOLO) pour connaître le nombre exact de signatures attendues indépendamment des données RH
- Référentiel de templates par entreprise pour affiner les règles de validation
- Portabilité Linux complète (chemins actuellement codés pour Windows) -- *partiellement couverte par la conteneurisation Docker, section 5.1*
- Gestion de la concurrence à l'échelle infrastructure (file d'attente distribuée, plusieurs instances/GPU) -- la contention GPU au sein d'un même serveur est déjà gérée au niveau du code (sémaphores, section 7) ; ce point ne concerne que le dimensionnement à plus grande échelle (plusieurs serveurs, load balancing)