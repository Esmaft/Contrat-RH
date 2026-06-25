import sys
sys.path.append("modules")
from pipeline import pipeline_complet

resultat = pipeline_complet("Contrat_CDD_Scanne.pdf", "003")
print(resultat)