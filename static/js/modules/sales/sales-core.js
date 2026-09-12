/**
 * Sales Module - Ventas / POS (Vanilla JS).
 * Delega la busqueda de clientes y productos en el motor centralizado
 * window.AppOTSearch (static/js/shared/search-core.js) y conserva su API
 * publica y eventos para no romper las vistas que lo consumen.
 *
 * Requiere (en este orden): event-bus.js, search-core.js
 */
window.SalesModule = (function() {
    'use strict';

    var isInitialized = false;
    var clientEngine = null;
    var productEngine = null;

    var config = {
        searchDelay: 300,
        minSearchLength: 1
    };

    var cache = {
        clients: new Map(),
        products: new Map()
    };

    function emit(name, data) {
        try {
            if (window.EventBus && typeof window.EventBus.emit === 'function') {
                window.EventBus.emit(name, data);
            }
        } catch (e) { /* EventBus opcional */ }
    }

    function coreReady() {
        if (!window.AppOTSearch) {
            if (window.console) console.error('[SalesModule] AppOTSearch no cargado');
            return false;
        }
        return true;
    }

    /* Busqueda de clientes del POS: dropdown centralizado + foco a producto. */
    function initializeClientSearch() {
        // El modulo dedicado de clientes ya cubre este input: no duplicar binding
        if (window.ClientsModule) {
            return;
        }
        if (!coreReady()) return;
        var clientInput = document.getElementById('buscar-cliente');
        if (!clientInput) return;

        clientEngine = window.AppOTSearch.initClientSearch({
            input: clientInput,
            results: document.getElementById('client-suggestions'),
            hiddenId: document.getElementById('cliente-id'),
            minLength: config.minSearchLength,
            debounceMs: config.searchDelay,
            onSelect: function (client) { selectClient(client); }
        });
    }

    function searchClients(term) {
        if (!term || term.length < config.minSearchLength) return;
        if (cache.clients.has(term)) {
            var cached = cache.clients.get(term);
            emit('sales:client-search', { term: term, results: cached });
            return;
        }
        if (!coreReady()) return;
        window.AppOTSearch.fetchJSON('/clients/buscar?q=' + encodeURIComponent(term))
            .then(function (data) {
                var list = (Array.isArray(data) ? data : (data.clients || []))
                    .map(window.AppOTSearch.normalizeClient);
                cache.clients.set(term, list);
                emit('sales:client-search', { term: term, results: list });
            })
            .catch(function (error) {
                if (window.console) console.error('Error buscando clientes:', error);
                emit('sales:error', { type: 'client-search', error: String(error && error.message || error) });
            });
    }

    function selectClient(clientData) {
        var c = clientData && clientData._raw ? clientData._raw : (clientData || {});
        var clientInput = document.getElementById('buscar-cliente');
        var clientIdInput = document.getElementById('cliente-id');
        var clientEmail = document.getElementById('cliente-correo');
        var clientPhone = document.getElementById('cliente-telefono');

        if (clientInput) clientInput.value = c.label || c.nombre || '';
        if (clientIdInput) clientIdInput.value = c.id !== undefined ? c.id : '';
        if (clientEmail) clientEmail.textContent = c.correo || '—';
        if (clientPhone) clientPhone.textContent = c.telefono || '—';

        emit('sales:client-selected', clientData);

        setTimeout(function () {
            var productInput = document.querySelector('.buscar-producto');
            if (productInput) {
                productInput.focus();
                productInput.select();
            }
        }, 100);
    }

    /* Busqueda de productos: el template puede delegarla aqui o usar
       AppOTSearch.initProductSearch directamente con su onSelect. */
    function initializeProductSearch() {
        if (!coreReady()) return;
        var productInput = document.querySelector('.buscar-producto');
        if (!productInput) return;
        // Solo auto-enlazar si la vista no gestiona su propio motor
        if (productInput.dataset.appotSearch === 'off') return;
        productEngine = window.AppOTSearch.initProductSearch({
            input: productInput,
            results: null,
            minLength: config.minSearchLength,
            debounceMs: config.searchDelay,
            onSelect: function (product) {
                emit('sales:product-selected', product);
            }
        });
    }

    function searchProducts(term) {
        if (!term || term.length < config.minSearchLength) return;
        if (cache.products.has(term)) {
            emit('sales:product-search', { term: term, results: cache.products.get(term) });
            return;
        }
        if (!coreReady()) return;
        window.AppOTSearch.fetchJSON('/products/buscar?q=' + encodeURIComponent(term))
            .then(function (data) {
                var list = (data && data.productos ? data.productos : (Array.isArray(data) ? data : []))
                    .map(window.AppOTSearch.normalizeProduct);
                cache.products.set(term, list);
                emit('sales:product-search', { term: term, results: list });
            })
            .catch(function (error) {
                if (window.console) console.error('Error buscando productos:', error);
                emit('sales:error', { type: 'product-search', error: String(error && error.message || error) });
            });
    }

    return {
        init: function() {
            if (isInitialized) {
                if (window.console) console.warn('SalesModule ya esta inicializado');
                return;
            }
            initializeClientSearch();
            initializeProductSearch();
            isInitialized = true;
            try {
                if (window.ModuleRegistry) window.ModuleRegistry.register('sales', this);
            } catch (e) { /* registro opcional */ }
            emit('sales:initialized', { module: 'sales' });
        },

        selectClient: selectClient,
        searchClients: searchClients,
        searchProducts: searchProducts,
        clearCache: function() {
            cache.clients.clear();
            cache.products.clear();
        },

        getCache: function() {
            return { clients: cache.clients.size, products: cache.products.size };
        },

        isInitialized: function() {
            return isInitialized;
        },

        version: '3.0.0'
    };
})();

// Auto-inicializar solo si estamos en paginas de ventas
document.addEventListener('DOMContentLoaded', function() {
    var isSalesPage = document.body.classList.contains('sales-module') ||
                       window.location.pathname.includes('/ventas/') ||
                       document.getElementById('buscar-cliente') !== null;

    if (!isSalesPage) return;

    function boot() {
        try {
            if (window.SalesModule && window.SalesModule.init) window.SalesModule.init();
        } catch (e) {
            if (window.console) console.error('[SalesModule] init:', e);
        }
    }
    if (window.EventBus && window.AppOTSearch) {
        boot();
    } else {
        setTimeout(function () {
            if (window.AppOTSearch) boot();
            else if (window.console) console.error('[SalesModule] AppOTSearch no disponible');
        }, 100);
    }
});
