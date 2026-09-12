/**
 * Inicialización global de datepickers con Flatpickr
 * Se aplica automáticamente a todos los inputs con clase 'datepicker'
 */

document.addEventListener('DOMContentLoaded', function() {
    // Configuración global de Flatpickr en español con formato dd/mm/yyyy
    const datepickerConfig = {
        dateFormat: "d/m/Y",
        locale: "es",
        allowInput: true,
        disableMobile: true,
        onReady: function(selectedDates, dateStr, instance) {
            // Añadir ícono de calendario en el input
            const input = instance.input;
            if (!input.parentElement.classList.contains('input-group')) {
                const wrapper = document.createElement('div');
                wrapper.className = 'input-group';
                input.parentNode.insertBefore(wrapper, input);
                
                const icon = document.createElement('span');
                icon.className = 'input-group-text';
                icon.innerHTML = '<i class="bi bi-calendar"></i>';
                icon.style.cursor = 'pointer';
                icon.addEventListener('click', function() {
                    instance.open();
                });
                
                wrapper.appendChild(input);
                wrapper.appendChild(icon);
            }
        }
    };

    // Inicializar todos los inputs con clase 'datepicker'
    const datepickerInputs = document.querySelectorAll('input.datepicker, input[type="text"].fecha-input');
    datepickerInputs.forEach(function(input) {
        // Evitar doble inicialización
        if (!input._flatpickr) {
            flatpickr(input, datepickerConfig);
        }
    });

    // Observer para detectar nuevos inputs dinámicos
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === 1) { // Element node
                    // Buscar inputs datepicker en el nodo añadido
                    const newDatepickers = node.querySelectorAll ? 
                        node.querySelectorAll('input.datepicker, input[type="text"].fecha-input') : [];
                    
                    newDatepickers.forEach(function(input) {
                        if (!input._flatpickr) {
                            flatpickr(input, datepickerConfig);
                        }
                    });

                    // Si el nodo mismo es un datepicker
                    if (node.matches && node.matches('input.datepicker, input[type="text"].fecha-input') && !node._flatpickr) {
                        flatpickr(node, datepickerConfig);
                    }
                }
            });
        });
    });

    // Observar cambios en el DOM
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
});
