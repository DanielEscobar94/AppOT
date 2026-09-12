"""
Utilidades para manejo de zona horaria en la aplicación.

ZONA HORARIA: America/Bogota (UTC-5)

ESTANDARIZACIÓN: TIMESTAMPTZ
-----------------------------
La base de datos utiliza TIMESTAMP WITH TIME ZONE (TIMESTAMPTZ).
Todos los datetimes se guardan y leen con timezone America/Bogota.


USO EN PYTHON:
--------------
from utils.timezone_utils import get_local_now

# Obtener hora actual de Colombia (timezone-aware)
fecha = get_local_now()

# Al guardar en BD, se inserta como TIMESTAMPTZ en Colombia
venta = Venta(fecha=get_local_now())


USO EN TEMPLATES JINJA2:
-------------------------
SIEMPRE usar los filtros personalizados:

✅ CORRECTO:
{{ venta.fecha|local_datetime }}              -> 23/10/2025 14:30
{{ orden.fecha_creacion|local_date }}         -> 23/10/2025
{{ cierre.fecha_cierre|local_time }}          -> 14:30
{{ venta.fecha|local_datetime('%d-%m-%Y') }}  -> 23-10-2025


FILTROS DISPONIBLES:
--------------------
- local_datetime: Fecha y hora (default: '%d/%m/%Y %H:%M')
- local_date: Solo fecha (default: '%d/%m/%Y')
- local_time: Solo hora (default: '%H:%M')

Todos aceptan formato personalizado como parámetro.
"""

from datetime import datetime
import pytz

# Timezones
COLOMBIA_TZ = pytz.timezone('America/Bogota')
UTC = pytz.utc


def get_local_now():
    """
    Obtiene la hora actual en Colombia como datetime naive (sin timezone).

    Se devuelve sin tzinfo para que PostgreSQL guarde el valor literal
    de Colombia sin convertir a UTC.

    Returns:
        datetime: naive datetime con la hora actual de Colombia
    """
    return datetime.now(COLOMBIA_TZ).replace(tzinfo=None)


def now_utc():
    """Alias explícito para obtener la hora actual de Colombia."""
    return get_local_now()


def utc_to_local(utc_dt):
    """
    Convierte un datetime UTC a zona horaria de Colombia (aware).

    Args:
        utc_dt (datetime): Datetime en UTC (puede ser naive o aware). If naive,
            it is interpreted as UTC.

    Returns:
        datetime: Datetime convertido a Colombia (tzinfo=COLOMBIA_TZ)
    """
    if utc_dt is None:
        return None

    if utc_dt.tzinfo is None:
        utc_dt = UTC.localize(utc_dt)

    return utc_dt.astimezone(COLOMBIA_TZ)


def local_to_utc(local_dt):
    """
    Convierte un datetime local (Colombia) a UTC (aware).

    Args:
        local_dt (datetime): Datetime en zona horaria de Colombia (puede ser
            naive o aware). If naive, it is interpreted as Colombia local time.

    Returns:
        datetime: Datetime convertido a UTC (tzinfo=UTC)
    """
    if local_dt is None:
        return None

    if local_dt.tzinfo is None:
        local_dt = COLOMBIA_TZ.localize(local_dt)

    return local_dt.astimezone(UTC)


def db_to_local(dt):
    """
    Normaliza un datetime de la base de datos para display.

    Con TIMESTAMPTZ configurado en America/Bogota, PostgreSQL puede devolver
    datetimes en Colombia o UTC dependiendo de la configuración de sesión.
    Esta función asegura que siempre retornemos Colombia timezone.

    Args:
        dt: datetime desde la BD (puede ser aware o naive)

    Returns: datetime en timezone de Bogotá o None
    """
    if dt is None:
        return None

    # Si es naive, asumimos Colombia (zona por defecto)
    if dt.tzinfo is None:
        return COLOMBIA_TZ.localize(dt)
    
    # Si ya está en Colombia, retornar tal cual
    if dt.tzinfo.zone == 'America/Bogota':
        return dt
    
    # Si está en otro timezone (ej. UTC), convertir a Colombia
    return dt.astimezone(COLOMBIA_TZ)
