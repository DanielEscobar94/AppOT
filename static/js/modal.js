/**
 * Envia un formulario por AJAX y ejecuta un callback con la respuesta
 * @param {string} formId - El id del formulario a enviar
 * @param {function} callback - Funcion a ejecutar con la respuesta
 */
function enviarFormularioAjax(formId, callback) {
  console.log('[enviarFormularioAjax] Iniciando envío AJAX para form:', formId);
  const form = document.getElementById(formId);
  if (!form) {
    console.error('[enviarFormularioAjax] Formulario no encontrado:', formId);
    return;
  }
  console.log('[enviarFormularioAjax] Form action:', form.action, 'method:', form.method);
  const data = new FormData(form);
  const headers = { 'X-Requested-With': 'XMLHttpRequest' };
  try {
    // Cinturon + tirantes: el campo csrf del FormData ya cubre, el header tambien
    if (window.csrfHeaders) {
      const extra = window.csrfHeaders({});
      for (const k in extra) headers[k] = extra[k];
    }
  } catch(e) {}
  fetch(form.action, {
    method: form.method || 'POST',
    body: data,
    headers: headers
  })
    .then(res => {
      // try to parse json, but fall back to text for better diagnostics
      return res.text().then(text => {
        try {
          const parsed = text ? JSON.parse(text) : {};
          // attach status for debugging
          parsed.__status = res.status;
          return parsed;
        } catch (e) {
          return { success: false, error: 'Respuesta no-JSON del servidor', __status: res.status, __raw: text };
        }
      });
    })
    .then(resp => {
      if (typeof callback === 'function') callback(resp);
    })
    .catch((err) => {
      console.error('[enviarFormularioAjax] fetch error', err);
      if (typeof callback === 'function') callback({ success: false, error: 'Error de conexion' });
    });
}

if (typeof window !== 'undefined') {
  window.enviarFormularioAjax = enviarFormularioAjax;
}
// modal.js - Funciones reutilizables para Bootstrap modals

/**
 * Abre un modal Bootstrap por id y gestiona el foco correctamente
 * @param {string} modalId - El id del modal a mostrar
 * @param {string} [focusSelector] - Selector del elemento a enfocar al abrir
 */
function abrirModal(modalId, focusSelector) {
  const modalEl = document.getElementById(modalId);
  if (!modalEl) return;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  modal.show();
  // Esperar a que el modal este visible y enfocar el elemento deseado
  modalEl.addEventListener('shown.bs.modal', function handler() {
    if (focusSelector) {
      const el = modalEl.querySelector(focusSelector) || document.querySelector(focusSelector);
      if (el) el.focus();
    }
    modalEl.removeEventListener('shown.bs.modal', handler);
  });
}

/**
 * Cierra un modal Bootstrap por id
 * @param {string} modalId - El id del modal a cerrar
 */
function cerrarModal(modalId) {
  const modalEl = document.getElementById(modalId);
  if (!modalEl) return;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  modal.hide();
  // Mueve el foco al input buscar-cliente si existe, si no al body
  setTimeout(function() {
    var buscarCliente = document.getElementById('buscar-cliente');
    if (buscarCliente) {
      buscarCliente.focus();
      buscarCliente.select && buscarCliente.select();
    } else {
      document.body.focus();
    }
  }, 150);
}

/**
 * Limpia y cierra un modal con formulario
 * @param {string} formId - El id del formulario a limpiar
 * @param {string} modalId - El id del modal a cerrar
 */
function limpiarYCerrarModal(formId, modalId) {
  const form = document.getElementById(formId);
  if (form) form.reset();
  cerrarModal(modalId);
}

// Cambia el label y el name del campo identificacion en el modal segun el tipo de cliente
function activarCambioIdentificacionModal() {
  var tipoCliente = document.getElementById('tipo-cliente');
  var labelIdentificacion = document.getElementById('label-identificacion');
  var inputIdentificacion = document.getElementById('input-identificacion');
  if (tipoCliente && labelIdentificacion && inputIdentificacion) {
    tipoCliente.addEventListener('change', function() {
      if (this.value === 'empresa') {
        labelIdentificacion.textContent = 'NIT';
        inputIdentificacion.setAttribute('name', 'nit');
        inputIdentificacion.setAttribute('placeholder', 'NIT de la empresa');
      } else {
        labelIdentificacion.textContent = 'Numero de identificacion';
        inputIdentificacion.setAttribute('name', 'cc');
        inputIdentificacion.setAttribute('placeholder', 'Cedula o documento');
      }
    });
  }
}

// Inicializa el modal de cliente para todas las vistas
document.addEventListener('DOMContentLoaded', function() {
  try {
    console.log('[modal.js] DOMContentLoaded, inicializando modal.js');
    activarCambioIdentificacionModal();

    var formCliente = document.getElementById('formNuevoCliente');
    if (formCliente) {
      console.log('[modal.js] Encontrado formNuevoCliente, registrando event listener');
    formCliente.addEventListener('submit', function(e) {
      console.log('[modalNuevoCliente] Submit interceptado, previniendo default');
      e.preventDefault();
      console.log('[modalNuevoCliente] e.defaultPrevented:', e.defaultPrevented);
      // Refuerzo: fuerza el name correcto en el campo de identificacion
      var tipoCliente = document.getElementById('tipo-cliente');
      var inputIdentificacion = document.getElementById('input-identificacion');
      if (tipoCliente && inputIdentificacion) {
        if (tipoCliente.value === 'empresa') {
          inputIdentificacion.setAttribute('name', 'nit');
        } else {
          inputIdentificacion.setAttribute('name', 'cc');
        }
      }
      // Validacion HTML5 previa
      if (!formCliente.checkValidity()) {
        formCliente.reportValidity();
        return;
      }
      enviarFormularioAjax('formNuevoCliente', function(resp) {
        try { console.log('[modalNuevoCliente] resp', resp); } catch(e) {}
        if (resp.success && resp.cliente && resp.cliente.id) {
          
          // Mapear los datos del servidor al formato esperado por la UI
          const clienteData = {
            id: resp.cliente.id,
            nombre: resp.cliente.nombre,
            correo: resp.cliente.correo || '',
            telefono: resp.cliente.telefono || '',
            cedula: resp.cliente.cc || resp.cliente.nit || '',
            cc: resp.cliente.cc || '',
            nit: resp.cliente.nit || ''
          };
          
          console.log('[modalNuevoCliente] Cliente creado, actualizando UI con:', clienteData);
          
          // Actualizar directamente la UI (similar a como lo hace el template)
          const buscarCliente = document.getElementById('buscar-cliente');
          const clienteId = document.getElementById('client-id') || document.getElementById('cliente-id');
          const nombreDisplay = document.getElementById('cliente-nombre-display');
          const documentoSpan = document.getElementById('cliente-documento');
          
          if (buscarCliente) buscarCliente.value = clienteData.nombre;
          if (clienteId) {
            clienteId.value = clienteData.id;
            clienteId.dispatchEvent(new Event('input'));
          }
          if (nombreDisplay) nombreDisplay.textContent = clienteData.nombre;
          if (documentoSpan) documentoSpan.textContent = clienteData.cedula;
          
          // Actualizar correo
          const correoSpan = document.getElementById('cliente-correo');
          const correoContainer = document.getElementById('cliente-correo-container');
          if (correoSpan && correoContainer) {
            if (clienteData.correo) {
              correoSpan.textContent = clienteData.correo;
              correoContainer.style.display = 'block';
            } else {
              correoContainer.style.display = 'none';
            }
          }
          
          // Actualizar teléfono
          const telefonoSpan = document.getElementById('cliente-telefono');
          const telefonoContainer = document.getElementById('cliente-telefono-container');
          if (telefonoSpan && telefonoContainer) {
            if (clienteData.telefono) {
              telefonoSpan.textContent = clienteData.telefono;
              telefonoContainer.style.display = 'block';
            } else {
              telefonoContainer.style.display = 'none';
            }
          }
          
          // Mostrar la sección de datos del cliente
          const datosCliente = document.getElementById('datos-cliente');
          if (datosCliente) {
            datosCliente.style.display = 'block';
          }
          
          // Cerrar el modal
          cerrarModal('modalNuevoCliente');
          
          // Limpiar el formulario
          formCliente.reset();
        } else {
          // Mostrar error
          console.error('[modalNuevoCliente] Error en respuesta:', resp);
          alert('Error al crear cliente: ' + (resp.error || 'Error desconocido'));
        }
      });
    });
  }
  } catch (error) {
    console.error('[modal.js] Error en inicialización:', error);
  }
});

// Funcion para limpiar dropdowns de busqueda cuando se abre un modal
function initModalCleanupFix() {
  // Funcion para limpiar dropdowns
  function clearSearchDropdowns() {
    // Limpiar cualquier dropdown de busqueda que este activo
    const dropdownLists = document.querySelectorAll('ul.list-group');
    dropdownLists.forEach(function(list) {
      // Verificar si es un dropdown de busqueda (tiene position absolute y z-index alto)
      const style = list.style;
      if ((style.position === 'absolute' || style.zIndex === '2000') && list.parentNode) {
        list.parentNode.removeChild(list);
      }
    });
    
    // Tambien quitar foco del campo de busqueda
    const buscarClienteInput = document.getElementById('buscar-cliente');
    if (buscarClienteInput) {
      buscarClienteInput.blur();
    }
  }
  
  // Agregar event listeners a todos los botones que abren modales
  document.querySelectorAll('[data-bs-toggle="modal"]').forEach(function(button) {
    button.addEventListener('click', function() {
      // Limpiar inmediatamente cuando se hace clic en el boton
      clearSearchDropdowns();
    });
  });
  
  // Buscar todos los modales y agregar event listeners
  document.querySelectorAll('.modal').forEach(function(modal) {
    modal.addEventListener('show.bs.modal', function() {
      // Limpiar cuando el modal se esta mostrando
      clearSearchDropdowns();
    });
    
    modal.addEventListener('shown.bs.modal', function() {
      // Verificar una vez mas cuando el modal ya esta completamente visible
      clearSearchDropdowns();
    });
  });
}

// Export para uso global
if (typeof window !== 'undefined') {
  window.abrirModal = abrirModal;
  window.cerrarModal = cerrarModal;
  window.limpiarYCerrarModal = limpiarYCerrarModal;
  window.activarCambioIdentificacionModal = activarCambioIdentificacionModal;
  window.initModalCleanupFix = initModalCleanupFix;
  // Global helper for inline onsubmit handlers to ensure AJAX submit
  // no global inline helper needed in original version
}

// Inicializar la funcion de limpieza cuando se carga el DOM
document.addEventListener('DOMContentLoaded', initModalCleanupFix);
