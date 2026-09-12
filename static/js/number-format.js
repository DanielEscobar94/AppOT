/**
 * Utilidades para formateo de números con separadores de miles (puntos) sin decimales
 * Usando Cleave.js - biblioteca profesional para formateo de inputs
 */

// Almacenar instancias de Cleave para cada input
const cleaveInstances = new Map();

// Formatear número con separadores de miles (puntos) - función de utilidad
function formatearNumero(valor) {
  const numero = Math.round(parseFloat(valor) || 0);
  if (isNaN(numero)) return '0';
  return numero.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

// Limpiar formato y obtener número puro
function limpiarNumero(valorFormateado) {
  if (!valorFormateado && valorFormateado !== 0) return 0;
  const valorStr = valorFormateado.toString();
  const limpio = valorStr.replace(/[\.\s]/g, '');
  const numero = parseInt(limpio, 10);
  return isNaN(numero) ? 0 : numero;
}

// Inicializar Cleave.js en inputs al cargar la página
function inicializarFormatoNumerico() {
  // Esperar a que Cleave esté disponible
  if (typeof Cleave === 'undefined') {
    console.warn('Cleave.js no está cargado aún, reintentando...');
    setTimeout(inicializarFormatoNumerico, 100);
    return;
  }

  // Selectores para inputs de precios y cantidades monetarias
  const selectores = [
    '#producto-precio', // Input específico del POS
    'input[name*="precio"]:not([type="hidden"])',
    'input[name*="monto"]:not([type="hidden"])',
    'input[name*="total"]:not([type="hidden"])',
    'input[name*="anticipo"]:not([type="hidden"])',
    '.formato-numero',
    '.currency-input'
  ];
  
  const inputs = document.querySelectorAll(selectores.join(', '));
  
  inputs.forEach(input => {
    // Si ya tiene una instancia de Cleave, destruirla primero
    if (cleaveInstances.has(input)) {
      cleaveInstances.get(input).destroy();
    }
    
    // Crear nueva instancia de Cleave con formato colombiano
    const cleave = new Cleave(input, {
      numeral: true,
      numeralThousandsGroupStyle: 'thousand',
      numeralDecimalScale: 0,
      numeralPositiveOnly: true,
      delimiter: '.',
      numeralDecimalMark: ',', // No se usa pero se define para evitar conflictos
    });
    
    // Guardar instancia
    cleaveInstances.set(input, cleave);
  });
}

// Limpiar inputs antes de enviar formulario
function limpiarFormularioAntesDeEnviar(form) {
  const inputs = form.querySelectorAll('input[name*="precio_unitario_"], input[name*="monto"], input[name*="anticipo"]');
  
  inputs.forEach(input => {
    if (input.value && input.type === 'hidden') {
      return;
    }
    if (input.value) {
      const valorLimpio = limpiarNumero(input.value);
      if (input.name) {
        input.dataset.valorFormateado = input.value;
        input.value = valorLimpio;
      }
    }
  });
}

// Restaurar formato después de envío (en caso de error)
function restaurarFormatoFormulario(form) {
  const inputs = form.querySelectorAll('input[data-valor-formateado]');
  inputs.forEach(input => {
    if (input.dataset.valorFormateado) {
      input.value = input.dataset.valorFormateado;
      delete input.dataset.valorFormateado;
    }
  });
}

// Re-inicializar cuando se agreguen nuevos inputs dinámicamente
function reinicializarFormatos() {
  inicializarFormatoNumerico();
}

// Inicializar cuando el DOM esté listo
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', inicializarFormatoNumerico);
} else {
  inicializarFormatoNumerico();
}

// Interceptar envíos de formularios para limpiar valores
document.addEventListener('submit', function(e) {
  if (e.target.tagName === 'FORM') {
    limpiarFormularioAntesDeEnviar(e.target);
  }
}, true);

// Exponer funciones globalmente para uso en código inline
window.formatearNumero = formatearNumero;
window.limpiarNumero = limpiarNumero;
window.reinicializarFormatos = reinicializarFormatos;

