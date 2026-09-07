# association.py
# Une un Target con una Disease + lista de Evidence.
# El metodo get_total_score() es donde mas brilla el polimorfismo de evidencias.

# nota: no necesito importar Target ni Disease aqui porque solo guardo
# referencias a objetos ya construidos. Los imports estan en procesar_api.py


class Association:
    def __init__(self, target, disease, evidence_list):
        self.target = target
        self.disease = disease
        self.evidence_list = evidence_list

    def get_total_score(self) -> float:
        # Media de scores. Si no hay evidencias, score = 0 (decision propia,
        # asi luego puedo filtrar por umbral sin que de KeyError)
        if not self.evidence_list:
            return 0.0

        total_score = 0
        for evidence in self.evidence_list:
            # polimorfismo: get_score() devuelve el valor que corresponda
            # segun la subclase (IndirectEvidence devuelve *0.8 etc.)
            total_score += evidence.get_score()

        return float(total_score / len(self.evidence_list))

    def get_top_evidence(self):
        # Devuelve la evidencia con mejor score.
        # Lo uso en alguna columna de la tabla para mostrar "tipo predominante"
        if not self.evidence_list:
            return None

        list_scores = []
        for evidence in self.evidence_list:
            list_scores.append(evidence.get_score())

        index = list_scores.index(max(list_scores))
        return self.evidence_list[index]

    def __lt__(self, other):
        # Ordena las asociaciones por score total. Lo uso para que la tabla
        # de resultados salga ordenada de mayor a menor con sort(reverse=True)
        return self.get_total_score() < other.get_total_score()

    def __eq__(self, other):
        # dos asociaciones son iguales si comparten target y disease
        if not isinstance(other, Association):
            return False
        return self.target == other.target and self.disease == other.disease

    def __repr__(self):
        return (
            f"<Association {self.target.approvedSymbol} - "
            f"{self.disease.name} score={self.get_total_score():.3f}>"
        )