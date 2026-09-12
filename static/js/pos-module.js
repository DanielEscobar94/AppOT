/**
 * POS Product Search Module - Buscador de productos independiente para POS
 * Maneja la búsqueda y selección de productos sin depender de otros módulos
 */

window.POSProductSearch = (function() {
    'use strict';

    // Escape HTML defensivo para datos del servidor (XSS)
    function esc(s) {
        return String(s === null || s === undefined ? '' : s)
            .replace(/[&<>"']/g, function (c) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
            });
    }

    // Variables privadas
    let productSearchTimeout = null;
    let isInitialized = false;

    // Configuración
    const config = {
        searchDelay: 300,
        minSearchLength: 1
    };

    // Funciones de búsqueda de productos
    function initializeProductSearch() {
        const productInput = document.querySelector('.buscar-producto');
        if (!productInput) return;

        productInput.addEventListener('input', function() {
            clearTimeout(productSearchTimeout);
            productSearchTimeout = setTimeout(() => {
                searchProducts(this.value.trim());
            }, config.searchDelay);
        });

        // Limpiar resultados al hacer clic fuera
        document.addEventListener('click', function(e) {
            const productInputArea = document.querySelector('.buscar-producto');
            if (productInputArea && !productInputArea.parentNode.contains(e.target)) {
                hideProductResults();
            }
        });

        // Navegación con teclado
        productInput.addEventListener('keydown', function(e) {
            const resultsList = document.querySelector('.pos-product-results');
            if (!resultsList) {
                // Si no hay resultados y presiona Enter, pasar al siguiente campo
                if (e.key === 'Enter') {
                    const productoId = document.getElementById('producto-id');
                    if (productoId && productoId.value) {
                        e.preventDefault();
                        const cantidadInput = document.getElementById('producto-cantidad');
                        if (cantidadInput) {
                            cantidadInput.focus();
                            cantidadInput.select();
                        }
                    }
                }
                return;
            }

            const items = resultsList.querySelectorAll('.pos-result-item');
            let currentIndex = -1;

            items.forEach((item, index) => {
                if (item.classList.contains('active')) {
                    currentIndex = index;
                }
            });

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                const nextIndex = Math.min(items.length - 1, currentIndex + 1);
                if (currentIndex >= 0) items[currentIndex].classList.remove('active');
                items[nextIndex].classList.add('active');
                items[nextIndex].scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                const prevIndex = Math.max(0, currentIndex - 1);
                if (currentIndex >= 0) items[currentIndex].classList.remove('active');
                items[prevIndex].classList.add('active');
                items[prevIndex].scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (currentIndex >= 0 && items[currentIndex]) {
                    items[currentIndex].click();
                }
            } else if (e.key === 'Escape') {
                hideProductResults();
                productInput.focus();
            }
        });
    }

    function searchProducts(term) {
        if (term.length < config.minSearchLength) {
            hideProductResults();
            return;
        }

        fetch(`/products/buscar?q=${encodeURIComponent(term)}`)
            .then(res => res.json())
            .then(data => {
                showProductResults(data);
            })
            .catch(error => {
                console.error('Error buscando productos:', error);
                hideProductResults();
            });
    }

    function showProductResults(data) {
        const productInput = document.querySelector('.buscar-producto');
        if (!productInput) return;

        hideProductResults();

        if (!data || data.length === 0) {
            const list = document.createElement('ul');
            list.className = 'list-group pos-product-results';
            list.style.cssText = 'position: absolute; top: 100%; left: 0; right: 0; z-index: 1000; max-height: 300px; overflow-y: auto; box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15); border-radius: 0.375rem; margin-top: 2px;';

            const li = document.createElement('li');
            li.className = 'list-group-item text-muted';
            li.textContent = 'Sin resultados';
            list.appendChild(li);

            productInput.parentNode.appendChild(list);
            return;
        }

        const list = document.createElement('ul');
        list.className = 'list-group pos-product-results';
        list.style.cssText = 'position: absolute; top: 100%; left: 0; right: 0; z-index: 1000; max-height: 300px; overflow-y: auto; box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15); border-radius: 0.375rem; margin-top: 2px;';

        data.forEach((product, index) => {
            const li = document.createElement('li');
            li.className = 'list-group-item list-group-item-action pos-result-item d-flex justify-content-between align-items-center';
            li.style.cursor = 'pointer';
            li.dataset.index = index;

            const nombre = product.label || product.nombre || '';
            const sku = product.sku || '';
            const precio = product.precio ? formatNumber(product.precio) : '';

            li.innerHTML = `
                <div>
                    <div class="fw-bold">${esc(nombre)}</div>
                    ${sku ? `<small class="text-muted">SKU: ${esc(sku)}</small>` : ''}
                </div>
                <div class="text-end">
                    <div class="fw-bold text-primary">$${precio}</div>
                    <small class="badge bg-success">Producto</small>
                </div>
            `;

            li.addEventListener('mousedown', function(e) {
                e.preventDefault();
                selectProduct(product);
            });

            list.appendChild(li);
        });

        productInput.parentNode.appendChild(list);

        // Activar primer elemento
        const firstItem = list.querySelector('.pos-result-item');
        if (firstItem) {
            firstItem.classList.add('active');
        }
    }

    function hideProductResults() {
        const existingList = document.querySelector('.pos-product-results');
        if (existingList) {
            existingList.remove();
        }
    }

    function selectProduct(product) {
        const productInput = document.querySelector('.buscar-producto');
        const productIdInput = document.getElementById('producto-id');
        const precioInput = document.getElementById('producto-precio');
        const cantidadGroup = document.getElementById('producto-cantidad-group');
        const descuentoGroup = document.getElementById('producto-descuento-group');
        const btnAgregar = document.getElementById('btn-agregar-carrito');

        if (productInput) productInput.value = product.label || product.nombre || '';
        if (productIdInput) productIdInput.value = product.id || '';
        if (precioInput) {
            const precio = Math.round(parseFloat(product.precio) || 0);
            precioInput.value = precio;
        }
        if (cantidadGroup) cantidadGroup.classList.remove('d-none');
        if (descuentoGroup) descuentoGroup.classList.remove('d-none');
        if (btnAgregar) btnAgregar.classList.remove('d-none');

        hideProductResults();

        // Enfocar en cantidad
        setTimeout(() => {
            const cantidadInput = document.getElementById('producto-cantidad');
            if (cantidadInput) {
                cantidadInput.focus();
                cantidadInput.select();
            }
        }, 100);
    }

    // Función auxiliar para formatear números (independiente)
    function formatNumber(valor) {
        const numero = Math.round(parseFloat(valor) || 0);
        if (isNaN(numero)) return '0';
        return numero.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }

    // Inicialización del módulo
    function init() {
        if (isInitialized) {
            console.warn('POSProductSearch ya está inicializado');
            return;
        }

        console.log('Inicializando POS Product Search...');

        // Verificar que estamos en la página correcta
        const isPOSPage = document.querySelector('.buscar-producto') !== null;

        if (!isPOSPage) {
            console.log('No es una página POS, omitiendo inicialización del buscador de productos');
            return;
        }

        initializeProductSearch();

        isInitialized = true;
        console.log('POS Product Search inicializado correctamente');
    }

    // API pública del módulo
    return {
        init: init,
        searchProducts: searchProducts,
        hideProductResults: hideProductResults,
        isInitialized: () => isInitialized,
        version: '1.0.0'
    };
})();

// Auto-inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', function() {
    window.POSProductSearch.init();
});