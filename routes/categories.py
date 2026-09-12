from flask import Blueprint, render_template, request, redirect, flash, url_for
from flask_login import login_required
from utils.decorators import role_required
from models.models import Category
from extensions import db
from forms.category_form import CategoryForm

categories_bp = Blueprint("categories", __name__, url_prefix="/categories")

@categories_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required('admin', 'supervisor')
def nuevo():
    form = CategoryForm()

    if form.validate_on_submit():
        nombre = form.nombre.data.strip()
        if Category.query.filter_by(nombre=nombre).first():
            flash("La categoria ya existe", "warning")
            return redirect(url_for("categories.nuevo"))

        categoria = Category(nombre=nombre)
        db.session.add(categoria)
        db.session.commit()
        flash("Categoria creada correctamente", "success")
        return redirect(url_for("products.listar"))

    return render_template("categories/nuevo.html", form=form)
    
@categories_bp.route("/api/nueva", methods=["POST"])
@login_required
@role_required('admin', 'supervisor')
def crear_ajax():
    data = request.get_json()
    nombre = data.get("nombre", "").strip()
    
    if not nombre:
        return {"error": "Nombre requerido"}, 400
    if len(nombre) < 2 or len(nombre) > 50:
        return {"error": "El nombre debe tener entre 2 y 50 caracteres"}, 400
    if Category.query.filter_by(nombre=nombre).first():
        return {"error": "La categoria ya existe"}, 409

    nueva = Category(nombre=nombre)
    db.session.add(nueva)
    db.session.commit()
    return {"id": nueva.id, "nombre": nueva.nombre}

