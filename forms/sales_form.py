from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, IntegerField, FieldList, FormField
from wtforms.validators import DataRequired, NumberRange

class ProductoVentaForm(FlaskForm):
    producto_id = SelectField("Producto", coerce=int, validators=[DataRequired()])
    cantidad = IntegerField("Cantidad", validators=[DataRequired(), NumberRange(min=1)])
    precio_unitario = DecimalField("Precio Unitario", places=2, validators=[DataRequired()])

class VentaForm(FlaskForm):
    cliente_id = SelectField("Cliente", coerce=int, validators=[DataRequired()])
    productos = FieldList(FormField(ProductoVentaForm), min_entries=1)