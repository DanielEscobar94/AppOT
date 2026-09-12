from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms.validators import DataRequired, ValidationError

# Validador para NIT con digito de verificacion
def validar_nit_con_dv(form, field):
    valor = field.data.strip()
    if '-' not in valor:
        raise ValidationError("Debe incluir el digito de verificacion. Ej: 123456789-1")
    partes = valor.split('-')
    if len(partes) != 2 or not partes[0].isdigit() or not partes[1].isdigit():
        raise ValidationError("El NIT y el digito deben ser numericos.")

class ClientForm(FlaskForm):
    # CSRF habilitado por defecto para seguridad
    # Si se necesita desactivar para API, hacerlo explicitamente en la ruta
    
    nombre = StringField("Nombre", validators=[DataRequired()])
    tipo = SelectField("Tipo de cliente", choices=[
        ('natural', 'Persona Natural'),
        ('empresa', 'Empresa')
    ])
    cc = StringField("Cedula")      # solo para naturales
    nit = StringField("NIT")        # solo para empresas
    telefono = StringField("Telefono")
    correo = StringField("Correo")
    submit = SubmitField("Guardar")

    def validate(self, extra_validators=None):
        rv = super().validate(extra_validators)
        if not rv:
            return False

        if self.tipo.data == "empresa":
            if not self.nit.data:
                self.nit.errors.append("Este campo es obligatorio para empresas.")
                return False
            try:
                validar_nit_con_dv(self, self.nit)
            except ValidationError as e:
                self.nit.errors.append(str(e))
                return False

        elif self.tipo.data == "natural":
            if not self.cc.data or not self.cc.data.strip().isdigit():
                self.cc.errors.append("Ingrese una cedula valida (solo numeros).")
                return False

        return True