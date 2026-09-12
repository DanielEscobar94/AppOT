# forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, HiddenField
from wtforms.validators import DataRequired

class OrdenForm(FlaskForm):
    client_id = HiddenField(validators=[DataRequired()])
    categoria = SelectField('Categoria', choices=[
    ('Reloj', 'Reloj'),
    ('Bateria', 'Bateria'),
    ('Articulo electronico', 'Articulo electronico')
    ], validators=[DataRequired()])
    sku = StringField('SKU')
    marca = StringField('Marca', validators=[DataRequired()])
    referencia = StringField('Referencia')
    repuestos_usados = StringField('Repuestos usados')
    descripcion = TextAreaField('Descripcion')
    tecnico_id = SelectField('Tecnico encargado', coerce=int, validators=[DataRequired()])
    branch_id = SelectField('Sucursal', coerce=int, validators=[DataRequired()])