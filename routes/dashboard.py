from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from utils.decorators import role_required
from models.models import User, Branch, Venta, Client, Product, OrdenTrabajo, Notification
from extensions import db
from forms.logo_form import LogoForm
from forms.pos_form import PosFormatForm
from forms.company_form import CompanyForm
from sqlalchemy import desc
from sqlalchemy import func
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from utils.timezone_utils import get_local_now
import os

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

@dashboard_bp.route('/company', methods=['GET', 'POST'], endpoint='company')
@login_required
@role_required('admin')
def company():
    import json
    config_path = os.path.join(os.getcwd(), 'instance', 'company.json')
    form = CompanyForm()
    company_data = {'name': '', 'address': '', 'phone': ''}
    # Load existing data
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                company_data = json.load(f)
        except Exception:
            pass
    if request.method == 'GET':
        form.name.data = company_data.get('name', '')
        form.address.data = company_data.get('address', '')
        form.phone.data = company_data.get('phone', '')
    if form.validate_on_submit():
        company_data = {
            'name': form.name.data,
            'address': form.address.data,
            'phone': form.phone.data
        }
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(company_data, f, ensure_ascii=False, indent=2)
            flash('Datos de la empresa guardados correctamente', 'success')
            return redirect(url_for('dashboard.index'))
        except Exception as e:
            flash(f'No se pudo guardar: {e}', 'danger')
    return render_template('dashboard/company.html', form=form)

@dashboard_bp.route("/")
@login_required
@role_required('admin', 'supervisor', 'tecnico', 'vendedor')
def index():
    # Si el usuario es vendedor, renderizamos un dashboard mas simple y personalizado
    if getattr(request, 'user', None) is None:
        # algunos contextos no exponen request.user; usar current_user desde flask_login
        from flask_login import current_user
        user = current_user
    else:
        user = request.user
    try:
        from flask_login import current_user
        user = current_user
    except Exception:
        pass
    # default fallbacks to avoid UnboundLocalError in unexpected control flows
    ventas_mias = 0
    ventas_sucursal = 0
    ordenes_mias = 0
    ordenes_sucursal = 0
    notifs_unread = 0
    ultimas_notifs = []
    ventas_monto_dia = 0

    ventas_mes_actual = []
    ordenes_finalizadas = 0
    ordenes_pendientes = 0
    ordenes_en_proceso = 0
    if user and getattr(user, 'rol', None) == 'vendedor':
        # Para vendedores, calcular órdenes finalizadas sin facturar por sucursal
        query_finalizadas = OrdenTrabajo.query.filter(
            OrdenTrabajo.branch_id == user.branch_id,
            OrdenTrabajo.estado == 'finalizado'
        )
        # Exclude orders that already have a linked Venta (facturadas)
        try:
            from models.models import Venta as _Venta
            query_finalizadas = query_finalizadas.outerjoin(_Venta, _Venta.orden_id == OrdenTrabajo.id).filter(_Venta.orden_id == None)
        except Exception:
            pass
        ordenes_finalizadas = query_finalizadas.count() if user.branch_id else 0
    elif user:
        # Para otros roles (como admin), calcular órdenes finalizadas sin facturar por técnico
        query_finalizadas = OrdenTrabajo.query.filter(
            OrdenTrabajo.tecnico_id == user.id,
            OrdenTrabajo.estado == 'finalizado'
        )
        # Exclude orders that already have a linked Venta (facturadas)
        try:
            from models.models import Venta as _Venta
            query_finalizadas = query_finalizadas.outerjoin(_Venta, _Venta.orden_id == OrdenTrabajo.id).filter(_Venta.orden_id == None)
        except Exception:
            pass
        ordenes_finalizadas = query_finalizadas.count()
    if user and getattr(user, 'rol', None) == 'vendedor':
        # Estadisticas enfocadas al vendedor
        ventas_mias = Venta.query.filter(Venta.usuario_id == user.id).count()
        ventas_sucursal = Venta.query.filter(Venta.branch_id == user.branch_id).count() if user.branch_id else 0
        # Total acumulado de ventas del dia (por vendedor)
        try:
            now = get_local_now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow_start = today_start + timedelta(days=1)
            ventas_monto_dia_q = db.session.query(func.coalesce(func.sum(Venta.total), 0)).filter(
                Venta.usuario_id == user.id,
                Venta.fecha >= today_start,
                Venta.fecha < tomorrow_start
            ).scalar()
            ventas_monto_dia = int(round(float(ventas_monto_dia_q or 0)))
        except Exception:
            ventas_monto_dia = 0
        ordenes_mias = OrdenTrabajo.query.filter(OrdenTrabajo.tecnico_id == user.id).count()
        ordenes_sucursal = OrdenTrabajo.query.filter(OrdenTrabajo.branch_id == user.branch_id).count() if user.branch_id else 0
        # Órdenes pendientes (no finalizadas) en la sucursal
        ordenes_pendientes = OrdenTrabajo.query.filter(
            OrdenTrabajo.branch_id == user.branch_id,
            OrdenTrabajo.estado.in_(['pendiente', 'en_proceso'])
        ).count()
        # Órdenes en proceso específicamente
        ordenes_en_proceso = OrdenTrabajo.query.filter(
            OrdenTrabajo.tecnico_id == user.id,
            OrdenTrabajo.estado == 'en_proceso'
        ).count()
        # Debug logging
        print(f"[DEBUG Dashboard] User {user.id} ({user.username}): ordenes_finalizadas={ordenes_finalizadas}, ordenes_pendientes={ordenes_pendientes}, ordenes_en_proceso={ordenes_en_proceso}")
        # Datos para gráfica de ventas del mes actual
        mes_actual_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ventas_mes_actual = []
        try:
            for dia in range(1, now.day + 1):
                dia_date = mes_actual_start.replace(day=dia)
                dia_start = dia_date.replace(hour=0, minute=0, second=0, microsecond=0)
                dia_end = dia_start + timedelta(days=1)
                # Calculate net sales: total - descuento (NO restar anticipo_total porque ya ingresó antes)
                neto_q = db.session.query(
                    func.coalesce(func.sum(Venta.total - func.coalesce(Venta.descuento, 0)), 0)
                ).filter(
                    Venta.usuario_id == user.id,
                    Venta.fecha >= dia_start,
                    Venta.fecha < dia_end
                ).scalar()
                ventas_mes_actual.append({
                    'dia': str(dia),
                    'monto': int(round(float(neto_q or 0)))
                })
        except Exception as e:
            print(f"Error calculating ventas_mes_actual: {e}")
            ventas_mes_actual = []
        # Notificaciones del usuario
        notifs_unread = Notification.query.filter(Notification.user_id == user.id, Notification.read == False).count()
        ultimas_notifs = Notification.query.filter(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(5).all()

        if ventas_mes_actual is None:
            ventas_mes_actual = []
        return render_template('dashboard/vendedor.html', user=user,
           ventas_mias=ventas_mias, ventas_sucursal=ventas_sucursal,
           ordenes_mias=ordenes_mias, ordenes_sucursal=ordenes_sucursal,
           ordenes_pendientes=ordenes_pendientes, ordenes_en_proceso=ordenes_en_proceso,
           ordenes_finalizadas=ordenes_finalizadas,
           ventas_mes_actual=ventas_mes_actual,
           notifs_unread=notifs_unread, ultimas_notifs=ultimas_notifs,
           ventas_monto_dia=ventas_monto_dia)
    # Metricas
    total_usuarios = User.query.count()
    total_sucursales = Branch.query.count()
    total_ventas = Venta.query.count()
    total_clientes = Client.query.count()
    total_productos = Product.query.count()
    total_ordenes = OrdenTrabajo.query.count()

    # Listas resumen (ultimos 5)
    ultimos_usuarios = User.query.order_by(desc(User.id)).limit(5).all()
    ultimas_ventas = Venta.query.order_by(desc(Venta.id)).limit(5).all()
    ultimos_clientes = Client.query.order_by(desc(Client.id)).limit(5).all()
    ultimos_productos = Product.query.order_by(desc(Product.id)).limit(5).all()
    ultimas_ordenes = OrdenTrabajo.query.order_by(desc(OrdenTrabajo.id)).limit(5).all()

    return render_template(
        "dashboard/index.html",
        total_usuarios=total_usuarios,
        total_sucursales=total_sucursales,
        total_ventas=total_ventas,
        total_clientes=total_clientes,
        total_productos=total_productos,
        total_ordenes=total_ordenes,
        ultimos_usuarios=ultimos_usuarios,
        ultimas_ventas=ultimas_ventas,
        ultimos_clientes=ultimos_clientes,
        ultimos_productos=ultimos_productos,
        ultimas_ordenes=ultimas_ordenes,
        ventas_mes_actual=ventas_mes_actual,
        ordenes_finalizadas=ordenes_finalizadas
    )

@dashboard_bp.route("/logo", methods=["GET", "POST"])
@login_required
@role_required('admin')
def cambiar_logo():
    form = LogoForm()
    if form.validate_on_submit():
        logo_file = form.logo.data
        if logo_file:
            from flask import current_app
            # Defensa en profundidad: verificar contenido real de imagen
            # (la extension ya fue validada por FileAllowed del formulario).
            try:
                from PIL import Image
                logo_file.stream.seek(0)
                with Image.open(logo_file.stream) as img:
                    img.verify()
                logo_file.stream.seek(0)
            except Exception:
                flash("El archivo no es una imagen válida", "danger")
                return render_template("dashboard/cambiar_logo.html", form=form)
            # Always store the main logo as 'logo.png' in the static folder
            target_path = os.path.join(current_app.static_folder, 'logo.png')
            # Ensure directory exists
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            logo_file.save(target_path)
            flash("Logo actualizado correctamente", "success")
            return redirect(url_for("dashboard.index"))
    return render_template("dashboard/cambiar_logo.html", form=form)


@dashboard_bp.route('/pos_format', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def pos_format():
    form = PosFormatForm()
    # load existing config from instance/sales_formats.json per branch
    branch_id = request.args.get('branch_id', type=int) or None
    config_path = os.path.join(os.getcwd(), 'instance', 'sales_formats.json')
    current_cfg = {}
    try:
        if os.path.exists(config_path):
            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                all_cfg = json.load(f)
            if branch_id:
                current_cfg = all_cfg.get(str(branch_id), {})
            else:
                current_cfg = all_cfg.get('default', {})
    except Exception:
        current_cfg = {}

    if request.method == 'GET':
        # Populate form with existing values
        if current_cfg:
            form.ticket_width.data = current_cfg.get('ticket_width', '88')
            form.font_size.data = current_cfg.get('font_size', 12)
            form.show_company.data = current_cfg.get('show_company', True)
            form.include_address.data = current_cfg.get('include_address', True)
            form.auto_print.data = current_cfg.get('auto_print', True)
            form.header_text.data = current_cfg.get('header_text', '')
            form.footer_text.data = current_cfg.get('footer_text', '')

    if form.validate_on_submit():
        # Save config
        cfg = {
            'ticket_width': form.ticket_width.data,
            'font_size': form.font_size.data,
            'show_company': bool(form.show_company.data),
            'include_address': bool(form.include_address.data),
            'auto_print': bool(form.auto_print.data),
            'header_text': form.header_text.data or '',
            'footer_text': form.footer_text.data or ''
        }
        try:
            import json
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            all_cfg = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    all_cfg = json.load(f)
            key = str(branch_id) if branch_id else 'default'
            all_cfg[key] = cfg
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(all_cfg, f, ensure_ascii=False, indent=2)
            flash('Configuracion POS guardada', 'success')
            return redirect(url_for('dashboard.index'))
        except Exception as e:
            flash(f'No se pudo guardar la configuracion: {e}', 'danger')

    return render_template('dashboard/pos_format.html', form=form, branch_id=branch_id)