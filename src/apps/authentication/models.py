"""Beherbergt HistoricalUser/HistoricalGroup, die simple_history dynamisch
hier anhängt (siehe managers.py). Keine eigenen Model-Definitionen.

Notwendig, nicht nur Konvention: simple_history.register(..., app=
"apps.authentication") importiert intern per importlib.import_module(
"apps.authentication.models") und hängt die generierten Historical*-Klassen
per setattr dort an. Ohne diese Datei schlägt die Registrierung mit
ModuleNotFoundError fehl.
"""
