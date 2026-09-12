# forms/orden_trabajo_form.py

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, DecimalField, HiddenField, IntegerField
from wtforms.validators import DataRequired, Optional, Regexp, ValidationError
import re

def validar_solo_letras(form, field):
    """Validador personalizado que solo permite letras, espacios y acentos."""
    # Si el campo esta vacio, permitirlo (sera opcional en edicion)
    if not field.data or not field.data.strip():
        return
    
    # Patron que permite letras, espacios, acentos y caracteres especiales del espanol
    patron = r'^[a-zA-ZaeiouAEIOUnNuU\s]+$'
    if not re.match(patron, field.data.strip()):
        raise ValidationError('El nombre del responsable solo puede contener letras y espacios.')

def coerce_int_or_none(value):
    """Coerce para SelectField que convierte '' a None y el resto a int."""
    if value == '' or value is None:
        return None
    return int(value)

class OrdenTrabajoForm(FlaskForm):
    # Hidden fields are validated explicitly in the backend
    client_id = HiddenField(validators=[Optional()])
    branch_id = HiddenField(validators=[Optional()])

    # Choices will be populated dynamically from the DB table in the route (id, nombre)
    # Opcional porque ahora se usa el sistema de artículos con articulos_json
    categoria = SelectField("Articulo", choices=[], coerce=int, validators=[Optional()])

    # estado_equipo field removed - no longer needed

    sku = StringField("SKU", validators=[Optional()])
    # Opcional porque ahora cada artículo tiene su propia referencia
    referencia = StringField("Referencia", validators=[Optional()])
    # Opcional porque ahora cada artículo tiene su propia descripción
    descripcion = TextAreaField("Descripcion del problema", validators=[Optional()])

    # Marca del equipo
    from wtforms.validators import Optional
    marca = StringField("Marca", validators=[Optional()])

    anticipo_monto = DecimalField("Anticipo", validators=[Optional()])
    anticipo_metodo = SelectField("Metodo de pago", choices=[
        ("efectivo", "Efectivo"),
        ("tarjeta", "Tarjeta"),
        ("transferencia", "Transferencia")
    ], validators=[Optional()])
    
    
    from wtforms.validators import DataRequired
    tecnico_id = SelectField("Sitio de la Reparacion", coerce=coerce_int_or_none, validators=[Optional()])
    responsable = StringField("Responsable (quien elabora la OT)", validators=[validar_solo_letras])
    repuestos_usados = TextAreaField("Repuestos usados", validators=[Optional()])


