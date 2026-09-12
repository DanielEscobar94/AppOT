from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired

class CompanyForm(FlaskForm):
    name = StringField('Nombre de la empresa', validators=[DataRequired()])
    address = StringField('Direccion', validators=[DataRequired()])
    phone = StringField('Telefono', validators=[DataRequired()])
