# data1.py
# Modulo que se encarga de hacer la peticion a la API GraphQL de Open Targets
# para obtener informacion de un Target (gen) y sus enfermedades asociadas.
#
# Uso un diccionario como cache para no llamar a la API en cada refresco del
# navegador. La primera vez tarda 1-2s, las siguientes son instantaneas.

import requests
import json


# cache en memoria: clave = gene_id, valor = respuesta de la API
_cache = {}


# guardo el endpoint en una constante por si hay que cambiarlo
ENDPOINT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"


def obtener_datos_api(gene):
    """Pregunta a Open Targets por un Target y devuelve la respuesta JSON.

    Si ya hemos preguntado por ese gene antes, devolvemos lo que tenemos
    cacheado. Si no, lanzamos la peticion POST.
    """
    # primero miro la cache
    if gene in _cache:
        return _cache[gene]

    # construyo la query GraphQL.
    # nota: pongo size=25 en associatedDiseases y size=50 en evidences porque
    # con valores mas altos la API me decia "Query is too expensive". 
    
    query_multiples_enfermedades = """
    query BuscarEnfermedadesYEvidencias($ensemblId: String!) {
      target(ensemblId: $ensemblId) {
        id
        approvedSymbol
        biotype
        tractability {
          label
          modality
          value
        }
        associatedDiseases(page: {index: 0, size: 25}) {
          rows {
            disease {
              id
              name
              evidences(ensemblIds: [$ensemblId], size: 50) {
                rows {
                  id
                  score
                  datatypeId
                  datasourceId
                }
              }
            }
          }
        }
      }
    }
    """

    variables = {"ensemblId": gene}

    # peticion. Pongo timeout porque si la API se queda colgada no quiero
    # que el servidor se quede esperando para siempre
    try:
        r = requests.post(
            ENDPOINT_GRAPHQL,
            json={"query": query_multiples_enfermedades, "variables": variables},
            timeout=15,
        )
        api_response = r.json()
    except Exception as e:
        # devuelvo el error con la misma estructura que usa Open Targets
        # cuando ella misma falla, asi el procesador lo trata de forma uniforme
        print(f"Error al consultar la API: {e}")
        return {"errors": [{"message": str(e)}]}

    # guardo el JSON en disco. me viene bien para depurar
    try:
        with open("datos.json", "w", encoding="utf-8") as f:
            json.dump(api_response, f, indent=2)
    except OSError:
        # si por lo que sea no puedo escribir el fichero, sigo adelante
        pass

    _cache[gene] = api_response
    return api_response


def obtener_targets_de_disease(efo_id):
    """Consulta los Targets asociados a una Disease (búsqueda inversa).

    Esta funcion la uso en /searchDisease. Aqui el punto de entrada es una
    enfermedad y queremos saber qué genes la causan, en lugar de partir
    del gen como hacemos en obtener_datos_api.
    """
    cache_key = f"disease:{efo_id}"
    if cache_key in _cache:
        return _cache[cache_key]

    query = """
    query TargetsDeEnfermedad($efoId: String!) {
      disease(efoId: $efoId) {
        id
        name
        associatedTargets(page: {index: 0, size: 25}) {
          rows {
            target {
              id
              approvedSymbol
              biotype
              tractability {
                label
                modality
                value
              }
            }
            score
          }
        }
      }
    }
    """

    variables = {"efoId": efo_id}

    try:
        r = requests.post(
            ENDPOINT_GRAPHQL,
            json={"query": query, "variables": variables},
            timeout=15,
        )
        api_response = r.json()
    except Exception as e:
        print(f"Error al consultar la API (disease): {e}")
        return {"errors": [{"message": str(e)}]}

    _cache[cache_key] = api_response
    return api_response