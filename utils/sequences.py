from models.models import BranchSequence
from extensions import db

def get_next_sequence(branch_id, tipo):
    """
    Obtiene el siguiente numero de secuencia para una sucursal y tipo.
    Usa with_for_update() para evitar condiciones de carrera.
    """
    from models.models import Venta
    try:
        seq = BranchSequence.query.filter_by(branch_id=branch_id, tipo=tipo).with_for_update().first()
        if not seq:
            seq = BranchSequence(branch_id=branch_id, tipo=tipo, siguiente=1)
            db.session.add(seq)
            db.session.flush()
        # Buscar el siguiente número de factura disponible
        numero = seq.siguiente
        while True:
            existe = Venta.query.filter_by(branch_id=branch_id, numero_factura=str(numero)).first()
            if not existe:
                break
            numero += 1
        seq.siguiente = numero + 1
        db.session.flush()
        return numero
    except Exception:
        db.session.rollback()
        raise
