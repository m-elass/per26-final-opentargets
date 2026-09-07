#!/usr/bin/python
# servidor.py
#
# Servidor HTTP basado en BaseHTTPRequestHandler (sin frameworks externos)
# que sirve la interfaz de consulta de Open Targets.
# Soporta GET y POST en las rutas de busqueda. Soporta dos origenes de
# datos: la API GraphQL real de Open Targets y ficheros JSON locales.

import json
import html
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from data1 import obtener_datos_api, obtener_targets_de_disease
from data_local import obtener_datos_local, obtener_disease_local
from procesar_api import (
    procesar_json_a_asociaciones,
    procesar_json_disease_a_asociaciones,
)


# Si el usuario hace una busqueda general sin indicar Target ID y pide
# datos de la API, le pongo este target por defecto y le aviso. La API
# necesita un punto de entrada y TP53 es uno de los genes con mas
# asociaciones conocidas, asi siempre habra resultados.
TARGET_POR_DEFECTO = "ENSG00000141510"  # TP53


class ServidorOpenTargets(BaseHTTPRequestHandler):

    # --- UTILIDADES BASICAS DE RESPUESTA HTTP -----------------------

    def set_response(self, status_code=200, content_type="text/html; charset=utf-8"):
        """Cabeceras + status, dejo el cuerpo listo para escribir."""
        self.send_response(status_code)
        self.send_header("Content-type", content_type)
        self.end_headers()

    def enviar_html(self, html, status=200):
        """Atajo: cabeceras + cuerpo HTML."""
        self.set_response(status)
        self.wfile.write(html.encode("utf-8"))

    def enviar_json(self, datos_dict, status=200, nombre_archivo="resultados.json"):
        """Envia un JSON para descarga."""
        self.send_response(status)
        self.send_header("Content-type", "application/json; charset=utf-8")
        # Content-Disposition con attachment hace que el navegador descargue
        # el fichero en lugar de mostrarlo
        self.send_header(
            "Content-Disposition", f'attachment; filename="{nombre_archivo}"'
        )
        self.end_headers()
        payload = json.dumps(datos_dict, indent=2, ensure_ascii=False)
        self.wfile.write(payload.encode("utf-8"))

    def leer_html(self, nombre_archivo):
        """Lee un fichero HTML del disco. Si no existe, devuelvo HTML de error."""
        try:
            with open(nombre_archivo, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return f"<h1>Error</h1><p>No se encuentra {nombre_archivo}</p>"

    # --- PASO 1: PARSEAR PARAMETROS ---------------------------------

    def parsear_parametros(self, query_string):
        """Convierte una query string en un diccionario normalizado.

        Uso parse_qs en lugar de hacer split manual porque maneja
        correctamente caracteres especiales (%20, +, acentos, etc.).
        """
        crudo = parse_qs(query_string, keep_blank_values=True)

        return {
            "targetID": crudo.get("targetID", [""])[0].strip(),
            "diseaseID": crudo.get("diseaseID", [""])[0].strip(),
            "mscore": crudo.get("mscore", [""])[0].strip(),
            "source": crudo.get("source", ["api"])[0].strip().lower(),
        }

    # --- PASO 2: VALIDAR Y NORMALIZAR -------------------------------

    def validar_parametros(self, params):
        """Comprueba que los parametrs tengan sentido.

        Devuelv (params_normalizados, error). Si error es None, todo OK.

        El README de la practica permite que cualquier campo este vacio,
        asi que NO obligo a meter targetID. La unica validacion 
        es que el score, si esta, sea numerico y entre 0 y 1.
        """
        mscore_raw = params.get("mscore", "").strip()
        if mscore_raw == "":
            # vacio -> 0.0 por defecto (no filtra)
            mscore = 0.0
        else:
            try:
                mscore = float(mscore_raw)
            except ValueError:
                return None, "El score minimo debe ser un numero valido."

        if not (0.0 <= mscore <= 1.0):
            return None, "El score minimo debe estar entre 0.0 y 1.0."

        # source solo puede ser 'api' o 'local'. Cualquier otr cosa -> api
        source = params.get("source", "api")
        if source not in ("api", "local"):
            source = "api"

        return (
            {
                "targetID": params.get("targetID", "").strip(),
                "diseaseID": params.get("diseaseID", "").strip(),
                "mscore": mscore,
                "source": source,
            },
            None,
        )

    # --- PASO 3: CARGAR DATOS DE LA FUENTE ELEGDA ------------------

    def cargar_asociaciones_target(self, target_id, source="api"):
        """Carga asociaciones partiendo de un Target.

        Si no se pasa target_id y la fuente es API, uso TARGET_POR_DEFECTO.
        Si la fuente es local, sin target_id devuelvo todo el fichero.
        """
        if source == "local":
            json_datos = obtener_datos_local(target_id if target_id else None)
        else:
            target_consulta = target_id if target_id else TARGET_POR_DEFECTO
            json_datos = obtener_datos_api(target_consulta)

        return procesar_json_a_asociaciones(json_datos)

    def cargar_asociaciones_disease(self, efo_id, source="api"):
        """Carga asociaciones partiendo de una Disease .

        Esto es lo que usa /searchDisease. Si no hay efo_id y la fuente es API,
        no puedo consultar , asi que devuelvo
        lista vacia. En modo local, sin efo_id devuelvo el contenido del JSON.
        """
        if not efo_id and source == "api":
            return []

        if source == "local":
            json_datos = obtener_disease_local(efo_id if efo_id else None)
        else:
            json_datos = obtener_targets_de_disease(efo_id)

        return procesar_json_disease_a_asociaciones(json_datos)

    # --- PASO 4: FILTRAR Y ORDENAR ----------------------

    def filtrar_asociaciones(self, asociaciones, target_id, disease_id, mscore):
        """Aplica los tres filtros opcionales y ordena por score descendente."""
        resultado = []
        for asoc in asociaciones:
            # filtro por target (solo si se especifico)
            if target_id and asoc.target.id != target_id:
                continue
            # filtro por disease (solo si se especifico)
            if disease_id and asoc.disease.id != disease_id:
                continue
            # filtro por score (siempre se aplica; mscore=0.0 lo deja pasar todo)
            if asoc.get_total_score() < mscore:
                continue
            resultado.append(asoc)

        # ordeno usando __lt__ de Association (de mayor a menor score)
        resultado.sort(reverse=True)
        return resultado

    # --- PASO 5: ELEGIR COLUMNAS Y TITULO SEGUN LA RUTA -------------

    def columnas_para_ruta(self, ruta, target_id, disease_id):
        """Cada ruta muestra columnas distintas segun lo que el usaurio quiere ver."""
        if ruta == "/searchTarget":
            return (
                f"Enfermedades asociadas al target {target_id or 'por defecto'}",
                ["disease", "diseaseID", "score", "tipo_evidencia", "n_evidencias"],
                ["Enfermedad", "Disease ID", "Score", "Tipo evidencia", "Nº evidencias"],
            )
        if ruta == "/searchDisease":
            return (
                f"Targets asociados a {disease_id or '(sin filtro)'}",
                ["symbol", "targetID", "score", "druggable"],
                ["Símbolo", "Target ID", "Score", "Druggable"],
            )
        # /resultados -> vista completa por defecto
        # Incluyo "tipo de evidencia" porque el enunciado lo pide
        # explicitamente como "dato mas relevante"
        return (
            "Resultados de la búsqueda",
            ["symbol", "disease", "score", "druggable", "tipo_evidencia", "n_evidencias"],
            ["Símbolo", "Enfermedad", "Score Total", "Druggable", "Tipo evidencia", "Nº evidencias"],
        )

    # --- CONSTRUCCION DE LA TABLA HTML ---------------------------

    def _celda(self, asoc, col):
        """Valor de la celda segun la columna pedida.

         paso todo por html.escape para evitar que algun campo
        traiga caracteres raros (<, >, &) que rompan la tabla. 
        """
        if col == "symbol":
            return html.escape(asoc.target.approvedSymbol)
        if col == "targetID":
            return html.escape(asoc.target.id)
        if col == "disease":
            return html.escape(asoc.disease.name)
        if col == "diseaseID":
            return html.escape(asoc.disease.id)
        if col == "score":
            return f"{asoc.get_total_score():.4f}"
        if col == "druggable":
            return "Sí" if asoc.target.is_druggable() else "No"
        if col == "n_evidencias":
            return str(len(asoc.evidence_list))
        if col == "tipo_evidencia":
            # tipo de la evidencia con score mas alto (predominante).
            # Lo pide el enunciado en "datos mas relevantes"
            top = asoc.get_top_evidence()
            return html.escape(top.datatypeId) if top else "-"
        return ""

    def construir_filas(self, asociaciones, columnas):
        """Genera los <tr> a partir de la lista de asociaciones."""
        filas = ""
        for asoc in asociaciones:
            celdas = "".join(
                f"<td style='padding:8px'>{self._celda(asoc, c)}</td>"
                for c in columnas
            )
            filas += f"<tr>{celdas}</tr>"
        return filas

    def render_tabla(self, titulo, asociaciones, columnas, cabeceras, query_actual=""):
        """Devuelve el HTML completo de la pagina de resultados.

        query_actual es la query string original, la paso al boton de
        descarga para que el endpoint sepa exactamente que datos generar.
        """
        # boton de descarga JSON (solo si hay resultados)
        boton_descarga = ""
        if asociaciones:
            boton_descarga = (
                f"<a href='/resultados/download?{query_actual}' class='dl'>"
                f"📥 Descargar resultados (JSON)</a>"
            )

        if not asociaciones:
            cuerpo = (
                "<div class='empty'>🔍 No se han encontrado asociaciones "
                "que coincidan con los criterios introducidos.</div>"
            )
        else:
            ths = "".join(f"<th>{h}</th>" for h in cabeceras)
            filas = self.construir_filas(asociaciones, columnas)
            cuerpo = f"""
            <p class='count'>{len(asociaciones)} resultado(s) encontrados</p>
            <table>
              <thead><tr>{ths}</tr></thead>
              <tbody>{filas}</tbody>
            </table>"""

        # estilos en linea para que la pagina se vea bonita 
        estilos = """
        <style>
          * { box-sizing: border-box; margin: 0; padding: 0; }
          body { font-family: -apple-system, 'Segoe UI', sans-serif;
                 background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f0c29 100%);
                 min-height: 100vh; padding: 40px 20px; color: #e0e0e0; }
          .wrap { max-width: 1100px; margin: 0 auto;
                  background: rgba(255,255,255,0.05); backdrop-filter: blur(20px);
                  border: 1px solid rgba(177,74,255,0.2);
                  border-radius: 16px; padding: 40px;
                  box-shadow: 0 20px 60px rgba(0,0,0,0.5); }
          h2 { color: #fff; margin-bottom: 8px; font-size: 1.8em; }
          .count { color: #b14aff; font-weight: 600; margin-bottom: 24px; }
          table { width: 100%; border-collapse: separate; border-spacing: 0;
                  border-radius: 10px; overflow: hidden;
                  background: rgba(0,0,0,0.3); }
          thead { background: linear-gradient(135deg, #4a90ff, #b14aff); color: white; }
          th { padding: 14px 12px; font-weight: 600; text-align: left;
               text-transform: uppercase; font-size: 0.85em; letter-spacing: 0.5px; }
          tbody tr { border-bottom: 1px solid rgba(177,74,255,0.1); transition: all 0.2s ease; }
          tbody tr:hover { background: rgba(177,74,255,0.08); }
          td { padding: 14px 12px; color: #e0e0e0; }
          .empty { text-align: center; padding: 40px; color: #888; font-size: 1.1em; }
          .actions { margin-top: 24px; display: flex; gap: 12px; flex-wrap: wrap; }
          .back, .dl {
              display: inline-block; padding: 12px 26px;
              background: linear-gradient(135deg, #4a90ff, #b14aff);
              color: white; text-decoration: none;
              border-radius: 8px; font-weight: 600;
              transition: transform 0.3s ease, box-shadow 0.3s ease;
          }
          .dl { background: linear-gradient(135deg, #b14aff, #ff4a4a); }
          .back:hover, .dl:hover { transform: translateY(-2px);
                                   box-shadow: 0 8px 20px rgba(177,74,255,0.4); }
          .aviso { background: rgba(255, 200, 0, 0.15);
                   border-left: 4px solid #f0c040;
                   padding: 12px 16px; border-radius: 6px;
                   margin-bottom: 20px; color: #f0d080; }
        </style>"""

        return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>{titulo}</title>{estilos}</head>
<body>
<div class="wrap">
  <h2>{titulo}</h2>
  {cuerpo}
  <div class="actions">
    <a href="/index.html" class="back">← Volver al buscador</a>
    {boton_descarga}
  </div>
</div>
</body></html>"""

    # --- ORQUESTADOR PRINCIPAL DE BUSQUEDAS -------------------------

    def procesar_busqueda(self, query_string, ruta):
        """Coordina los 5 pasos para servir una busqueda."""

        # 1. Parsear
        params = self.parsear_parametros(query_string)

        # 2. Validar
        params_ok, error = self.validar_parametros(params)
        if error:
            self.enviar_html(
                f"<h1>La consulta no tiene los datos bien formados.</h1>"
                f"<p>{error}</p><a href='/'>Volver</a>",
                400,
            )
            return

        # 3-4. Cargar y filtrar (segun la ruta y la fuente)
        try:
            if ruta == "/searchDisease":
                # query inversa: parto de la enfermedad
                todas = self.cargar_asociaciones_disease(
                    params_ok["diseaseID"], params_ok["source"]
                )
            else:
                # /resultados y /searchTarget: parto del target
                todas = self.cargar_asociaciones_target(
                    params_ok["targetID"], params_ok["source"]
                )

            filtradas = self.filtrar_asociaciones(
                todas,
                params_ok["targetID"],
                params_ok["diseaseID"],
                params_ok["mscore"],
            )
        except Exception as e:
            # red de seguridad si algo se rompe que el servidor no se caiga
            self.enviar_html(
                f"<h1>Error interno del servidor.</h1><p>{e}</p>", 500
            )
            return

        # 5. Renderizar
        titulo, columnas, cabeceras = self.columnas_para_ruta(
            ruta, params_ok["targetID"], params_ok["diseaseID"]
        )
        html = self.render_tabla(
            titulo, filtradas, columnas, cabeceras, query_actual=query_string
        )

        # Aviso amigable si hemos completado target por defecto
        if (
            ruta != "/searchDisease"
            and not params_ok["targetID"]
            and params_ok["source"] == "api"
        ):
            aviso = (
                f"<div class='aviso'>ℹ️ No has especificado un Target ID, "
                f"así que muestro resultados para <b>{TARGET_POR_DEFECTO}</b> "
                f"(TP53) por defecto. La API necesita un punto de entrada.</div>"
            )
            html = html.replace(f"<h2>{titulo}</h2>", f"<h2>{titulo}</h2>{aviso}", 1)

        self.enviar_html(html)

    # --- DESCARGA JSON DE RESULTADOS----------------

    def descargar_resultados(self, query_string, ruta_origen="/resultados"):
        """Construye un JSON estructurado con los resultados actuales."""
        params = self.parsear_parametros(query_string)
        params_ok, error = self.validar_parametros(params)
        if error:
            self.enviar_html(f"<h1>Error: {error}</h1>", 400)
            return

        try:
            if ruta_origen == "/searchDisease":
                todas = self.cargar_asociaciones_disease(
                    params_ok["diseaseID"], params_ok["source"]
                )
            else:
                todas = self.cargar_asociaciones_target(
                    params_ok["targetID"], params_ok["source"]
                )
            filtradas = self.filtrar_asociaciones(
                todas,
                params_ok["targetID"],
                params_ok["diseaseID"],
                params_ok["mscore"],
            )
        except Exception as e:
            self.enviar_html(f"<h1>Error: {e}</h1>", 500)
            return

        # estructura del JSON descargable. La documento en el README.
        payload = {
            "metadata": {
                "consulta": {
                    "targetID": params_ok["targetID"],
                    "diseaseID": params_ok["diseaseID"],
                    "score_minimo": params_ok["mscore"],
                    "origen_datos": params_ok["source"],
                },
                "total_resultados": len(filtradas),
            },
            "asociaciones": [],
        }

        for asoc in filtradas:
            payload["asociaciones"].append(
                {
                    "target": {
                        "id": asoc.target.id,
                        "approvedSymbol": asoc.target.approvedSymbol,
                        "biotype": asoc.target.biotype,
                        "is_druggable": asoc.target.is_druggable(),
                    },
                    "disease": {
                        "id": asoc.disease.id,
                        "name": asoc.disease.name,
                    },
                    "score_total": asoc.get_total_score(),
                    "n_evidencias": len(asoc.evidence_list),
                    "evidencias": [
                        {
                            "id": ev.id,
                            "score": ev.get_score(),
                            "datatypeId": ev.datatypeId,
                            "tipo": type(ev).__name__,
                        }
                        for ev in asoc.evidence_list
                    ],
                }
            )

        self.enviar_json(payload, nombre_archivo="opentargets_resultados.json")

    # ----------------------

    def do_GET(self):
        url = urlparse(self.path)
        ruta = url.path

        if ruta in ("/", "/index.html", "/index.htm"):
            self.enviar_html(self.leer_html("index.html"))

        elif ruta == "/autor":
            self.enviar_html(self.leer_html("autor.html"))

        elif ruta == "/resultados/download":
            self.descargar_resultados(url.query, "/resultados")

        elif ruta == "/searchDisease/download":
            self.descargar_resultados(url.query, "/searchDisease")

        elif ruta == "/searchTarget/download":
            self.descargar_resultados(url.query, "/searchTarget")

        elif ruta in ("/resultados", "/searchTarget", "/searchDisease"):
            self.procesar_busqueda(url.query, ruta)

        else:
            # 404 obligatorio 
            self.enviar_html("<h1>Página no encontrada.</h1>", 404)

    def do_POST(self):
        # Leo el cuerpo de la peticion POST
        length = int(self.headers.get("Content-Length", 0))
        cuerpo = self.rfile.read(length).decode("utf-8")

        if self.path in ("/resultados", "/searchTarget", "/searchDisease"):
            self.procesar_busqueda(cuerpo, self.path)
        else:
            self.enviar_html("<h1>Página no encontrada.</h1>", 404)

    # silencio el log por defecto para no llenar la consola
    def log_message(self, format, *args):
        # comentar esta linea si se quiere ver el log de peticiones
        return


# --- ARRANQUE DEL SERVIDOR -------------------------------------------

def run(
    server_class=HTTPServer,
    handler_class=ServidorOpenTargets,
    host="127.0.0.1",
    port=21080,
):
    """Arranca el servidor en host:port y lo deja corriendo hasta Ctrl+C."""
    httpd = server_class((host, port), handler_class)
    print(f"Servidor de Open Targets arrancado en http://{host}:{port}")
    print("Pulsa Ctrl+C para parar.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nApagando el servidor limpiamente...")
        httpd.server_close()


if __name__ == "__main__":
    run()