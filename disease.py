# disease.py
# Clase Disease. La práctica 1 pedía que el id empezara por "EFO_",
# pero al cargar datos de la API real de Open Targets resulta que muchas
# enfermedades vienen con otros prefijos (MONDO_, Orphanet_, HP_, etc.)
# porque la plataforma integra varias ontologías.
# He ampliado los prefijos aceptados para no descartar la mayoría de los
# datos reales. Se justifica en el README.


class Disease:
    # ontologías que acepto. EFO es la principal pero las otras vienen
    # mezcladas en las respuestas reales de Open Targets.
    PREFIJOS_VALIDOS = (
        "EFO_",
        "MONDO_",
        "Orphanet_",
        "HP_",
        "OTAR_",
        "GO_",
        "DOID_",
        "NCIT_",
        "OBA_",
    )

    def __init__(self, id: str, name, fen_list: list):
        # validacion: id valido + nombre no vacio
        if not id.startswith(Disease.PREFIJOS_VALIDOS) or name == "":
            raise ValueError("The id or name is not correct")

        self.id = id
        self.name = name
        self.fen_list = fen_list

    def has_phenotype(self, name: str):
        # case-insensitive: el README de la practica 1 lo pide
        for phenotype in self.fen_list:
            if phenotype.lower() == name.lower():
                return True
        return False

    def __eq__(self, other):
        return isinstance(other, Disease) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"<Disease {self.id} ({self.name})>"
