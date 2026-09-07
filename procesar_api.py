# procesar_api.py
# Convierte el JSON crudo que devuelve la API en objetos de mis clases.
# Es la "capa de adaptacion" entre los datos remotos y mi modelo de POO.

from target import Target, TractabilityItem
from disease import Disease
from evidence import Evidence, GeneticEvidence, IndirectEvidence
from association import Association


def procesar_json_a_asociaciones(json_datos: dict) -> list:
    """Recorre el JSON y devuelve una lista de objetos Association.

    Si el JSON viene con errores o vacío, devuelvo lista vacía para que
    el servidor pueda mostrar el mensaje de "no se han encontrado resultados".
    """

    # 1. Comprobar si la API devolvio un error explicito
    if "errors" in json_datos:
        # Open Targets devuelve "Query is too expensive" si pedimos demasiado.
        # Si pasa, devolvemos vacio para que el servidor muestre el mensaje
        # de "no hay resultados" (no quiero que el servidor se caiga por esto)
        return []

    # 2. Comprobar que viene data y que dentro hay target
    if "data" not in json_datos or not json_datos["data"].get("target"):
        return []

    datos_target = json_datos["data"]["target"]

    # 3. Construir el Target con su tractabilidad
    lista_tract = []
    for t in datos_target.get("tractability", []):
        lista_tract.append(
            TractabilityItem(t["label"], t["modality"], t["value"])
        )

    try:
        mi_target = Target(
            datos_target["id"],
            datos_target["approvedSymbol"],
            datos_target["biotype"],
            lista_tract,
        )
    except ValueError:
        # si el ID no es ENSG cortamos aqui
        return []

    lista_asociaciones = []

    # 4. Recorrer las enfermedades asociadas
    filas_enfermedades = datos_target.get("associatedDiseases", {}).get("rows", [])
    for fila in filas_enfermedades:
        datos_enfermedad = fila["disease"]

        try:
            # paso lista vacia de fenotipos: ni el formulario ni la tabla
            # los necesitan y asi la query de la API es mucho mas ligera.
            # esto lo justifico en el README.
            mi_disease = Disease(
                datos_enfermedad["id"], datos_enfermedad["name"], []
            )
        except ValueError:
            # raro tras ampliar los prefijos en disease.py, pero por si
            # cae alguna disease con id de una ontologia que no contemplo
            # o sin nombre, la salto y sigo con el resto
            continue

        # 5. Construir evidencias:
        #
        #    - genetic_association  -> GeneticEvidence (necesita sourceId)
        #    - el resto             -> Evidence base
        #
        #    No uso IndirectEvidence aqui porque la API no me indica de forma
        #    directa cuando una evidencia ha sido propagada por ontologia EFO
        #    descendiente. Para esos casos no quiero "adivinar" el tipo, asi
        #    que dejo todo como Evidence base salvo cuando estoy seguro.
        #    La clase IndirectEvidence se prueba en unittests con datos
        #    sinteticos para verificar el polimorfismo del *0.8.
        lista_evidencias = []
        filas_evidencias = datos_enfermedad.get("evidences", {}).get("rows", [])

        for ev in filas_evidencias:
            try:
                if ev["datatypeId"] == "genetic_association":
                    lista_evidencias.append(
                        GeneticEvidence(
                            ev["id"],
                            ev["score"],
                            ev["datatypeId"],
                            ev.get("datasourceId", ""),
                        )
                    )
                else:
                    lista_evidencias.append(
                        Evidence(ev["id"], ev["score"], ev["datatypeId"])
                    )
            except ValueError:
                # por ejemplo: gwas_catalog con score < 0.05.
                # esa evidencia se descarta, las demas siguen.
                continue

        # 6. Solo creo la Association si hemos podido construir al menos una
        # evidencia. Si una enfermedad llega "sin pruebas", no aporta nada.
        if lista_evidencias:
            lista_asociaciones.append(
                Association(mi_target, mi_disease, lista_evidencias)
            )

    return lista_asociaciones


def procesar_json_disease_a_asociaciones(json_datos: dict) -> list:
    """Para /searchDisease. Procesa el JSON de la query inversa (disease -> targets).

    Aqui el punto de partida es una enfermedad y por cada target asociado
    creamos una Association. Como la query inversa de la API devuelve un
    score directo en lugar de evidencias detalladas, fabrico una Evidence
    sintetica que represente ese score (para mantener la coherencia con
    el modelo: una Association siempre necesita evidencias).
    """
    if "errors" in json_datos:
        return []
    if "data" not in json_datos or not json_datos["data"].get("disease"):
        return []

    datos_disease = json_datos["data"]["disease"]

    try:
        mi_disease = Disease(datos_disease["id"], datos_disease["name"], [])
    except ValueError:
        return []

    lista_asociaciones = []

    filas = datos_disease.get("associatedTargets", {}).get("rows", [])
    for fila in filas:
        datos_target = fila["target"]
        score = fila.get("score", 0.0)

        # tractabilidad puede no venir en esta query, pongo lista vacia
        lista_tract = []
        for t in datos_target.get("tractability", []) or []:
            lista_tract.append(
                TractabilityItem(t["label"], t["modality"], t["value"])
            )

        try:
            mi_target = Target(
                datos_target["id"],
                datos_target["approvedSymbol"],
                datos_target.get("biotype", ""),
                lista_tract,
            )
        except ValueError:
            continue

        # Fabricamos una "evidencia agregada" con el score que da la API.
        # No es ideal (perdemos detalle de las evidencias individuales)
        # pero es lo que tenemos en esta query inversa.
        try:
            ev_agregada = Evidence(
                id=f"agg-{datos_target['id']}",
                score=score,
                datatypeId="aggregated_score",
            )
        except ValueError:
            continue

        lista_asociaciones.append(
            Association(mi_target, mi_disease, [ev_agregada])
        )

    return lista_asociaciones