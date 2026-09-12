from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField
from wtforms.validators import DataRequired, Length

class BranchForm(FlaskForm):
    nombre = StringField("Nombre de la sucursal", validators=[
        DataRequired(), Length(min=2, max=100)
    ])
    direccion = StringField("Direccion", validators=[Length(max=200)])
    ciudad = StringField("Ciudad", validators=[Length(max=100)])
    estado = StringField("Estado", validators=[Length(max=100)])
    activo = BooleanField("Sucursal activa")