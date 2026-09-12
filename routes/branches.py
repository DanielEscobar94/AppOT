from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required
from utils.decorators import role_required
from extensions import db
from models.models import Branch
from forms.branch_form import BranchForm

branches_bp = Blueprint("branches", __name__, url_prefix="/branches")

@branches_bp.route("/listar")
@login_required
@role_required('admin', 'supervisor')
def listar():
    sucursales = Branch.query.order_by(Branch.nombre.asc()).all()
    return render_template("branches/listar.html", sucursales=sucursales)

@branches_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required('admin', 'supervisor')
def nuevo():
    form = BranchForm()
    if form.validate_on_submit():
        nombre = form.nombre.data.strip()
        
        # Verificar si ya existe una sucursal con ese nombre
        existing_branch = Branch.query.filter_by(nombre=nombre).first()
        if existing_branch:
            flash(f"Ya existe una sucursal con el nombre '{nombre}'", "danger")
            return render_template("branches/nuevo.html", form=form)
        
        sucursal = Branch(
            nombre=nombre,
            direccion=form.direccion.data.strip(),
            ciudad=form.ciudad.data.strip(),
            estado=form.estado.data.strip(),
            activo=form.activo.data
        )
        try:
            db.session.add(sucursal)
            db.session.commit()
            flash("Sucursal creada correctamente", "success")
            return redirect(url_for("branches.listar"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error al guardar: {e}", "danger")
    return render_template("branches/nuevo.html", form=form)

@branches_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
@role_required('admin', 'supervisor')
def editar(id):
    sucursal = Branch.query.get_or_404(id)
    form = BranchForm(obj=sucursal)
    if form.validate_on_submit():
        nombre = form.nombre.data.strip()
        
        # Verificar si ya existe otra sucursal con ese nombre (excluyendo la actual)
        existing_branch = Branch.query.filter(Branch.nombre == nombre, Branch.id != id).first()
        if existing_branch:
            flash(f"Ya existe otra sucursal con el nombre '{nombre}'", "danger")
            return render_template("branches/nuevo.html", form=form, sucursal=sucursal)
        
        sucursal.nombre = nombre
        sucursal.direccion = form.direccion.data.strip()
        sucursal.ciudad = form.ciudad.data.strip()
        sucursal.estado = form.estado.data.strip()
        sucursal.activo = form.activo.data
        try:
            db.session.commit()
            flash("Sucursal actualizada", "success")
            return redirect(url_for("branches.listar"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error al actualizar: {e}", "danger")
    return render_template("branches/nuevo.html", form=form, sucursal=sucursal)

@branches_bp.route("/eliminar/<int:id>", methods=["POST"])
@login_required
@role_required('admin', 'supervisor')
def eliminar(id):
    sucursal = Branch.query.get_or_404(id)
    try:
        db.session.delete(sucursal)
        db.session.commit()
        flash("Sucursal eliminada", "success")
    except Exception:
        db.session.rollback()
        flash("Error al eliminar la sucursal", "danger")
    return redirect(url_for("branches.listar"))