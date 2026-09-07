# data_local.py
# Modalidad de origen de datos LOCAL.
# Lee de ficheros JSON en disco con la misma estructura que la API de
# Open Targets. Sirve para el extra de "dualidad de origen de datos" y
# tambien para probar el servidor sin necesidad de conexion.
#
# Manejo dos ficheros distintos:
#   - data_local.json     -> estructura tipo "target -> diseases"
#   - disease_local.json  -> estructura tipo "disease -> targets"
# El nombre lo elijo segun lo que pide el usuario.

import json
import os


RUTA_TARGET = "data_local.json"
RUTA_DISEASE = "disease_local.json"


def obtener_datos_local(gene_id):
    """Lee data_local.json (orientado a Target).

    Si gene_id es None o vacio devuelvo todo el JSON tal cual.
    Si se pide un gene_id que no coincide con el del fichero, devuelvo
    estructura vacia ({"data": {"target": None}}).
    """
    if not os.path.exists(RUTA_TARGET):
        return {"errors": [{"message": f"No se encuentra el fichero {RUTA_TARGET}"}]}

    try:
        with open(RUTA_TARGET, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except json.JSONDecodeError as e:
        return {"errors": [{"message": f"JSON local mal formado: {e}"}]}

    # sin gene_id -> devuelvo el contenido entero
    if not gene_id:
        return datos

    # con gene_id -> compruebo que coincida con el del fichero
    target_local = datos.get("data", {}).get("target", {}) or {}
    if target_local.get("id") != gene_id:
        return {"data": {"target": None}}

    return datos


def obtener_disease_local(efo_id):
    """Lee disease_local.json (orientado a Disease).

    Misma logica que obtener_datos_local pero para la query inversa.
    """
    if not os.path.exists(RUTA_DISEASE):
        return {"errors": [{"message": f"No se encuentra el fichero {RUTA_DISEASE}"}]}

    try:
        with open(RUTA_DISEASE, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except json.JSONDecodeError as e:
        return {"errors": [{"message": f"JSON local mal formado: {e}"}]}

    if not efo_id:
        return datos

    disease_local = datos.get("data", {}).get("disease", {}) or {}
    if disease_local.get("id") != efo_id:
        return {"data": {"disease": None}}

    return datos