from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileSize, FileRequired
from wtforms import SubmitField

# 2 MB maximo para el logo (suficiente para PNG/JPG web)
LOGO_MAX_BYTES = 2 * 1024 * 1024

class LogoForm(FlaskForm):
    # Nota: SVG excluido a proposito (puede contener JavaScript ejecutable).
    logo = FileField('Selecciona el logo', validators=[
        FileRequired(),
        FileAllowed(['png', 'jpg', 'jpeg', 'webp'],
                    'Solo imágenes (PNG, JPG o WEBP)'),
        FileSize(max_size=LOGO_MAX_BYTES,
                 message='El logo no debe superar los 2 MB'),
    ])
    submit = SubmitField('Actualizar logo')
