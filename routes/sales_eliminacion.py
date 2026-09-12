# Rutas para el sistema de solicitudes de eliminación de ventas
# Este archivo se importará en sales.py

from flask import request, url_for
from flask_login import current_user, login_required
from extensions import db
from models.models import Venta, SolicitudEliminacionVenta, Notification, User
from utils.timezone_utils import get_local_now
from utils.decorators import role_required


def solicitar_eliminacion(venta_id):
    """Crear solicitud de eliminación de una venta"""
    try:
        venta = Venta.query.get_or_404(venta_id)
        
        # Verificar que la venta no esté ya eliminada
        if venta.eliminada:
            return {'ok': False, 'error': 'Esta venta ya fue eliminada'}, 400
        
        # Verificar que no haya una solicitud pendiente
        solicitud_existente = SolicitudEliminacionVenta.query.filter_by(
            venta_id=venta_id,
            estado='pendiente'
        ).first()
        
        if solicitud_existente:
            return {'ok': False, 'error': 'Ya existe una solicitud pendiente para esta venta'}, 400
        
        data = request.get_json()
        motivo = data.get('motivo', '').strip()
        
        if not motivo:
            return {'ok': False, 'error': 'El motivo es obligatorio'}, 400
        
        # Crear la solicitud
        solicitud = SolicitudEliminacionVenta(
            venta_id=venta_id,
            solicitante_id=current_user.id,
            motivo=motivo,
            estado='pendiente'
        )
        db.session.add(solicitud)
        
        # Crear notificaciones para supervisores y admins
        supervisores_admins = User.query.filter(User.rol.in_(['supervisor', 'admin'])).all()
        
        for usuario in supervisores_admins:
            notificacion = Notification(
                user_id=usuario.id,
                message=f'Solicitud de eliminación de venta #{venta.numero_factura} por {current_user.username}',
                link=url_for('sales.gestionar_solicitudes')
            )
            db.session.add(notificacion)
        
        db.session.commit()
        
        return {'ok': True, 'message': 'Solicitud enviada correctamente'}
        
    except Exception as e:
        db.session.rollback()
        return {'ok': False, 'error': str(e)}, 500


def aprobar_solicitud(solicitud_id):
    """Aprobar solicitud y eliminar la venta (soft delete)"""
    try:
        solicitud = SolicitudEliminacionVenta.query.get_or_404(solicitud_id)
        
        if solicitud.estado != 'pendiente':
            return {'ok': False, 'error': 'Esta solicitud ya fue procesada'}, 400
        
        data = request.get_json() or {}
        comentario = data.get('comentario', '').strip()
        
        # Actualizar la solicitud
        solicitud.estado = 'aprobada'
        solicitud.aprobador_id = current_user.id
        solicitud.fecha_respuesta = get_local_now()
        solicitud.comentario_respuesta = comentario or 'Aprobada'
        
        # Marcar la venta como eliminada (soft delete)
        venta = solicitud.venta
        venta.eliminada = True
        venta.motivo_eliminacion = solicitud.motivo
        venta.fecha_eliminacion = get_local_now()
        venta.eliminada_por_id = current_user.id
        
        # Notificar al solicitante
        notificacion = Notification(
            user_id=solicitud.solicitante_id,
            message=f'Tu solicitud de eliminación de venta #{venta.numero_factura} fue APROBADA',
            link=url_for('sales.ver', venta_id=venta.id)
        )
        db.session.add(notificacion)
        
        db.session.commit()
        
        return {'ok': True, 'message': 'Solicitud aprobada y venta eliminada'}
        
    except Exception as e:
        db.session.rollback()
        return {'ok': False, 'error': str(e)}, 500


def rechazar_solicitud(solicitud_id):
    """Rechazar solicitud de eliminación"""
    try:
        solicitud = SolicitudEliminacionVenta.query.get_or_404(solicitud_id)
        
        if solicitud.estado != 'pendiente':
            return {'ok': False, 'error': 'Esta solicitud ya fue procesada'}, 400
        
        data = request.get_json() or {}
        comentario = data.get('comentario', '').strip()
        
        if not comentario:
            return {'ok': False, 'error': 'Debes especificar el motivo del rechazo'}, 400
        
        # Actualizar la solicitud
        solicitud.estado = 'rechazada'
        solicitud.aprobador_id = current_user.id
        solicitud.fecha_respuesta = get_local_now()
        solicitud.comentario_respuesta = comentario
        
        # Notificar al solicitante
        venta = solicitud.venta
        notificacion = Notification(
            user_id=solicitud.solicitante_id,
            message=f'Tu solicitud de eliminación de venta #{venta.numero_factura} fue RECHAZADA: {comentario}',
            link=url_for('sales.ver', venta_id=venta.id)
        )
        db.session.add(notificacion)
        
        db.session.commit()
        
        return {'ok': True, 'message': 'Solicitud rechazada'}
        
    except Exception as e:
        db.session.rollback()
        return {'ok': False, 'error': str(e)}, 500
