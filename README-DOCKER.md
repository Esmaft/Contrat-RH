# Deploiement Docker -- Systeme de Verification de Contrats RH

## Structure reelle du projet

Les fichiers Docker sont a la racine du projet (pas dans un sous-dossier `docker/`) :

```
projet rh/
├── docker-compose.yml
├── models/
│   └── yolov8s_signature_final.pt
├── modules/
│   ├── comparaison.py
│   ├── scoring.py
│   ├── llm.py
│   └── identification_signataires.py
└── services/
    ├── signature/
    │   ├── Dockerfile
    │   └── signature_service.py
    ├── ocr/
    │   ├── Dockerfile
    │   └── ocr_service.py
    └── api/
        ├── Dockerfile
        └── main.py
```

Aucun fichier `requirements.txt` : les dependances Python sont installees directement dans chaque `Dockerfile` (`RUN pip install ...`), pas de fichier separe a maintenir.

## Prerequis sur la machine hote

1. **Docker** et **Docker Compose** installes
2. **Pilote NVIDIA** installe sur l'hote si GPU disponible (Windows : via WSL2, cf. documentation NVIDIA CUDA on WSL)
3. **NVIDIA Container Toolkit** installe (uniquement si GPU disponible) :
   ```bash
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
   curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   sudo systemctl restart docker
   ```
   Sans GPU disponible : voir section "Fonctionnement sans GPU" plus bas -- le systeme reste fonctionnel, juste plus lent.

## Variables d'environnement critiques (deja configurees dans docker-compose.yml)

Ces variables resolvent des incompatibilites de chemins entre l'execution locale (Windows) et l'execution en conteneur (Linux). Elles sont deja presentes dans `docker-compose.yml` fourni -- **rien a modifier pour un lancement standard**, mais a connaitre en cas de probleme :

| Variable | Service | Valeur attendue | Role |
|---|---|---|---|
| `MODEL_PATH` | signature | `/app/models/yolov8s_signature_final.pt` | Chemin du modele YOLO a l'interieur du conteneur |
| `MODULES_PATH` | api | `/app/modules` | Chemin des modules partages (comparaison, scoring, llm, identification_signataires) |
| `OLLAMA_URL` | api | `http://ollama:11434/api/generate` | **Doit imperativement inclure `/api/generate`** -- une URL sans ce chemin provoque une erreur `405 Method Not Allowed` cote Ollama |
| `SIGNATURE_SERVICE_URL` | api | `http://signature:8002` | Nom de service Docker, pas `localhost` |
| `OCR_SERVICE_URL` | api | `http://ocr:8001` | Nom de service Docker, pas `localhost` |

## Etapes de deploiement

### 1. Verifier que le modele est present

```bash
ls models/yolov8s_signature_final.pt
```

Ce fichier doit exister a la racine du dossier `models/` (~67 Mo) -- il est monte en volume, pas copie dans l'image.

### 2. Construire toutes les images

```bash
docker compose build --no-cache
```

Le `--no-cache` est recommande pour un premier build ou apres une mise a jour du code, afin d'eviter que Docker reutilise une couche en cache perimee.

### 3. Lancer tous les services

```bash
docker compose up -d
```

### 4. Telecharger le modele Ollama (une seule fois, obligatoire)

```bash
docker exec -it ollama_service ollama pull qwen2.5:7b
```

Sans cette etape, le service API demarre normalement mais toute requete de verification echouera a l'etape d'extraction LLM.

### 5. Verifier que tout tourne

```bash
docker compose ps
```

Les 4 services (`api_principale`, `ocr_service`, `signature_service`, `ollama_service`) doivent etre a l'etat `Up`, sans `Restarting`.

Testez ensuite chaque service (sous PowerShell, utiliser `curl.exe`, pas l'alias `curl`) :

```powershell
curl.exe http://localhost:8000/
curl.exe http://localhost:8001/
curl.exe http://localhost:8002/
curl.exe http://localhost:11434/
```

Chaque commande doit retourner un JSON de statut (ou "Ollama is running" pour le dernier).

### 6. Tester le pipeline complet

```
POST http://localhost:8000/api/version1/verify
```

Body multipart/form-data avec un champ `fichier` (PDF) et un champ `donnees_rh` (JSON). Voir le README principal du projet pour le format exact.

## Fonctionnement sans GPU

Si le serveur cible n'a pas de GPU, retirer les blocs suivants de `docker-compose.yml` pour chaque service concerne (`signature`, `ocr`, `ollama`) :

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

Le systeme reste fonctionnel sur CPU, mais le temps de traitement augmente significativement : l'etape OCR passe d'environ 7 secondes (GPU) a environ 60-70 secondes (CPU), et l'extraction LLM (Ollama, modele 7B) peut prendre plusieurs minutes sur CPU. 

## Problemes connus et deja resolus (a ne pas reintroduire)

Ces problemes sont deja corriges dans les `Dockerfile` fournis. Ils sont documentes ici pour eviter de les reintroduire lors d'une modification future :

- **Conflit NumPy/OpenCV** : installer `ultralytics` sans `--no-deps` peut entrainer l'installation simultanee de `opencv-python` ET `opencv-python-headless`, provoquant une erreur `RuntimeError: Numpy is not available` au moment de l'inference (pas au chargement du modele). Le Dockerfile du service `signature` installe `ultralytics` avec `--no-deps` et liste explicitement ses dependances avec des versions figees pour eviter ce conflit.
- **`filelock` obsolete** : l'image de base `pytorch/pytorch` embarque une version de `filelock` trop ancienne pour Ultralytics recent (`AsyncFileLock` manquant). Le Dockerfile fixe explicitement `filelock>=3.16.1`.
- **Contexte de build de l'API** : le service `api` a besoin du dossier `modules/` situe a la racine du projet, hors de `services/api/`. Le `docker-compose.yml` utilise donc `context: .` avec `dockerfile: services/api/Dockerfile` pour ce service specifiquement (different des 2 autres services).

## Commandes utiles

```bash
# Voir les logs d'un service en temps reel
docker compose logs -f signature

# Reconstruire et redemarrer un seul service (apres modification du code)
docker compose build --no-cache signature
docker compose up -d --force-recreate signature

# Verifier les versions de packages installes dans un conteneur (diagnostic)
docker exec -it signature_service pip list | findstr opencv

# Tout arreter
docker compose down

# Tout arreter ET supprimer les volumes (efface le modele Ollama telecharge)
docker compose down -v
```

## Notes complementaires

- **Portabilite** : cette configuration resout la limite des chemins Windows codes en dur (`POPPLER_PATH`) -- `poppler-utils` est installe nativement dans les images Linux.
- **GPU partage** : les services demandant un GPU (Signature, OCR, Ollama) peuvent tourner simultanement sur un seul GPU si sa VRAM est suffisante (empreinte cumulee largement sous 8 Go dans nos tests).
- **Validation** : cette configuration a ete testee de bout en bout (test complet du pipeline avec un contrat reel, resultat conforme a l'execution locale).
