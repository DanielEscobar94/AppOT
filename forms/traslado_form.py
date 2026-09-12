from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DateTimeField, SelectField, IntegerField
from wtforms.validators import DataRequired, Optional, Length

class TrasladoForm(FlaskForm):
    numero_traslado_siigo = StringField(
        'No. Traslado Siigo',
        validators=[DataRequired(message='El número de traslado es requerido'), Length(max=100)]
    )
    branch_origen_id = SelectField(
        'Sale de (Bodega Origen)',
        coerce=int,
        validators=[DataRequired(message='Seleccione la bodega de origen')]
    )
    branch_destino_id = SelectField(
        'Entra a (Bodega Destino)',
        coerce=int,
        validators=[DataRequired(message='Seleccione la bodega de destino')]
    )
    fecha = DateTimeField(
        'Fecha',
        format='%Y-%m-%dT%H:%M',
        validators=[DataRequired(message='La fecha es requerida')]
    )
    responsable = StringField(
        'Responsable',
        validators=[DataRequired(message='El responsable es requerido'), Length(max=200)]
    )
    observacion = TextAreaField(
        'Observación',
        validators=[Optional(), Length(max=500)]
    )
