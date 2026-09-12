from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Length

class CategoryForm(FlaskForm):
    nombre = StringField("Nombre de la categoria", validators=[
        DataRequired(message="El nombre es obligatorio"),
        Length(min=2, max=50)
    ])