# evidence.py
# Jerarquia de evidencias: clase base + dos subclases.
# El polimorfismo de get_score() es la clave para que Association
# calcule la media correctamente sin saber el tipo concreto de cada
# evidencia.


class Evidence:
    def __init__(self, id: str, score: float, datatypeId: str):
        # el score viene de Open Targets ya normalizado entre 0 y 1
        if not (0.0 <= score <= 1.0):
            raise ValueError("Valor fuera de rango!")
        self.id = id
        self.score = score
        self.datatypeId = datatypeId

    def get_score(self):
        return self.score

    def __repr__(self):
        return f"<Evidence {self.id} score={self.score}>"


class GeneticEvidence(Evidence):
    # Evidencia genetica directa. Lleva un sourceId extra que indica
    # de donde viene (gwas_catalog, gene_burden, etc.)
    def __init__(self, id, score, datatypeId, sourceId):
        super().__init__(id, score, datatypeId)
        self.sourceId = sourceId

        # filtro del README de la practica 1: si la fuente es gwas_catalog
        # y el score es muy bajo, lo descartamos (Open Targets aplica este
        # umbral en su pipeline)
        if sourceId == "gwas_catalog" and score < 0.05:
            raise ValueError("ERROR")


class IndirectEvidence(Evidence):
    # Evidencia indirecta: viene propagada desde enfermedades descendientes
    # en la ontologia EFO. Por eso se penaliza con un factor 0.8 al obtener
    # su score (es menos fiable que una evidencia directa).
    def __init__(self, id, score, datatypeId):
        super().__init__(id, score, datatypeId)

    def get_score(self):
        # sobreescribo el metodo del padre para aplicar el 0.8.
        # Asi cuando Association recorre la lista y va llamando a
        # get_score() en cada elemento, las indirectas devuelven solas
        # su score "penalizado" sin que Association tenga que saber el tipo.
        return super().get_score() * 0.8