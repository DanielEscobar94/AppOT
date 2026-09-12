/**
 * Clients Module - Busqueda y seleccion de clientes (Vanilla JS).
 * Delega el autocompletado en el motor centralizado window.AppOTSearch
 * (static/js/shared/search-core.js) y conserva su API publica y eventos
 * para no romper las vistas que lo consumen (POS, ordenes, clients-base).
 *
 * Requiere (en este orden): event-bus.js, search-core.js
 */
window.ClientsModule = (function() {
    'use strict';

    var clientCache = new Map();
    var isInitialized = false;
    var selectedClientId = null;
    var engine = null;

    var config = {
        cacheTimeout: 5 * 60 * 1000, // 5 minutos
        maxSuggestions: 10
    };

    function emit(name, data) {
        try {
            if (window.EventBus && typeof window.EventBus.emit === 'function') {
                window.EventBus.emit(name, data);
            }
        } catch (e) { /* EventBus opcional */ }
    }

    function getCacheKey(searchTerm) {
        return 'client_search_' + String(searchTerm).toLowerCase().trim();
    }

    function setCache(key, data) {
        clientCache.set(key, { data: data, timestamp: Date.now() });
    }

    function getCache(key) {
        var cached = clientCache.get(key);
        if (cached && (Date.now() - cached.timestamp) < config.cacheTimeout) {
            return cached.data;
        }
        clientCache.delete(key);
        return null;
    }

    /* Busqueda programatica con cache (misma firma historica). */
    function searchClients(searchTerm, callback) {
        if (!searchTerm || String(searchTerm).length < 1) {
            callback([]);
            return;
        }
        var cacheKey = getCacheKey(searchTerm);
        var cachedResult = getCache(cacheKey);
        if (cachedResult) {
            callback(cachedResult);
            emit('clients:search-cache-hit', { searchTerm: searchTerm, results: cachedResult });
            return;
        }
        if (!window.AppOTSearch) {
            if (window.console) console.error('[ClientsModule] AppOTSearch no cargado');
            callback([]);
            return;
        }
        window.AppOTSearch.fetchJSON('/clients/buscar?q=' + encodeURIComponent(searchTerm))
            .then(function (data) {
                var results = (Array.isArray(data) ? data : (data.clients || []))
                    .map(window.AppOTSearch.normalizeClient)
                    .slice(0, config.maxSuggestions);
                setCache(cacheKey, results);
                callback(results);
                emit('clients:search-success', { searchTerm: searchTerm, results: results });
            })
            .catch(function (error) {
                if (window.console) console.error('Error buscando clientes:', error);
                callback([]);
                emit('clients:search-error', { searchTerm: searchTerm, error: String(error && error.message || error) });
            });
    }

    /* Aplica la seleccion en los campos conocidos (OT, POS) sin emitir. */
    function applyClientSelection(client) {
        client = client || {};
        selectedClientId = client.id !== undefined ? client.id : null;

        var idField = document.querySelector('input[name="cliente_id"]') ||
                      document.getElementById('client-id') ||
                      document.getElementById('cliente-id');
        if (idField) {
            idField.value = client.id !== undefined && client.id !== null ? client.id : '';
        }

        // Plantillas de ordenes: rellenar el input visible de busqueda
        var searchInput = document.querySelector('.clients-search-input, input[name="cliente_nombre"]');
        if (searchInput && searchInput.id !== 'client-search-input') {
            searchInput.value = client.nombre || '';
        }

        // Panel de datos del cliente (POS y OT)
        var datosCliente = document.getElementById('datos-cliente');
        if (datosCliente) {
            var nombreDisplay = document.getElementById('cliente-nombre-display');
            var documentoSpan = document.getElementById('cliente-documento');
            var correoSpan = document.getElementById('cliente-correo');
            var correoContainer = document.getElementById('cliente-correo-container');
            var telefonoSpan = document.getElementById('cliente-telefono');
            var telefonoContainer = document.getElementById('cliente-telefono-container');
            var btnEditar = document.getElementById('btn-editar-cliente');
            var cedulaInput = document.getElementById('cliente-cedula');
            var telefonoHidden = document.getElementById('cliente-telefono-hidden');

            if (nombreDisplay) nombreDisplay.textContent = client.nombre || '—';
            if (documentoSpan) documentoSpan.textContent = client.documento || client.cedula || '-';
            if (correoSpan && correoContainer) {
                if (client.correo) {
                    correoSpan.textContent = client.correo;
                    correoContainer.style.display = 'block';
                } else {
                    correoContainer.style.display = 'none';
                }
            } else if (correoSpan) {
                correoSpan.textContent = client.correo || '—';
            }
            if (telefonoSpan && telefonoContainer) {
                if (client.telefono) {
                    telefonoSpan.textContent = client.telefono;
                    telefonoContainer.style.display = 'block';
                } else {
                    telefonoContainer.style.display = 'none';
                }
            } else if (telefonoSpan) {
                telefonoSpan.textContent = client.telefono || '—';
            }
            if (cedulaInput) cedulaInput.value = client.documento || client.cedula || '';
            if (telefonoHidden) telefonoHidden.value = client.telefono || '';
            if (btnEditar) btnEditar.style.display = 'inline-block';
            datosCliente.style.display = 'block';
        }

        // En el listado /clients, filtrar la vista a ese cliente
        try {
            var path = window.location.pathname || '';
            if (path === '/clients' || path === '/clients/') {
                var q = new URLSearchParams(window.location.search);
                q.set('selected_id', client.id);
                q.delete('page');
                window.location.href = window.location.pathname + '?' + q.toString();
                return;
            }
        } catch (e) { /* sin redireccion fuera de /clients */ }
    }

    /* Seleccion publica: aplica + notifica (una sola emision por pick;
       el motor ya emite 'clients:selected' al elegir del dropdown). */
    function selectClient(client, opts) {
        applyClientSelection(client);
        if (!opts || opts.emit !== false) {
            emit('clients:selected', client);
        }
    }

    function initializeClientSearch() {
        if (!window.AppOTSearch) {
            if (window.console) console.error('[ClientsModule] AppOTSearch no cargado; autocompletado desactivado');
            return;
        }
        var searchInput = document.querySelector('.clients-search-input, input[name="cliente_nombre"]');
        if (!searchInput) return;

        var suggestions = document.getElementById('client-suggestions') ||
                          document.getElementById('sugerencias');
        var hidden = document.querySelector('input[name="cliente_id"]');

        engine = window.AppOTSearch.initClientSearch({
            input: searchInput,
            results: suggestions,
            hiddenId: hidden,
            maxItems: config.maxSuggestions,
            onSelect: function (client) { selectClient(client, { emit: false }); }
        });
    }

    return {
        init: function() {
            if (isInitialized) {
                if (window.console) console.warn('ClientsModule ya esta inicializado');
                return;
            }
            initializeClientSearch();
            isInitialized = true;
            try {
                if (window.ModuleRegistry) window.ModuleRegistry.register('clients', this);
            } catch (e) { /* registro opcional */ }
            emit('clients:initialized', { module: 'clients' });
        },

        selectClient: selectClient,

        searchClients: function(searchTerm, callback) {
            searchClients(searchTerm, callback);
        },

        getSelectedClientId: function() {
            return selectedClientId;
        },

        clearSelection: function() {
            selectedClientId = null;
            ['cliente_nombre', 'cliente_cedula', 'cliente_telefono', 'cliente_id'].forEach(function (fieldName) {
                var field = document.querySelector('input[name="' + fieldName + '"]');
                if (field) field.value = '';
            });
            if (engine) engine.clear();
            emit('clients:selection-cleared');
        },

        clearCache: function() {
            clientCache.clear();
            emit('clients:cache-cleared');
        },

        getCacheSize: function() {
            return clientCache.size;
        },

        isInitialized: function() {
            return isInitialized;
        },

        version: '3.0.0'
    };
})();

// Auto-inicializar solo si la pagina necesita busqueda de clientes
document.addEventListener('DOMContentLoaded', function() {
    var needsClientSearch = document.body.classList.contains('clients-module') ||
                             document.querySelector('.clients-search-input') !== null ||
                             document.querySelector('input[name="cliente_nombre"]') !== null ||
                             window.location.pathname.includes('/clientes/') ||
                             window.location.pathname.includes('/ventas/') ||
                             window.location.pathname.includes('/ordenes/');

    if (!needsClientSearch) return;

    function boot() {
        try {
            if (window.ClientsModule && window.ClientsModule.init) window.ClientsModule.init();
        } catch (e) {
            if (window.console) console.error('[ClientsModule] init:', e);
        }
    }
    if (window.EventBus && window.AppOTSearch) {
        boot();
    } else {
        setTimeout(function () {
            if (window.AppOTSearch) boot();
            else if (window.console) console.error('[ClientsModule] AppOTSearch no disponible');
        }, 100);
    }
});
