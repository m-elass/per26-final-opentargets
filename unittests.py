'''hacer muchos test y comentarios'''
# unittests.py
# Bateria de pruebas unitarias para el servidor de Open Targets.
#
# El README de la practica pide probar como minimo:
#   - Filtrado logico (por Target ID, Disease ID, score)
#   - Ordenacion con __lt__
#   - Gestion de parametros (query strings, casos limite)
#   - Gestion de casos vacios
#
# Como no quiero abrir sockets de verdad en los tests (lento y poco
# reproducible), instancio ServidorOpenTargets con un mock minimo que
# no llama al constructor de BaseHTTPRequestHandler. Asi puedo probar
# los metodos auxiliares directamente.

import unittest

from target import Target, TractabilityItem
from disease import Disease
from evidence import Evidence, GeneticEvidence, IndirectEvidence
from association import Association
from servidor import ServidorOpenTargets


def hacer_handler():
    """Instancia ServidorOpenTargets sin pasar por __init__ del padre.

    Esto me permite usar los metodos del handler sin tener que abrir un
    socket real ni hacer peticiones HTTP de verdad.
    """
    handler = ServidorOpenTargets.__new__(ServidorOpenTargets)
    return handler


# --- FIXTURE: objetos de ejemplo que usan varios tests ---------------

def crear_target(id="ENSG00000141510", simbolo="TP53", druggable=True):
    tract = []
    if druggable:
        tract.append(TractabilityItem("Approved Drug", "SM", True))
    return Target(id, simbolo, "protein_coding", tract)


def crear_disease(id="EFO_0000305", nombre="breast carcinoma", fenotipos=None):
    return Disease(id, nombre, fenotipos or [])


def crear_asociacion(target, disease, scores):
    """Crea una Association con evidencias Evidence basicas con esos scores."""
    evs = [Evidence(f"ev_{i}", s, "literature") for i, s in enumerate(scores)]
    return Association(target, disease, evs)


# --- CLASES DE DOMINIO -----------------------------------------------

class TestTarget(unittest.TestCase):
    """Pruebas de la clase Target."""

    def test_01_target_id_debe_empezar_por_ensg(self):
        # Constructor valida el prefijo
        with self.assertRaises(ValueError):
            Target("XYZ12345", "FOO", "protein_coding", [])

    def test_02_target_druggable_aprobado(self):
        # con un TractabilityItem aprobado, is_druggable -> True
        t = Target(
            "ENSG00000001",
            "TEST",
            "protein_coding",
            [TractabilityItem("Approved Drug", "SM", True)],
        )
        self.assertTrue(t.is_druggable())

    def test_03_target_no_druggable_si_no_hay_approved_drug(self):
        # con TractabilityItems pero ninguno con Approved Drug y True
        t = Target(
            "ENSG00000002",
            "TEST",
            "protein_coding",
            [TractabilityItem("Phase 1 Clinical", "SM", True),
             TractabilityItem("Approved Drug", "SM", False)],
        )
        self.assertFalse(t.is_druggable())

    def test_04_targets_iguales_por_id(self):
        a = Target("ENSG00000003", "FOO", "protein_coding", [])
        b = Target("ENSG00000003", "BAR", "lncRNA", [])
        self.assertEqual(a, b)  # mismo id -> son iguales


class TestDisease(unittest.TestCase):
    """Pruebas de la clase Disease, incluyendo la ampliacion de prefijos."""

    def test_05_disease_prefijo_efo_valido(self):
        d = Disease("EFO_0001", "x", [])
        self.assertEqual(d.id, "EFO_0001")

    def test_06_disease_prefijo_mondo_aceptado(self):
        # esta es la mejora: aceptar prefijos de la API real
        d = Disease("MONDO_0001", "alzheimer", [])
        self.assertEqual(d.name, "alzheimer")

    def test_07_disease_prefijo_invalido_lanza_error(self):
        with self.assertRaises(ValueError):
            Disease("INVENTADO_1", "x", [])

    def test_08_disease_nombre_vacio_lanza_error(self):
        with self.assertRaises(ValueError):
            Disease("EFO_0001", "", [])

    def test_09_has_phenotype_case_insensitive(self):
        d = Disease("EFO_0001", "x", ["Headache", "Fatigue"])
        self.assertTrue(d.has_phenotype("HEADACHE"))
        self.assertTrue(d.has_phenotype("fatigue"))
        self.assertFalse(d.has_phenotype("Cough"))


class TestEvidence(unittest.TestCase):
    """Pruebas de la jerarquia Evidence + polimorfismo de get_score."""

    def test_10_evidence_score_fuera_de_rango(self):
        with self.assertRaises(ValueError):
            Evidence("e", 1.5, "x")
        with self.assertRaises(ValueError):
            Evidence("e", -0.1, "x")

    def test_11_genetic_evidence_gwas_score_bajo(self):
        # regla del README: gwas_catalog con score < 0.05 -> ValueError
        with self.assertRaises(ValueError):
            GeneticEvidence("g", 0.04, "genetic_association", "gwas_catalog")

    def test_12_indirect_evidence_aplica_factor_08(self):
        ind = IndirectEvidence("i", 0.5, "literature")
        # el polimorfismo hace que get_score() multiplique por 0.8
        self.assertAlmostEqual(ind.get_score(), 0.4)


# --- ASSOCIATION: SCORE TOTAL Y ORDENACION ---------------------------

class TestAssociation(unittest.TestCase):

    def test_13_score_total_media_de_evidencias(self):
        t = crear_target()
        d = crear_disease()
        a = crear_asociacion(t, d, [0.5, 0.7, 0.9])
        # media = 0.7
        self.assertAlmostEqual(a.get_total_score(), 0.7, places=3)

    def test_14_score_total_sin_evidencias_es_cero(self):
        t = crear_target()
        d = crear_disease()
        a = Association(t, d, [])
        self.assertEqual(a.get_total_score(), 0.0)

    def test_15_polimorfismo_mezcla_directa_e_indirecta(self):
        # 0.8 (Evidence) + 0.8*0.8 (IndirectEvidence) = 1.44 / 2 = 0.72
        t = crear_target()
        d = crear_disease()
        evs = [
            Evidence("e1", 0.8, "literature"),
            IndirectEvidence("e2", 0.8, "literature"),
        ]
        a = Association(t, d, evs)
        self.assertAlmostEqual(a.get_total_score(), 0.72, places=3)

    def test_16_top_evidence_es_la_mejor(self):
        t = crear_target()
        d = crear_disease()
        a = crear_asociacion(t, d, [0.3, 0.9, 0.5])
        top = a.get_top_evidence()
        self.assertEqual(top.score, 0.9)

    def test_17_lt_ordena_de_mayor_a_menor_con_reverse(self):
        # creo tres asociaciones con scores distintos y compruebo el sort
        t = crear_target()
        d1 = crear_disease("EFO_0001", "una")
        d2 = crear_disease("EFO_0002", "dos")
        d3 = crear_disease("EFO_0003", "tres")
        a1 = crear_asociacion(t, d1, [0.3])
        a2 = crear_asociacion(t, d2, [0.9])
        a3 = crear_asociacion(t, d3, [0.6])

        ordenadas = sorted([a1, a2, a3], reverse=True)
        # de mayor a menor: 0.9, 0.6, 0.3
        self.assertEqual(ordenadas[0].disease.id, "EFO_0002")
        self.assertEqual(ordenadas[1].disease.id, "EFO_0003")
        self.assertEqual(ordenadas[2].disease.id, "EFO_0001")


# --- FILTRADO LOGICO (lo que pide el README explicitamente) ----------

class TestFiltrado(unittest.TestCase):

    def setUp(self):
        # creo varias asociaciones de ejemplo con datos variados
        t1 = crear_target("ENSG00000001", "GEN1", druggable=True)
        t2 = crear_target("ENSG00000002", "GEN2", druggable=False)
        d1 = crear_disease("EFO_0001", "una")
        d2 = crear_disease("EFO_0002", "dos")
        d3 = crear_disease("MONDO_0001", "tres")
        self.asocs = [
            crear_asociacion(t1, d1, [0.9]),  # score alto
            crear_asociacion(t1, d2, [0.5]),  # score medio
            crear_asociacion(t2, d3, [0.2]),  # score bajo
            crear_asociacion(t2, d1, [0.8]),  # otra alta
        ]
        self.handler = hacer_handler()

    def test_18_filtrar_por_target_id(self):
        res = self.handler.filtrar_asociaciones(
            self.asocs, target_id="ENSG00000001", disease_id="", mscore=0.0
        )
        self.assertEqual(len(res), 2)
        for a in res:
            self.assertEqual(a.target.id, "ENSG00000001")

    def test_19_filtrar_por_disease_id(self):
        res = self.handler.filtrar_asociaciones(
            self.asocs, target_id="", disease_id="EFO_0001", mscore=0.0
        )
        # dos asociaciones tienen EFO_0001
        self.assertEqual(len(res), 2)

    def test_20_filtrar_por_score_minimo(self):
        res = self.handler.filtrar_asociaciones(
            self.asocs, target_id="", disease_id="", mscore=0.6
        )
        # solo las que tienen score >= 0.6
        self.assertEqual(len(res), 2)
        for a in res:
            self.assertGreaterEqual(a.get_total_score(), 0.6)

    def test_21_filtrar_combinacion(self):
        res = self.handler.filtrar_asociaciones(
            self.asocs, target_id="ENSG00000001",
            disease_id="EFO_0001", mscore=0.0,
        )
        # solo hay una que cumpla las dos cosas
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].target.id, "ENSG00000001")
        self.assertEqual(res[0].disease.id, "EFO_0001")

    def test_22_filtrar_sin_criterios_devuelve_todo_ordenado(self):
        res = self.handler.filtrar_asociaciones(
            self.asocs, target_id="", disease_id="", mscore=0.0
        )
        self.assertEqual(len(res), 4)
        # debe estar ordenado de mayor a menor
        scores = [a.get_total_score() for a in res]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_23_filtrar_score_muy_alto_devuelve_vacio(self):
        # esto cubre el "caso vacio" del README
        res = self.handler.filtrar_asociaciones(
            self.asocs, target_id="", disease_id="", mscore=0.99
        )
        self.assertEqual(res, [])


# --- PARSEO Y VALIDACION DE QUERY STRINGS ----------------------------

class TestParsearParametros(unittest.TestCase):

    def setUp(self):
        self.h = hacer_handler()

    def test_24_parsear_query_completa(self):
        q = "targetID=ENSG00000001&diseaseID=EFO_0001&mscore=0.5&source=local"
        p = self.h.parsear_parametros(q)
        self.assertEqual(p["targetID"], "ENSG00000001")
        self.assertEqual(p["diseaseID"], "EFO_0001")
        self.assertEqual(p["mscore"], "0.5")
        self.assertEqual(p["source"], "local")

    def test_25_parsear_query_vacia(self):
        # todo a defaults
        p = self.h.parsear_parametros("")
        self.assertEqual(p["targetID"], "")
        self.assertEqual(p["diseaseID"], "")
        self.assertEqual(p["mscore"], "")
        self.assertEqual(p["source"], "api")  # api por defecto

    def test_26_parsear_parametros_con_espacios(self):
        # parse_qs maneja correctamente los %20 y +
        q = "targetID=%20ENSG00000001%20&mscore=0.5"
        p = self.h.parsear_parametros(q)
        # los espacios extra se quitan con strip()
        self.assertEqual(p["targetID"], "ENSG00000001")

    def test_27_parsear_solo_score(self):
        # buscar solo por umbral de score (el README lo permite)
        p = self.h.parsear_parametros("mscore=0.7")
        self.assertEqual(p["mscore"], "0.7")
        self.assertEqual(p["targetID"], "")


class TestValidarParametros(unittest.TestCase):

    def setUp(self):
        self.h = hacer_handler()

    def test_28_validar_score_numerico_ok(self):
        params = {"targetID": "ENSG001", "diseaseID": "", "mscore": "0.5", "source": "api"}
        ok, err = self.h.validar_parametros(params)
        self.assertIsNone(err)
        self.assertEqual(ok["mscore"], 0.5)

    def test_29_validar_score_no_numerico_devuelve_error(self):
        # caso "datos mal formados" del README
        params = {"targetID": "ENSG001", "diseaseID": "", "mscore": "abc", "source": "api"}
        _, err = self.h.validar_parametros(params)
        self.assertIsNotNone(err)

    def test_30_validar_score_fuera_de_rango(self):
        params = {"targetID": "ENSG001", "diseaseID": "", "mscore": "2.5", "source": "api"}
        _, err = self.h.validar_parametros(params)
        self.assertIsNotNone(err)

    def test_31_validar_todo_vacio_es_correcto(self):
        # el README permite que TODOS los campos esten vacios
        params = {"targetID": "", "diseaseID": "", "mscore": "", "source": "api"}
        ok, err = self.h.validar_parametros(params)
        self.assertIsNone(err)
        self.assertEqual(ok["mscore"], 0.0)

    def test_32_validar_source_invalido_se_corrige_a_api(self):
        params = {"targetID": "", "diseaseID": "", "mscore": "", "source": "hacker"}
        ok, _ = self.h.validar_parametros(params)
        self.assertEqual(ok["source"], "api")


# --- COLUMNAS POR RUTA -----------------------------------------------

class TestColumnasPorRuta(unittest.TestCase):

    def setUp(self):
        self.h = hacer_handler()

    def test_33_columnas_resultados_completas(self):
        titulo, cols, _ = self.h.columnas_para_ruta("/resultados", "X", "Y")
        # /resultados muestra vista completa
        self.assertIn("symbol", cols)
        self.assertIn("druggable", cols)
        self.assertIn("score", cols)

    def test_34_columnas_searchtarget_no_muestran_symbol(self):
        # En /searchTarget el symbol es redundante (ya filtras por target)
        _, cols, _ = self.h.columnas_para_ruta("/searchTarget", "X", "")
        self.assertNotIn("symbol", cols)
        self.assertIn("diseaseID", cols)

    def test_35_columnas_searchdisease_muestran_targets(self):
        # En /searchDisease nos interesan los targets
        _, cols, _ = self.h.columnas_para_ruta("/searchDisease", "", "Y")
        self.assertIn("targetID", cols)
        self.assertIn("druggable", cols)

    def test_36_resultados_incluye_tipo_evidencia(self):
        # el enunciado pide explicitamente "tipo de evidencia" en /resultados
        _, cols, _ = self.h.columnas_para_ruta("/resultados", "", "")
        self.assertIn("tipo_evidencia", cols)

    def test_37_celda_tipo_evidencia_devuelve_datatypeid(self):
        # _celda con col=tipo_evidencia debe devolver el datatypeId
        # de la evidencia con score mas alto
        t = crear_target()
        d = crear_disease()
        evs = [
            Evidence("e1", 0.3, "literature"),
            Evidence("e2", 0.9, "genetic_association"),  # esta es la top
            Evidence("e3", 0.5, "animal_model"),
        ]
        a = Association(t, d, evs)
        celda = self.h._celda(a, "tipo_evidencia")
        self.assertEqual(celda, "genetic_association")


# --- INTEGRACION: PROCESADO COMPLETO DE JSON LOCAL -------------------

class TestProcesadoLocal(unittest.TestCase):
    """Probamos que el procesador convierte bien JSON -> objetos."""

    def test_38_json_local_target_genera_asociaciones(self):
        from data_local import obtener_datos_local
        from procesar_api import procesar_json_a_asociaciones

        datos = obtener_datos_local("ENSG00000141510")
        asocs = procesar_json_a_asociaciones(datos)
        # data_local.json tiene varias enfermedades de TP53
        self.assertGreater(len(asocs), 0)
        # todas son del mismo target
        for a in asocs:
            self.assertEqual(a.target.id, "ENSG00000141510")
            self.assertEqual(a.target.approvedSymbol, "TP53")

    def test_39_json_local_disease_genera_asociaciones(self):
        from data_local import obtener_disease_local
        from procesar_api import procesar_json_disease_a_asociaciones

        datos = obtener_disease_local("EFO_0000349")
        asocs = procesar_json_disease_a_asociaciones(datos)
        self.assertGreater(len(asocs), 0)
        # todas a la misma enfermedad
        for a in asocs:
            self.assertEqual(a.disease.id, "EFO_0000349")

    def test_40_json_con_errores_devuelve_lista_vacia(self):
        from procesar_api import procesar_json_a_asociaciones
        # caso vacio del README: si la API devuelve errores, lista vacia
        res = procesar_json_a_asociaciones(
            {"errors": [{"message": "Query is too expensive"}]}
        )
        self.assertEqual(res, [])

    def test_41_json_sin_data_devuelve_lista_vacia(self):
        from procesar_api import procesar_json_a_asociaciones
        self.assertEqual(procesar_json_a_asociaciones({}), [])

    def test_42_target_inexistente_local_devuelve_vacio(self):
        from data_local import obtener_datos_local
        from procesar_api import procesar_json_a_asociaciones
        datos = obtener_datos_local("ENSG99999999")
        asocs = procesar_json_a_asociaciones(datos)
        self.assertEqual(asocs, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)