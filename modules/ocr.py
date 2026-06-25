"""
Module OCR — Chargement et extraction de texte
Utilise DocTR (Mindee) pour la reconnaissance optique de caractères
"""

import cv2
import os
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
from pdf2image import convert_from_path

# Chemin Poppler pour Windows
POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin"

# Chargement du modèle OCR une seule fois au démarrage
print("Chargement du modèle OCR (DocTR)...")
ocr_model = ocr_predictor(pretrained=True)
print("Modèle OCR prêt.")


def charger_document(chemin_fichier):
    """
    Convertit un PDF en liste d'images JPG (une image par page).
    Accepte aussi les images directement (.jpg, .jpeg, .png).
    Retourne une liste de chemins d'images, ou None si format non supporté.
    """
    extension = os.path.splitext(chemin_fichier)[1].lower()
    images = []

    if extension == ".pdf":
        pages = convert_from_path(chemin_fichier, poppler_path=POPPLER_PATH)
        for i, page in enumerate(pages):
            chemin_image = f"page_{i+1}.jpg"
            page.save(chemin_image)
            images.append(chemin_image)
            print(f"{len(images)} pages converties")
    elif extension in [".jpg", ".jpeg", ".png"]:
        images.append(chemin_fichier)
    else:
        print(f"Format non supporté : {extension}")
        return None

    return images


def pretraiter_image(chemin_image):
    """
    Prétraitement OpenCV : conversion en niveaux de gris + débruitage.
    Retourne le chemin de l'image prétraitée.
    """
    image = cv2.imread(chemin_image)
    gris = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    debruite = cv2.fastNlMeansDenoising(gris, h=10)
    chemin_pretraite = chemin_image.replace(".jpg", "_pretraite.jpg")
    cv2.imwrite(chemin_pretraite, debruite)
    return chemin_pretraite


def extraire_texte_ocr(chemin_image):
    """
    Extrait le texte d'une image prétraitée avec DocTR.
    Retourne (texte_complet, confiance_moyenne).
    """
    doc = DocumentFile.from_images(chemin_image)
    result = ocr_model(doc)

    texte_complet = ""
    confiances = []

    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                ligne_texte = " ".join([word.value for word in line.words])
                confs = [word.confidence for word in line.words]
                if confs and sum(confs) / len(confs) > 0.5:
                    texte_complet += ligne_texte + "\n"
                    confiances.extend(confs)

    confiance_moyenne = sum(confiances) / len(confiances) if confiances else 0
    return texte_complet, confiance_moyenne
