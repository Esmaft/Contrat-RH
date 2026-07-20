# Déploiement Docker — Système de Vérification de Contrats RH

## Structure attendue

```
docker/
├── docker-compose.yml
├── models/
│   └── yolov8s_signature_final.pt      <- a copier ici (non inclus dans l'image, volume monte)
└── services/
    ├── signature/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── signature_service.py         <- a copier depuis le projet
    ├── ocr/
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── ocr_service.py               <- a copier depuis le projet
    └── api/
        ├── Dockerfile
        ├── requirements.txt
        ├── main.py                      <- a copier depuis le projet
        └── modules/                     <- a copier depuis le projet
            ├── comparaison.py
            ├── scoring.py
            ├── llm.py
            └── identification_signataires.py
```

## Prérequis sur la machine hôte

1. **Docker** et **Docker Compose** installés
2. **Pilote NVIDIA** installé sur l'hôte (Windows : via WSL2, cf. documentation NVIDIA CUDA on WSL)
3. **NVIDIA Container Toolkit** installé, pour que Docker puisse accéder au GPU :
   ```bash
   # Sur une machine Linux (ou WSL2)
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
   curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
   sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
   sudo systemctl restart docker
   ```

## Étapes de déploiement

### 1. Préparer les fichiers

Copier les fichiers source réels du projet dans la structure `docker/` ci-dessus (remplacer les placeholders).

### 2. Construire et lancer tous les services

```bash
cd docker
docker compose up --build -d
```

### 3. Télécharger le modèle Ollama (une seule fois)

```bash
docker exec -it ollama_service ollama pull qwen2.5:7b
```

### 4. Vérifier que tout tourne

```bash
docker compose ps
```

Chaque service doit être à l'état "Up". Testez ensuite :

```bash
curl http://localhost:8000/
curl http://localhost:8001/
curl http://localhost:8002/
curl http://localhost:11434/
```

### 5. Tester le pipeline complet

Utilisez Bruno/Postman ou la plateforme de simulation, en pointant vers `http://localhost:8000/api/version1/verify` comme d'habitude — le comportement est identique à l'exécution locale, seule l'infrastructure change.

## Commandes utiles

```bash
# Voir les logs d'un service en temps reel
docker compose logs -f signature

# Redemarrer un seul service (apres modification du code)
docker compose up --build -d signature

# Tout arreter
docker compose down

# Tout arreter ET supprimer les volumes (efface le modele Ollama telecharge)
docker compose down -v
```

## Notes importantes

- **Portabilité** : cette configuration résout la limite connue des chemins Windows codés en dur (`POPPLER_PATH`) — `poppler-utils` est installé nativement dans les images Linux, le code bascule automatiquement (`platform.system() != "Windows"` → `POPPLER_PATH = None`).
- **GPU partagé** : les 3 services demandant un GPU (Signature, OCR, Ollama) peuvent tourner simultanément sur un seul GPU si sa VRAM est suffisante (cf. cahier des charges — empreinte cumulée largement sous 8 Go).
- **Sans GPU disponible** : retirer les blocs `deploy.resources.reservations.devices` de chaque service dans `docker-compose.yml` pour forcer un fonctionnement CPU (fonctionnel mais nettement plus lent, notamment pour l'OCR).
