from flask_wtf import FlaskForm
from wtforms import StringField, FloatField
from wtforms.validators import DataRequired, Length, Regexp

class ProductForm(FlaskForm):
    sku = StringField("SKU", validators=[
        DataRequired(message="El SKU es obligatorio"),
        Regexp(r"^[A-Za-z0-9\-]+$", message="Solo se permiten letras, numeros y guiones")
    ])

    nombre = StringField("Nombre", validators=[
        DataRequired(message="El nombre es obligatorio"),
        Length(min=2, max=100, message="Debe tener entre 2 y 100 caracteres")
    ])

    precio = FloatField("Precio", validators=[
        DataRequired(message="El precio es obligatorio")
    ])