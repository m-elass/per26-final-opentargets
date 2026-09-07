# target.py
# Clases Target y TractabilityItem.
# Vienen de la practica anterior, las dejo casi igual pero he añadido algun
# comentario y el __lt__ por si hace falta ordenar targets sueltos.


class TractabilityItem:
    # Cada Target tiene una lista de estos. Lo saco de la API tal cual viene.
    def __init__(self, label: str, modality: str, value: bool):
        self.label = label
        self.modality = modality
        self.value = value

    def __repr__(self):
        # me ayuda al hacer prints durante el desarrollo
        return f"<TractabilityItem {self.label}={self.value}>"


class Target:
    def __init__(self, id: str, approvedSymbol, biotype, tractability_Item: list):
        # comprobacion rapida: los Ensembl Gene IDs siempre empiezan por ENSG
        if not id.startswith("ENSG"):
            raise ValueError("El ID debe empezar por ENSG")

        self.id = id
        self.approvedSymbol = approvedSymbol
        self.biotype = biotype
        self.tractability_Item = tractability_Item

    def is_druggable(self):
        # un target es "atacable" por un farmaco si tiene un item con
        # label "Approved Drug" y value True. Suficiente con que haya uno.
        for item in self.tractability_Item:
            if item.label == "Approved Drug" and item.value is True:
                return True
        return False

    def __eq__(self, other):
        # dos Targets son iguales si comparten id
        return isinstance(other, Target) and self.id == other.id

    def __hash__(self):
        # necesario para poder meterlos en sets / dicts
        return hash(self.id)

    def __repr__(self):
        return f"<Target {self.id} ({self.approvedSymbol})>"
