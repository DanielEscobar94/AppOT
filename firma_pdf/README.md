# Firma PDF (uso personal)

App local para estampar tu firma (imagen) en un PDF, junto con una línea de
metadata: nombre completo, cédula, lugar y fecha/hora. Todo se procesa en tu
equipo; nada se sube a internet.

## Uso
```bash
cd firma_pdf
pip install -r requirements.txt
# edita perfil.json con tus datos
python app.py
```
Abre http://127.0.0.1:5001, carga el PDF y la imagen de tu firma (PNG con
fondo transparente se ve mejor), elige página y posición y pulsa **Firmar**.
La fecha y hora se agregan automáticamente; nombre, cédula y lugar vienen de
`perfil.json` (puedes cambiarlos en el formulario para una firma puntual, o
guardarlos como nuevos valores por defecto con la casilla "Guardar").

Además de dibujar el texto, se escriben en los metadatos del PDF
(`/Signer`, `/SignerID`, `/SignedAt`, `/SignedPlace`).

> Es una firma visual/gráfica, no una firma digital con certificado (PKI).
