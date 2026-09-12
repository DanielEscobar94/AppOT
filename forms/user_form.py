from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional


class UserForm(FlaskForm):
    username = StringField("Nombre de usuario", validators=[
        DataRequired(), Length(max=64)
    ])
    email = StringField("Correo electronico", validators=[
        DataRequired(), Email(), Length(max=120)
    ])
    password = PasswordField("Contrasena", validators=[
        DataRequired(), Length(min=6)
    ])
    rol = SelectField("Rol", choices=[
        ("admin", "Administrador"),
        ("vendedor", "Vendedor"),
        ("supervisor", "Supervisor"),
        ("tecnico", "Tecnico")
    ])
    branch_id = SelectField("Sucursal", coerce=int, validators=[Optional()])


class DeleteForm(FlaskForm):
    """Minimal form used only to provide csrf_token for delete actions."""
    pass


class EditUserForm(UserForm):
    """Form used for editing a user: password is optional (leave blank to keep current)."""
    # Override password validators to make it optional on edit
    password = PasswordField("Contrasena", validators=[Optional(), Length(min=6)])
