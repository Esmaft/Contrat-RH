# Verification Automatique de Contrats RH

## Description

Module de verification automatique de contrats de travail scannes (CDD, CDI, stage) par comparaison avec les donnees du systeme RH.

**Pipeline :**
```
PDF scanne → OCR (DocTR) → Detection Signature (YOLOv8) → LLM Qwen 2.5 7B → Comparaison (RapidFuzz) → Decision
```

**Statuts de sortie :** `valide` | `Rejete` | `En revision` | `Erreur`

---

## Technologies

- **OCR :** DocTR (Mindee)
- **Detection Signatures :** YOLOv8n (dataset combine 2648 images)
- **LLM :** Qwen 2.5 7B via Ollama (100% local)
- **Comparaison :** RapidFuzz
- **API :** FastAPI
- **Tests :** Bruno

---

## Architecture Microservices

```
projet-rh/
├── services/
│   ├── api/                  ← Service principal (port 8000)
│   │   ├── main.py
│   │   └── Dockerfile
│   ├── ocr/                  ← Service OCR DocTR (port 8001)
│   │   ├── ocr_service.py
│   │   └── Dockerfile
│   └── signature/            ← Service Signature YOLOv8 (port 8002)
│       ├── signature_service.py
│       └── Dockerfile
├── modules/
│   ├── llm.py
│   ├── comparaison.py
│   ├── scoring.py
│   ├── api_rh.py
│   └── pipeline.py
├── models/
│   └── best.pt
├── contrats_test/
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Installation

```bash
pip install -r requirements.txt
ollama pull qwen2.5:7b
```

---
**Ou via Docker :**
```bash
docker-compose up -d
docker exec verification_contrats_ollama ollama pull qwen2.5:7b
```

**Image Docker Hub :**
```
esmadev/verification-contrats-rh:latest
```