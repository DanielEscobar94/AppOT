from flask import Blueprint, render_template, redirect, url_for, request, flash, Response, send_file, jsonify
from extensions import db
from models.models import Product
from forms.products_form import ProductForm
from sqlalchemy import or_
import csv
import openpyxl
from openpyxl.styles import Font
from io import StringIO, BytesIO
from flask_login import login_required
from utils.decorators import role_required

products_bp = Blueprint("products", __name__, url_prefix="/products")

@products_bp.route("/")
@login_required
@role_required('admin', 'supervisor')
def listar():
    page = request.args.get("page", 1, type=int)
    query = request.args.get("q", "", type=str)

    productos_query = Product.query

    if query:
        # Si el query coincide exactamente con un SKU, mostrar solo ese producto
        producto_exacto = Product.query.filter_by(sku=query.strip()).first()
        if producto_exacto:
            productos_query = Product.query.filter_by(sku=query.strip())
        else:
            palabras = query.strip().split()
            for kw in palabras:
                productos_query = productos_query.filter(
                    or_(
                        Product.nombre.ilike(f"%{kw}%"),
                        Product.sku.ilike(f"%{kw}%")
                    )
                )

    productos = productos_query.order_by(Product.sku.asc()).paginate(page=page, per_page=10)

    return render_template(
        "products/listar.html",
        productos=productos,
        query=query
    )

@products_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required('admin', 'supervisor')
def nuevo():
    form = ProductForm()

    if form.validate_on_submit():
        sku = form.sku.data.strip()
        if Product.query.filter_by(sku=sku).first():
            flash(f"Ya existe un producto con el SKU {sku}", "danger")
            return redirect(url_for("products.nuevo"))

        # Leer precio directamente del request para evitar problemas con FloatField
        precio_raw = request.form.get('precio', '0').strip()
        # Limpiar puntos de separador de miles
        precio_limpio = precio_raw.replace('.', '').replace(',', '')
        producto = Product(
            sku=sku,
            nombre=form.nombre.data.strip().upper(),
            precio=float(precio_limpio) if precio_limpio else 0.0
        )

        try:
            db.session.add(producto)
            db.session.commit()
            flash("Producto creado correctamente", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al guardar el producto: {e}", "danger")

        return redirect(url_for("products.listar"))

    return render_template("products/nuevo.html", form=form)

@products_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
@role_required('admin', 'supervisor')
def editar(id):
    producto = Product.query.get_or_404(id)
    form = ProductForm(obj=producto)

    if form.validate_on_submit():
        sku = form.sku.data.strip()
        existe = Product.query.filter_by(sku=sku).first()
        if existe and existe.id != producto.id:
            flash(f"El SKU {sku} ya esta en uso", "danger")
            return redirect(url_for("products.editar", id=id))

        producto.nombre = form.nombre.data.strip().upper()
        producto.sku = sku
        # Leer precio directamente del request para evitar problemas con FloatField
        precio_raw = request.form.get('precio', '0').strip()
        # Limpiar puntos de separador de miles
        precio_limpio = precio_raw.replace('.', '').replace(',', '')
        producto.precio = float(precio_limpio) if precio_limpio else 0.0

        try:
            db.session.commit()
            flash("Producto actualizado correctamente", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al actualizar el producto: {e}", "danger")

        return redirect(url_for("products.listar"))

    return render_template("products/nuevo.html", form=form, producto=producto)

@products_bp.route("/eliminar/<int:id>", methods=["POST"])
@login_required
@role_required('admin', 'supervisor')
def eliminar(id):
    producto = Product.query.get_or_404(id)
    try:
        db.session.delete(producto)
        db.session.commit()
        flash("Producto eliminado correctamente", "success")
    except Exception:
        db.session.rollback()
        flash("Error al eliminar el producto.", "danger")
    return redirect(url_for("products.listar"))

@products_bp.route("/exportar")
@login_required
@role_required('admin', 'supervisor')
def exportar():
    productos = Product.query.order_by(Product.nombre).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Nombre", "SKU", "Precio"])

    for p in productos:
        writer.writerow([
            p.id,
            p.nombre,
            p.sku,
            f"{int(round(p.precio))}"
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=productos.csv"}
    )

@products_bp.route("/exportar_excel")
@login_required
@role_required('admin', 'supervisor')
def exportar_excel():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Productos"

    encabezados = ["SKU", "Nombre", "Precio"]
    ws.append(encabezados)
    for celda in ws[1]:
        celda.font = Font(bold=True)

    productos = Product.query.order_by(Product.nombre).all()
    for p in productos:
        ws.append([
            p.sku,
            p.nombre,
            int(round(p.precio)) if p.precio else 0
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        download_name="productos.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@products_bp.route("/importar_excel", methods=["POST"])
@login_required
@role_required('admin', 'supervisor')
def importar_excel():
    import pandas as pd
    
    if 'archivo' not in request.files:
        flash('No se selecciono ningun archivo', 'danger')
        return redirect(url_for('products.listar'))
    
    archivo = request.files['archivo']
    if archivo.filename == '':
        flash('No se selecciono ningun archivo', 'danger')
        return redirect(url_for('products.listar'))
    
    if not archivo.filename.lower().endswith(('.xlsx', '.xls')):
        flash('Solo se permiten archivos Excel (.xlsx, .xls)', 'danger')
        return redirect(url_for('products.listar'))
    
    try:
        # Leer el archivo Excel
        df = pd.read_excel(archivo)

        # Limite anti-DoS: archivos gigantes agotan memoria/CPU
        MAX_IMPORT_ROWS = 5000
        if len(df) > MAX_IMPORT_ROWS:
            flash(f'El archivo supera el máximo de {MAX_IMPORT_ROWS} filas', 'danger')
            return redirect(url_for('products.listar'))
        
        # Verificar que las columnas esperadas existen
        columnas_esperadas = ['SKU', 'Nombre', 'Precio']
        columnas_faltantes = [col for col in columnas_esperadas if col not in df.columns]
        
        if columnas_faltantes:
            flash(f'Faltan las siguientes columnas en el archivo: {", ".join(columnas_faltantes)}', 'danger')
            return redirect(url_for('products.listar'))
        
        productos_creados = 0
        productos_actualizados = 0
        errores = []

        # Limits for Numeric(10,2): absolute value must be < 10**8
        MAX_ABS_PRICE = 10 ** 8 - 1

        # Process rows one by one but commit in small batches to avoid one bad row rolling back everything
        BATCH_SIZE = 50
        batch_count = 0

        for index, row in df.iterrows():
            try:
                # Validar datos obligatorios
                if pd.isna(row['Nombre']) or pd.isna(row['SKU']):
                    errores.append(f'Fila {index + 2}: Nombre y SKU son obligatorios')
                    continue

                sku = str(row['SKU']).strip()
                nombre = str(row['Nombre']).strip().upper()  # Convertir a mayusculas
                try:
                    precio = float(row['Precio']) if not pd.isna(row['Precio']) else 0.0
                except Exception:
                    precio = 0.0

                # Validate price range for Numeric(10,2)
                if abs(precio) >= 10 ** 8:
                    errores.append(f'Fila {index + 2}: Precio fuera de rango para la base de datos ({precio}). Maximo permitido absoluto: {MAX_ABS_PRICE}')
                    continue

                # Use no_autoflush when performing queries that could trigger autoflush while session has pending new objects
                with db.session.no_autoflush:
                    producto_existente = Product.query.filter_by(sku=sku).first()

                if producto_existente:
                    producto_existente.nombre = nombre
                    producto_existente.precio = precio
                    productos_actualizados += 1
                else:
                    producto = Product(
                        sku=sku,
                        nombre=nombre,
                        precio=precio
                    )
                    db.session.add(producto)
                    productos_creados += 1

                batch_count += 1
                if batch_count >= BATCH_SIZE:
                    try:
                        db.session.commit()
                    except Exception as e:
                        db.session.rollback()
                        errores.append(f'Error al guardar lote hasta fila {index + 2}: {str(e)}')
                    batch_count = 0

            except Exception as e:
                # If an unexpected error occurs per-row, rollback the session to reset state
                db.session.rollback()
                errores.append(f'Fila {index + 2}: {str(e)}')

        # Final commit for remaining items
        if batch_count > 0:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                errores.append(f'Error al guardar el ultimo lote: {str(e)}')
        
        # Mostrar resultados
        mensaje = f'Importacion completada: {productos_creados} productos creados, {productos_actualizados} actualizados'
        if errores:
            mensaje += f'. {len(errores)} errores encontrados'
            flash(mensaje, 'warning')
            for error in errores[:5]:  # Mostrar solo los primeros 5 errores
                flash(error, 'danger')
            if len(errores) > 5:
                flash(f'... y {len(errores) - 5} errores mas', 'danger')
        else:
            flash(mensaje, 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al procesar el archivo Excel: {str(e)}', 'danger')
    
    return redirect(url_for('products.listar'))

@products_bp.route("/bloquear/<int:id>", methods=["POST"])
@login_required
@role_required('admin', 'supervisor')
def bloquear(id):
    """Bloquear o desbloquear un producto (toggle)"""
    producto = Product.query.get_or_404(id)
    try:
        producto.bloqueado = not producto.bloqueado
        db.session.commit()
        estado = 'bloqueado' if producto.bloqueado else 'desbloqueado'
        flash(f'Producto "{producto.nombre}" {estado} correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cambiar estado del producto: {str(e)}', 'danger')
    return redirect(url_for('products.listar', q=request.args.get('q', ''), page=request.args.get('page', 1)))


@products_bp.route("/buscar", methods=["GET", "POST"])
@login_required
def buscar_productos():
    """Buscar productos por SKU o nombre - usado en POS y Ordenes de Trabajo"""
    # Soportar tanto GET como POST
    if request.method == "POST":
        data = request.get_json() or {}
        q = data.get("query", "").strip()
    else:
        q = request.args.get("q", "").strip()
    
    print(f"🔍 Búsqueda de productos: '{q}'")  # Debug log
    
    if not q:
        return jsonify({"productos": []})
    
    # Buscar por SKU o nombre, excluir productos bloqueados, limitar a 10 resultados
    productos = Product.query.filter(
        Product.bloqueado == False,
        or_(
            Product.sku.ilike(f"%{q}%"),
            Product.nombre.ilike(f"%{q}%")
        )
    ).limit(10).all()
    
    resultados = [p.to_dict() for p in productos]
    print(f"✅ Encontrados {len(resultados)} productos")  # Debug log
    
    return jsonify({"productos": resultados})

@products_bp.route("/buscar_sku")
@login_required
def buscar_sku():
    q = request.args.get("q", "")
    results = Product.query.filter(
        Product.bloqueado == False,
        Product.sku.ilike(f"%{q}%")
    ).all()
    return jsonify([p.to_dict() for p in results])