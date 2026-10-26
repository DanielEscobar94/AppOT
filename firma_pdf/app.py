import io
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

BASE = Path(__file__).parent
PERFIL = BASE / "perfil.json"
MAX_MB = 30

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024
app.secret_key = "firma-pdf-local"  # solo uso local (flash messages)

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

POSICIONES = {
    "abajo-derecha": "Abajo a la derecha",
    "abajo-centro": "Abajo al centro",
    "abajo-izquierda": "Abajo a la izquierda",
    "centro": "Centro",
    "arriba-derecha": "Arriba a la derecha",
    "arriba-izquierda": "Arriba a la izquierda",
}


def cargar_perfil():
    try:
        return json.loads(PERFIL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"nombre_completo": "", "cedula": "", "lugar": "",
                "zona_horaria": "America/Bogota"}


def fecha_texto(tz):
    ahora = datetime.now(ZoneInfo(tz))
    return ahora, f"{ahora.day} de {MESES[ahora.month - 1]} de {ahora.year}, {ahora:%H:%M}"


def bloque_firma(w, h, firma_png, lineas, posicion, ancho_firma=170, margen=36):
    """Devuelve (x, y) de la esquina inferior izquierda del bloque y sus dimensiones."""
    fw, fh = firma_png.size
    alto_firma = ancho_firma * fh / fw
    if alto_firma > 90:  # limita firmas muy altas
        alto_firma = 90
        ancho_firma = alto_firma * fw / fh
    tam, interlinea = 8, 10
    ancho_txt = max(len(l) for l in lineas) * tam * 0.5
    bw = max(ancho_firma, ancho_txt)
    bh = alto_firma + 4 + interlinea * len(lineas)
    vert, _, horiz = posicion.partition("-")
    if posicion == "centro":
        x, y = (w - bw) / 2, (h - bh) / 2
    else:
        y = margen if vert == "abajo" else h - margen - bh
        x = {"izquierda": margen, "centro": (w - bw) / 2}.get(horiz, w - margen - bw)
    return x, y, bw, alto_firma, ancho_firma, tam, interlinea


def firmar(pdf_bytes, firma_bytes, datos, pagina_sel, posicion):
    lector = PdfReader(io.BytesIO(pdf_bytes))
    if lector.is_encrypted:
        lector.decrypt("")
    n = len(lector.pages)

    firma = Image.open(io.BytesIO(firma_bytes)).convert("RGBA")
    bbox = firma.getbbox()  # recorta márgenes transparentes
    if bbox:
        firma = firma.crop(bbox)
    buf_img = io.BytesIO()
    firma.save(buf_img, "PNG")
    buf_img.seek(0)

    ahora, fecha = fecha_texto(datos["zona_horaria"])
    lineas = [datos["nombre_completo"],
              f"C.C. {datos['cedula']}",
              f"{datos['lugar']} - {fecha}"]

    if pagina_sel == "ultima":
        idx = [n - 1]
    elif pagina_sel == "primera":
        idx = [0]
    elif pagina_sel == "todas":
        idx = list(range(n))
    else:
        idx = [min(max(int(pagina_sel), 1), n) - 1]

    escritor = PdfWriter()
    for i, pag in enumerate(lector.pages):
        if i in idx:
            w, h = float(pag.mediabox.width), float(pag.mediabox.height)
            x, y, bw, afh, afw, tam, inter = bloque_firma(w, h, firma, lineas, posicion)
            capa = io.BytesIO()
            c = canvas.Canvas(capa, pagesize=(w, h))
            buf_img.seek(0)
            c.drawImage(ImageReader(buf_img), x, y + inter * len(lineas) + 4,
                        width=afw, height=afh, mask="auto")
            c.setFont("Helvetica", tam)
            for k, linea in enumerate(lineas):  # primera línea arriba
                c.drawString(x, y + inter * (len(lineas) - 1 - k) + 2, linea)
            c.save()
            capa.seek(0)
            pag.merge_page(PdfReader(capa).pages[0])
        escritor.add_page(pag)

    escritor.add_metadata({
        "/Signer": datos["nombre_completo"],
        "/SignerID": datos["cedula"],
        "/SignedPlace": datos["lugar"],
        "/SignedAt": ahora.isoformat(timespec="seconds"),
    })
    salida = io.BytesIO()
    escritor.write(salida)
    salida.seek(0)
    return salida


@app.get("/")
def index():
    return render_template("index.html", perfil=cargar_perfil(), posiciones=POSICIONES)


@app.post("/firmar")
def firmar_view():
    pdf = request.files.get("pdf")
    img = request.files.get("firma")
    if not pdf or not pdf.filename or not img or not img.filename:
        flash("Debes cargar el PDF y la imagen de la firma.")
        return redirect(url_for("index"))

    perfil = cargar_perfil()
    datos = {k: request.form.get(k, "").strip() or perfil.get(k, "")
             for k in ("nombre_completo", "cedula", "lugar")}
    datos["zona_horaria"] = perfil.get("zona_horaria", "America/Bogota")
    if not all(datos[k] for k in ("nombre_completo", "cedula", "lugar")):
        flash("Faltan nombre, cédula o lugar.")
        return redirect(url_for("index"))

    if request.form.get("guardar"):
        perfil.update({k: datos[k] for k in ("nombre_completo", "cedula", "lugar")})
        PERFIL.write_text(json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8")

    pagina = request.form.get("pagina", "ultima")
    if pagina == "numero":
        pagina = request.form.get("numero_pagina", "1") or "1"
    posicion = request.form.get("posicion", "abajo-derecha")
    if posicion not in POSICIONES:
        posicion = "abajo-derecha"

    try:
        salida = firmar(pdf.read(), img.read(), datos, pagina, posicion)
    except Exception as e:  # PDF/imagen inválidos
        flash(f"No se pudo firmar: {e}")
        return redirect(url_for("index"))

    nombre = Path(pdf.filename).stem + "_firmado.pdf"
    return send_file(salida, as_attachment=True, download_name=nombre,
                     mimetype="application/pdf")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
