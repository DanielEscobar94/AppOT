from flask_wtf import FlaskForm
from wtforms import SelectField, IntegerField, BooleanField, StringField, TextAreaField
from wtforms.validators import DataRequired, NumberRange


class PosFormatForm(FlaskForm):
    ticket_width = SelectField('Ancho de ticket', choices=[('80','80 mm'), ('88','88 mm')], validators=[DataRequired()])
    font_size = IntegerField('Tamano de fuente (px)', default=12, validators=[NumberRange(min=8, max=24)])
    show_company = BooleanField('Mostrar nombre de la empresa', default=True)
    include_address = BooleanField('Incluir direccion', default=True)
    auto_print = BooleanField('Auto imprimir al abrir', default=True)
    header_text = StringField('Texto de cabecera (opcional)')
    footer_text = TextAreaField('Texto de pie de pagina (opcional)')
