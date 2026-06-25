# Verification Automatique de Contrats RH
---

## Description

Module de verification automatique de contrats de travail scannes (CDD, CDI, stage) par comparaison avec les donnees du systeme RH.

**Pipeline :**
```
PDF scanne → DocTR (OCR) → Qwen 2.5 7B (extraction) → RapidFuzz (comparaison) → Decision
```

**Statuts de sortie :** `valide` | `Rejete` | `En revision` | `Erreur`

---

## Technologies

- **OCR :** DocTR (Mindee)
- **LLM :** Qwen 2.5 7B via Ollama (100% local)
- **Comparaison :** RapidFuzz
- **API :** FastAPI
- **Tests :** Bruno

---

## Structure

```
projet-rh/
├── modules/
│   ├── ocr.py
│   ├── llm.py
│   ├── comparaison.py
│   ├── scoring.py
│   ├── api_rh.py
│   └── pipeline.py
├── contrats_test/
├── main.py
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