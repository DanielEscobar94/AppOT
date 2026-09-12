from flask import Blueprint, render_template, redirect, url_for, request, flash, Response, send_file, jsonify, make_response, current_app
from extensions import db
from models.models import Client
from forms.clients_form import ClientForm
from sqlalchemy import or_
import csv
import openpyxl
from openpyxl.styles import Font
from io import StringIO, BytesIO
from routes.products import products_bp
from flask_login import login_required
from utils.decorators import role_required

clients_bp = Blueprint("clients", __name__, url_prefix="/clients")

@clients_bp.route('/crear_desde_modal', methods=['POST'])
@login_required
@role_required('admin', 'vendedor', 'supervisor', 'tecnico')
def crear_desde_modal():
    # Permitir CORS para peticiones AJAX
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Requested-With'
        return response

    # Debug: log incoming form for troubleshooting
    try:
        print('[DEBUG crear_desde_modal] headers:', dict(request.headers))
        print('[DEBUG crear_desde_modal] form:', dict(request.form))
    except Exception:
        pass

    tipo = request.form.get('tipo', '').strip()
    nombre = request.form.get('nombre', '').strip().upper()  # Convertir a mayusculas
    cc = request.form.get('cc', '').strip()
    nit = request.form.get('nit', '').strip()
    correo = request.form.get('correo', '').strip()
    telefono = request.form.get('telefono', '').strip()
    
    # Convertir cadenas vacias a None para evitar problemas de unique constraint
    correo = correo if correo else None
    telefono = telefono if telefono else None
    
    error = None
    cliente = None
    # Validacion basica requerida por base de datos
    if not nombre:
        error = 'El nombre es obligatorio.'
    if not error:
        if tipo == 'natural':
            if not cc:
                error = 'La cedula es obligatoria.'
            elif Client.query.filter_by(cc=cc).first():
                error = f'Ya existe un cliente con la identificacion {cc}'
            else:
                cliente = Client(nombre=nombre, cc=cc, correo=correo, telefono=telefono)
        elif tipo == 'empresa':
            if not nit:
                error = 'El NIT es obligatorio.'
            elif Client.query.filter_by(nit=nit).first():
                error = f'Ya existe un cliente con el NIT {nit}'
            else:
                cliente = Client(nombre=nombre, nit=nit, correo=correo, telefono=telefono)
        else:
            error = 'Tipo de cliente no valido.'
    if error:
        response = jsonify(success=False, error=error)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response, 400
    try:
        db.session.add(cliente)
        db.session.commit()
        try:
            print(f"[DEBUG crear_desde_modal] creado OK id={cliente.id}, nombre={cliente.nombre}")
        except Exception:
            pass
        
        cliente_data = {
            "id": cliente.id,
            "nombre": cliente.nombre,
            "correo": cliente.correo,
            "telefono": cliente.telefono,
            "cc": cliente.cc,
            "nit": cliente.nit,
            "label": cliente.nombre 
        }
        
        try:
            print(f"[DEBUG crear_desde_modal] Enviando respuesta: {cliente_data}")
        except Exception:
            pass
        
        response = jsonify(success=True, cliente=cliente_data)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        db.session.rollback()
        try:
            import traceback
            print('[DEBUG crear_desde_modal] EXCEPTION while saving client:')
            traceback.print_exc()
        except Exception:
            pass
        # Mensaje amigable para errores de integridad
        msg = str(e)
        if 'UNIQUE constraint failed' in msg:
            if 'clients.correo' in msg:
                error_msg = 'Ya existe un cliente con ese correo.'
            elif 'clients.cc' in msg:
                error_msg = 'Ya existe un cliente con esa cedula.'
            elif 'clients.nit' in msg:
                error_msg = 'Ya existe un cliente con ese NIT.'
            else:
                error_msg = 'Ya existe un cliente con datos duplicados.'
        else:
            error_msg = 'Error al guardar el cliente.'
    response = jsonify(success=False, error=error_msg)
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response, 400

@clients_bp.route('/')
@login_required
@role_required('admin', 'vendedor', 'supervisor', 'tecnico')
def listar():
    query = request.args.get("q", type=str)
    selected_id = request.args.get('selected_id', type=int)
    page = request.args.get("page", 1, type=int)
    per_page = 10
    clientes_query = Client.query

    if selected_id:
        clientes_query = clientes_query.filter(Client.id == selected_id)
    elif query:
        palabras = query.strip().split()
        filtros = []
        for kw in palabras:
            filtros.extend([
                Client.nombre.ilike(f"%{kw}%"),
                Client.cc.ilike(f"%{kw}%"),
                Client.nit.ilike(f"%{kw}%"),
                Client.correo.ilike(f"%{kw}%")
            ])
        clientes_query = clientes_query.filter(or_(*filtros))

    clientes_pagination = clientes_query.order_by(Client.nombre).paginate(page=page, per_page=per_page, error_out=False)
    clientes = clientes_pagination.items

    clientes_dict = [{
        'id': c.id,
        'nombre': c.nombre,
        'cc': c.cc,
        'nit': c.nit,
        'correo': c.correo,
        'telefono': c.telefono
    } for c in clientes]
    # Construir una lista amigable de páginas para mostrar en la UI
    def _build_page_links(current, total, left=2, right=2):
        # current: current page number (1-based)
        # total: total pages
        if total <= 1:
            return [1] if total == 1 else []
        pages = []
        # siempre mostrar la primera página
        if current - left > 2:
            pages.extend([1, '...'])
            start = current - left
        else:
            start = 1

        end = current + right
        if end < total - 1:
            tail = ['...', total]
        else:
            end = total
            tail = []

        for p in range(start, end + 1):
            if p not in pages:
                pages.append(p)

        pages.extend(tail)
        # ensure unique and ordered
        seen = set()
        ordered = []
        for x in pages:
            if x not in seen:
                ordered.append(x)
                seen.add(x)
        return ordered

    # Allow configuration for default page size
    per_page = current_app.config.get('CLIENTS_PER_PAGE', per_page)
    # Re-run paginate if per_page changed from default (rare)
    if clientes_pagination.per_page != per_page:
        clientes_pagination = clientes_query.order_by(Client.nombre).paginate(page=page, per_page=per_page, error_out=False)
        clientes = clientes_pagination.items

    page_links = _build_page_links(clientes_pagination.page, clientes_pagination.pages, left=2, right=2)
    # Quick sliding window for fast-access page links (visible row 1..N window)
    def _sliding_window(current, total, window=10):
        # Return a list of page numbers (ints) representing the sliding window
        if total <= 0:
            return []
        if total <= window:
            return list(range(1, total + 1))
        # bias edges: when near start, show 1..window; when near end, show last window
        left_bias = int(window * 0.6)
        right_bias = window - left_bias
        # If current is in the left zone
        if current <= left_bias:
            start = 1
            end = window
        # If current in right zone
        elif current > total - right_bias:
            start = total - window + 1
            end = total
        else:
            # centered window
            half = window // 2
            start = max(1, current - half)
            end = start + window - 1
            if end > total:
                end = total
                start = max(1, end - window + 1)
        return list(range(start, end + 1))

    quick_page_links = _sliding_window(clientes_pagination.page, clientes_pagination.pages, window=current_app.config.get('CLIENTS_QUICK_WINDOW', 10))

    return render_template(
        'clients/listar.html',
        clientes=clientes,
        clientes_json=clientes_dict,
        query=query,
        pagination=clientes_pagination,
        page_links=page_links,
        quick_page_links=quick_page_links
    )

@clients_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'vendedor', 'supervisor', 'tecnico')
def nuevo():
    form = ClientForm()

    if request.method == 'POST':
        tipo = request.form.get('tipo')
        cc = request.form.get('cc', '').strip()
        nit = request.form.get('nit', '').strip()
        form.tipo.data = tipo
        form.cc.data = cc
        form.nit.data = nit

    if form.validate_on_submit():
        tipo = form.tipo.data
        correo = form.correo.data.strip() if form.correo.data else ""
        telefono = form.telefono.data.strip() if form.telefono.data else ""
        nombre = form.nombre.data.strip()

        if tipo == "natural" and not form.cc.data:
            error = "La cédula es obligatoria para personas naturales"
        elif tipo == "empresa" and not form.nit.data:
            error = "El NIT es obligatorio para empresas"
        else:
            error = None

        if error:
            flash(error, "danger")
            return render_template('clients/nuevo.html', form=form)

        correo = correo if correo else None
        telefono = telefono if telefono else None
        nombre = nombre.upper()

        cliente = None
        if tipo == "natural":
            if Client.query.filter_by(cc=form.cc.data).first():
                flash(f"Ya existe un cliente con la identificacion {form.cc.data}", "danger")
                return render_template('clients/nuevo.html', form=form)
            else:
                cliente = Client(nombre=nombre, cc=form.cc.data, correo=correo, telefono=telefono)
        elif tipo == "empresa":
            if Client.query.filter_by(nit=form.nit.data).first():
                flash(f"Ya existe un cliente con el NIT {form.nit.data}", "danger")
                return render_template('clients/nuevo.html', form=form)
            else:
                cliente = Client(nombre=nombre, nit=form.nit.data, correo=correo, telefono=telefono)
        else:
            flash("Tipo de cliente no valido", "danger")
            return render_template('clients/nuevo.html', form=form)

        try:
            db.session.add(cliente)
            db.session.commit()
            flash("Cliente creado correctamente", "success")
            return redirect(url_for('clients.listar'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error al guardar el cliente: {e}", "danger")
            return render_template('clients/nuevo.html', form=form)

    return render_template('clients/nuevo.html', form=form)

@clients_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'vendedor', 'supervisor', 'tecnico')
def editar(id):
    cliente = Client.query.get_or_404(id)
    form = ClientForm(obj=cliente)

    # DEBUG: log incoming POST for troubleshooting why update may not apply
    if request.method == 'POST':
        try:
            print('[DEBUG clients.editar] POST received for client id=', id)
            print('[DEBUG clients.editar] request.form keys:', dict(request.form))
        except Exception:
            pass

    if form.validate_on_submit():
        tipo = request.form.get("tipo")
        correo = form.correo.data.strip() if form.correo.data else ""
        telefono = form.telefono.data.strip() if form.telefono.data else ""
        
        # Convertir nombre a mayusculas
        cliente.nombre = form.nombre.data.strip().upper()
        cliente.correo = correo if correo else None  # Convertir cadena vacia a None
        cliente.telefono = telefono if telefono else None  # Convertir cadena vacia a None

        if tipo == "natural":
            cc = request.form.get("cc", "").strip()
            if not cc:
                flash("La cedula es obligatoria para persona natural", "danger")
                return render_template("clients/editar.html", form=form, cliente=cliente)
            existe = Client.query.filter_by(cc=cc).first()
            if existe and existe.id != cliente.id:
                flash(f"La cedula {cc} ya esta en uso", "danger")
                return render_template("clients/editar.html", form=form, cliente=cliente)
            cliente.cc = cc
            cliente.nit = None

        elif tipo == "empresa":
            nit = request.form.get("nit", "").strip()
            if not nit:
                flash("El NIT es obligatorio para empresa", "danger")
                return render_template("clients/editar.html", form=form, cliente=cliente)
            existe = Client.query.filter_by(nit=nit).first()
            if existe and existe.id != cliente.id:
                flash(f"El NIT {nit} ya esta en uso", "danger")
                return render_template("clients/editar.html", form=form, cliente=cliente)
            cliente.nit = nit
            cliente.cc = None

        else:
            flash("Tipo de cliente invalido", "danger")
            return render_template("clients/editar.html", form=form, cliente=cliente)

        try:
            db.session.commit()
            flash("Cliente actualizado correctamente", "success")
            return redirect(url_for("clients.listar"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error al actualizar el cliente: {e}", "danger")
            print(f"Error tecnico al actualizar: {e}")
            return render_template("clients/editar.html", form=form, cliente=cliente)
    else:
        # If POST but validation failed, log errors to help debugging
        if request.method == 'POST':
            try:
                print('[DEBUG clients.editar] form.validate_on_submit() returned False')
                print('[DEBUG clients.editar] form.errors =', form.errors)
            except Exception:
                pass

    return render_template('clients/editar.html', form=form, cliente=cliente)

@clients_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@role_required('admin', 'supervisor')
def eliminar(id):
    cliente = Client.query.get_or_404(id)
    try:
        db.session.delete(cliente)
        db.session.commit()
        flash("Cliente eliminado correctamente", "success")
    except Exception:
        db.session.rollback()
        flash("Error al eliminar el cliente.", "danger")
    return redirect(url_for('clients.listar'))

@clients_bp.route('/exportar')
@login_required
@role_required('admin', 'supervisor')
def exportar():
    clientes = Client.query.order_by(Client.nombre).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Nombre', 'Tipo', 'Identificacion', 'Correo', 'Telefono'])

    for c in clientes:
        tipo = "Empresa" if c.nit else "Persona Natural"
        documento = c.nit or c.cc or ""
        writer.writerow([c.nombre, tipo, documento, c.correo, c.telefono])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=clientes.csv'}
    )

@clients_bp.route('/exportar_excel')
@login_required
@role_required('admin', 'supervisor')
def exportar_excel():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clientes"
    encabezados = ['Nombre', 'Tipo', 'Identificacion', 'Correo', 'Telefono']
    ws.append(encabezados)
    for celda in ws[1]:
        celda.font = Font(bold=True)

    clientes = Client.query.order_by(Client.nombre).all()
    for cliente in clientes:
        tipo = "Empresa" if cliente.nit else "Persona Natural"
        identificacion = cliente.nit or cliente.cc or ""
        ws.append([
            cliente.nombre,
            tipo,
            identificacion,
            cliente.correo,
            cliente.telefono
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        download_name="clientes.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@clients_bp.route('/buscar')
@login_required
@role_required('admin', 'vendedor', 'supervisor', 'tecnico')
def buscar():
    q = request.args.get("q", "", type=str)
    if not q:
        return jsonify([])

    clientes = Client.query.filter(
        or_(
            Client.nombre.ilike(f"%{q}%"),
            Client.cc.ilike(f"%{q}%"),
            Client.nit.ilike(f"%{q}%")
        )
    ).limit(10).all()

    resultados = []
    for c in clientes:
        identificacion = c.cc or c.nit or "—"
        resultados.append({
            "id": c.id,
            "nombre": c.nombre or "",
            "label": f"{c.nombre} ({identificacion})",
            "documento": identificacion,  # Agregar campo documento para compatibilidad
            "correo": c.correo or "",
            "telefono": c.telefono or ""
        })

    return jsonify(resultados)


@clients_bp.route('/api/cliente/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'vendedor', 'supervisor', 'tecnico')
def api_cliente(id):
    """API JSON para obtener/actualizar un cliente.
    GET: devuelve datos del cliente.
    POST: recibe JSON con campos para actualizar y devuelve el cliente actualizado.
    """
    cliente = Client.query.get_or_404(id)
    if request.method == 'GET':
        return jsonify({
            'id': cliente.id,
            'nombre': cliente.nombre,
            'correo': cliente.correo,
            'telefono': cliente.telefono,
            'cc': cliente.cc,
            'nit': cliente.nit,
            'cedula': cliente.cc or cliente.nit  # Agregar campo cedula para compatibilidad
        })

    # POST -> actualizar
    data = {}
    try:
        if request.is_json:
            data = request.get_json()
        else:
            # fallback a form data
            data = request.form.to_dict()
    except Exception:
        return jsonify({'success': False, 'error': 'Payload invalido'}), 400

    nombre = (data.get('nombre') or '').strip()
    correo = (data.get('correo') or '').strip() or None
    telefono = (data.get('telefono') or '').strip() or None
    tipo = data.get('tipo')
    cc = (data.get('cc') or '').strip() or None
    nit = (data.get('nit') or '').strip() or None

    if not nombre:
        return jsonify({'success': False, 'error': 'El nombre es obligatorio.'}), 400

    # Convertir nombre a mayusculas
    nombre_u = nombre.upper()

    # Validaciones de unicidad para CC/NIT y correo
    try:
        if cc:
            existe = Client.query.filter(Client.cc == cc, Client.id != cliente.id).first()
            if existe:
                return jsonify({'success': False, 'error': f'La cedula {cc} ya esta en uso por otro cliente.'}), 400
        if nit:
            existe2 = Client.query.filter(Client.nit == nit, Client.id != cliente.id).first()
            if existe2:
                return jsonify({'success': False, 'error': f'El NIT {nit} ya esta en uso por otro cliente.'}), 400
        if correo:
            existe3 = Client.query.filter(Client.correo == correo, Client.id != cliente.id).first()
            if existe3:
                return jsonify({'success': False, 'error': f'El correo {correo} ya esta en uso por otro cliente.'}), 400
    except Exception:
        # continuar y dejar que la DB valide si algo falla
        pass

    # Aplicar cambios
    cliente.nombre = nombre_u
    cliente.correo = correo
    cliente.telefono = telefono
    # Asignar CC/NIT acorde al tipo si fue proporcionado
    if tipo == 'natural':
        cliente.cc = cc
        cliente.nit = None
    elif tipo == 'empresa':
        cliente.nit = nit
        cliente.cc = None
    else:
        # Si no se especifica tipo, respetar campos enviados
        if cc is not None:
            cliente.cc = cc
        if nit is not None:
            cliente.nit = nit

    try:
        db.session.commit()
        return jsonify({'success': True, 'cliente': {
            'id': cliente.id,
            'nombre': cliente.nombre,
            'correo': cliente.correo,
            'telefono': cliente.telefono,
            'cc': cliente.cc,
            'nit': cliente.nit,
            'cedula': cliente.cc or cliente.nit  # Agregar campo cedula para compatibilidad
        }})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@clients_bp.route('/importar_excel', methods=['POST'])
@login_required
@role_required('admin', 'supervisor')
def importar_excel():
    archivo = request.files.get('archivo')
    if not archivo:
        flash("No se recibio archivo", "danger")
        return redirect(url_for("clients.listar"))

    # Validar extension del archivo
    if not archivo.filename.lower().endswith(('.xlsx', '.xls')):
        flash("Solo se permiten archivos Excel (.xlsx, .xls)", "danger")
        return redirect(url_for("clients.listar"))

    try:
        wb = openpyxl.load_workbook(archivo)
        sheet = wb.active
        
        # Verificar que el archivo tenga al menos una fila (encabezado)
        if sheet.max_row < 2:
            flash("El archivo esta vacio o solo tiene encabezados", "warning")
            return redirect(url_for("clients.listar"))

        # Limite anti-DoS: archivos gigantes agotan memoria/CPU
        MAX_IMPORT_ROWS = 5000
        if sheet.max_row > MAX_IMPORT_ROWS + 1:
            flash(f"El archivo supera el máximo de {MAX_IMPORT_ROWS} filas", "danger")
            return redirect(url_for("clients.listar"))

        clientes_creados = 0
        clientes_saltados = 0
        errores = []

        print(f"[DEBUG] Procesando archivo Excel con {sheet.max_row} filas y {sheet.max_column} columnas")
        
        # Mostrar los encabezados para debug
        encabezados = [cell.value for cell in sheet[1]]
        print(f"[DEBUG] Encabezados encontrados: {encabezados}")

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            try:
                # Manejar filas con diferentes longitudes
                valores = list(row) + [None] * (5 - len(row))  # Asegurar al menos 5 valores
                nombre, tipo, identificacion, correo, telefono = valores[0], valores[1], valores[2], valores[3], valores[4]
                
                print(f"[DEBUG] Fila {row_idx}: {valores}")

                # Validar campos obligatorios
                if not nombre or not identificacion:
                    errores.append(f"Fila {row_idx}: Nombre e identificacion son obligatorios")
                    continue

                # Limpiar y validar datos
                nombre = str(nombre).strip().upper()  # Convertir a mayusculas
                tipo = str(tipo).strip() if tipo else ""
                identificacion = str(identificacion).strip()
                correo = str(correo).strip() if correo and str(correo).strip() else None
                telefono = str(telefono).strip() if telefono and str(telefono).strip() else None

                # Validar longitudes segun el modelo de base de datos
                if len(nombre) > 120:
                    errores.append(f"Fila {row_idx}: Nombre demasiado largo (maximo 120 caracteres)")
                    continue
                
                if len(identificacion) > 12:
                    errores.append(f"Fila {row_idx}: Identificacion demasiado larga (maximo 12 caracteres)")
                    continue
                
                if correo and len(correo) > 120:
                    errores.append(f"Fila {row_idx}: Correo demasiado largo (maximo 120 caracteres)")
                    continue
                
                if telefono and len(telefono) > 20:
                    errores.append(f"Fila {row_idx}: Telefono demasiado largo (maximo 20 caracteres)")
                    continue

                # Determinar automaticamente si es CC o NIT basado en longitud y tipo
                cc_value = None
                nit_value = None
                
                if tipo.lower() in ["persona natural", "natural"]:
                    if len(identificacion) <= 12:
                        cc_value = identificacion
                    else:
                        errores.append(f"Fila {row_idx}: Cedula muy larga para persona natural (maximo 12 digitos)")
                        continue
                elif tipo.lower() in ["empresa", "juridica", "juridica"]:
                    if len(identificacion) <= 11:
                        nit_value = identificacion
                    else:
                        errores.append(f"Fila {row_idx}: NIT muy largo para empresa (maximo 11 digitos)")
                        continue
                else:
                    # Si el tipo no esta claro, determinar por longitud
                    if len(identificacion) <= 12:
                        cc_value = identificacion
                    elif len(identificacion) <= 11:
                        nit_value = identificacion
                    else:
                        errores.append(f"Fila {row_idx}: Identificacion muy larga (maximo 12 digitos para CC, 11 para NIT)")
                        continue

                # Verificar si ya existe (por CC, NIT o correo)
                filtros_duplicado = []
                
                if cc_value:
                    filtros_duplicado.append(Client.cc == cc_value)
                if nit_value:
                    filtros_duplicado.append(Client.nit == nit_value)
                if correo and correo.strip():
                    filtros_duplicado.append(Client.correo == correo)
                
                if filtros_duplicado:
                    existe = Client.query.filter(or_(*filtros_duplicado)).first()
                    if existe:
                        clientes_saltados += 1
                        print(f"[DEBUG] Cliente ya existe: {nombre} - {identificacion}")
                        continue

                # Crear nuevo cliente con session.no_autoflush para evitar flush prematuro
                with db.session.no_autoflush:
                    nuevo = Client(
                        nombre=nombre,
                        cc=cc_value,
                        nit=nit_value,
                        correo=correo,
                        telefono=telefono
                    )
                    db.session.add(nuevo)
                    clientes_creados += 1
                    print(f"[DEBUG] Cliente creado: {nombre}")

            except Exception as e:
                # Rollback para limpiar el estado de la sesion
                db.session.rollback()
                errores.append(f"Fila {row_idx}: Error al procesar - {str(e)}")
                print(f"[ERROR] Fila {row_idx}: {str(e)}")

        # Commit final
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Error al guardar los cambios: {e}", "danger")
            return redirect(url_for("clients.listar"))
        
        # Mensaje de resultado
        mensaje = f"Importacion completada: {clientes_creados} clientes creados"
        if clientes_saltados > 0:
            mensaje += f", {clientes_saltados} ya existian"
        if errores:
            mensaje += f", {len(errores)} errores"
            
        tipo_flash = "success" if clientes_creados > 0 else "warning"
        flash(mensaje, tipo_flash)
        
        # Mostrar errores especificos si los hay
        if errores:
            for error in errores[:5]:  # Mostrar solo los primeros 5 errores
                flash(error, "danger")
            if len(errores) > 5:
                flash(f"... y {len(errores) - 5} errores mas", "danger")

    except Exception as e:
        db.session.rollback()
        flash(f"Error al procesar el archivo: {e}", "danger")
        print(f"Error tecnico al importar: {e}")

    return redirect(url_for("clients.listar"))


@clients_bp.route('/nuevo', methods=['POST'])
@login_required
@role_required('admin', 'vendedor', 'supervisor', 'tecnico')
def nuevo_modal():
    nombre = request.form.get('nombre', '').strip()
    correo = request.form.get('correo', '').strip()
    telefono = request.form.get('telefono', '').strip()
    
    # Convertir cadenas vacias a None
    correo = correo if correo else None
    telefono = telefono if telefono else None
    
    if not nombre:
        flash('El nombre es obligatorio', 'danger')
        return redirect(url_for('sales.nueva'))
    cliente = Client(nombre=nombre, correo=correo, telefono=telefono)
    try:
        db.session.add(cliente)
        db.session.commit()
        flash('Cliente creado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar el cliente: {e}', 'danger')
    return redirect(url_for('sales.nueva'))

orden_id = db.Column(db.Integer, db.ForeignKey('orden.id'))

@clients_bp.route('/search', methods=['GET'])
@login_required
def search():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'clients': []})
    
    # Buscar por nombre, cc, nit o telefono
    clients = Client.query.filter(
        or_(
            Client.nombre.ilike(f'%{q}%'),
            Client.cc.ilike(f'%{q}%'),
            Client.nit.ilike(f'%{q}%'),
            Client.telefono.ilike(f'%{q}%')
        )
    ).limit(10).all()
    
    result = []
    for client in clients:
        # Usar cc o nit como documento, preferir cc si existe
        documento = client.cc if client.cc else client.nit
        result.append({
            'id': client.id,
            'nombre': client.nombre,
            'documento': documento,
            'telefono': client.telefono
        })
    
    return jsonify({'clients': result})






