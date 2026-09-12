/**
 * AppOTSearch — Motor centralizado de busqueda con autocompletado (Vanilla JS).
 * ----------------------------------------------------------------------------
 * Unifica los buscadores de clientes y productos de todo el proyecto
 * (CRUD /clients, POS /ventas, ordenes de trabajo) bajo un mismo componente
 * DRY: mismo debounce, mismos estados (carga / vacio / error) y misma
 * navegacion por teclado en todas las vistas.
 *
 * Uso:
 *   AppOTSearch.initClientSearch({ input: '#buscar-cliente', results: '#sugerencias',
 *                                  hiddenId: '#cliente-id', onSelect: fn });
 *   AppOTSearch.initProductSearch({ input: '.buscar-producto', results: null,
 *                                   onSelect: fn });
 *
 * Sin dependencias: solo Bootstrap 5.3 (list-group) + fetch nativo.
 * EventBus es opcional: si existe, se emiten eventos search:success/error.
 */
window.AppOTSearch = (function () {
    'use strict';

    var DEFAULTS = {
        minLength: 1,
        debounceMs: 300,
        maxItems: 10,
        loadingText: 'Buscando…',
        emptyText: 'Sin resultados',
        errorText: 'Error al buscar. Intenta de nuevo.'
    };

    function emit(name, data) {
        try {
            if (window.EventBus && typeof window.EventBus.emit === 'function') {
                window.EventBus.emit(name, data);
            }
        } catch (e) { /* EventBus opcional */ }
    }

    /* Debounce con temporizador propio por instancia (sin estado global). */
    function debounce(fn, delay) {
        var timer = null;
        return function () {
            var ctx = this, args = arguments;
            if (timer) clearTimeout(timer);
            timer = setTimeout(function () { fn.apply(ctx, args); }, delay);
        };
    }

    function resolveEl(ref) {
        if (!ref) return null;
        if (typeof ref === 'string') return document.querySelector(ref);
        return ref;
    }

    /* Crear el contenedor de resultados si la vista no lo incluye.
       Posicionamiento absoluto estricto: top 100%, ancho total del padre,
       sin desbordes laterales. El padre se fuerza a position:relative. */
    function ensureResults(input, resultsRef, listClass) {
        var box = resolveEl(resultsRef);
        if (box) {
            var w0 = input.parentNode;
            var cs0 = window.getComputedStyle ? getComputedStyle(w0).position : '';
            if (cs0 === 'static') w0.style.position = 'relative';
            return box;
        }
        box = document.createElement('div');
        box.className = 'appot-search-results list-group shadow';
        if (listClass) box.className += ' ' + listClass;
        box.style.position = 'absolute';
        box.style.top = '100%';
        box.style.left = '0';
        box.style.right = '0';
        box.style.width = '100%';
        box.style.zIndex = '1050';
        box.style.maxHeight = '300px';
        box.style.overflowY = 'auto';
        box.style.marginTop = '2px';
        var wrap = input.parentNode;
        var cs = window.getComputedStyle ? getComputedStyle(wrap).position : '';
        if (cs === 'static') wrap.style.position = 'relative';
        wrap.appendChild(box);
        return box;
    }

    function setBoxVisible(box, visible) {
        if (!box) return;
        box.style.display = visible ? 'block' : 'none';
    }

    /* Fetch JSON con manejo de 401/403/500 sin romper la UI. */
    function fetchJSON(url, options) {
        options = options || {};
        return fetch(url, {
            method: options.method || 'GET',
            headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        }).then(function (res) {
            if (res.status === 401) {
                if (typeof window.auth_show_login_modal === 'function') {
                    try { window.auth_show_login_modal(); } catch (e) { /* noop */ }
                }
                var err401 = new Error('Sesión expirada (401)');
                err401.status = 401;
                throw err401;
            }
            if (res.status === 403) {
                var err403 = new Error('Sin permiso (403)');
                err403.status = 403;
                throw err403;
            }
            if (!res.ok) {
                var err = new Error('Error del servidor (' + res.status + ')');
                err.status = res.status;
                throw err;
            }
            return res.json().catch(function () { return []; });
        });
    }

    /* Normaliza las distintas formas que devuelve GET /clients/buscar. */
    function normalizeClient(item) {
        item = item || {};
        var nombre = item.nombre || '';
        var documento = item.cedula || item.documento || item.cc || item.nit || '';
        if (!nombre && item.label) {
            var m = String(item.label).match(/^(.*)\s*\((.*)\)\s*$/);
            if (m) { nombre = m[1].trim(); if (!documento) documento = m[2].trim(); }
            else { nombre = item.label; }
        }
        return {
            id: item.id,
            nombre: nombre,
            documento: documento,
            correo: item.correo || '',
            telefono: item.telefono || '',
            label: item.label || (nombre + (documento ? ' (' + documento + ')' : '')),
            _raw: item
        };
    }

    /* Normaliza GET /products/buscar ({productos:[]} o array plano). */
    function normalizeProduct(item) {
        item = item || {};
        return {
            id: item.id,
            sku: item.sku || '',
            nombre: item.nombre || item.label || '',
            label: item.label || item.nombre || '',
            precio: item.precio !== undefined ? parseFloat(item.precio) || 0 : 0,
            _raw: item
        };
    }

    function unwrapList(data, key) {
        if (Array.isArray(data)) return data;
        if (data && Array.isArray(data[key])) return data[key];
        return [];
    }

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text !== undefined && text !== null) n.textContent = text;
        return n;
    }

    /* Escape HTML para interpolar datos (servidor/usuario) en innerHTML. */
    function escapeHtml(value) {
        return String(value === null || value === undefined ? '' : value)
            .replace(/[&<>"']/g, function (c) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
            });
    }
    if (typeof window !== 'undefined' && !window.escapeHtml) {
        window.escapeHtml = escapeHtml;
    }

    /* Item de cliente: nombre + documento + contacto (clases Bootstrap). */
    function renderClientItem(client) {
        var b = el('button', 'list-group-item list-group-item-action text-start');
        b.type = 'button';
        var title = el('strong', 'd-block text-truncate', client.nombre || 'Sin nombre');
        b.appendChild(title);
        var meta = [];
        if (client.documento) meta.push('ID: ' + client.documento);
        if (client.telefono) meta.push('Tel: ' + client.telefono);
        if (meta.length) b.appendChild(el('small', 'd-block text-muted text-truncate', meta.join(' · ')));
        if (client.correo) b.appendChild(el('small', 'd-block text-muted text-truncate', client.correo));
        return b;
    }

    /* Item de producto: nombre + SKU + precio. */
    function renderProductItem(p) {
        var b = el('button', 'list-group-item list-group-item-action text-start');
        b.type = 'button';
        var row = el('span', 'd-flex justify-content-between align-items-center gap-2');
        var left = el('span', 'text-truncate', p.nombre || 'Sin nombre');
        if (p.sku) {
            var sku = el('small', 'd-block text-muted text-truncate', 'SKU: ' + p.sku);
            var wrap = el('span', 'min-w-0');
            wrap.style.minWidth = '0';
            wrap.appendChild(left);
            wrap.appendChild(sku);
            row.appendChild(wrap);
        } else {
            row.appendChild(left);
        }
        if (p.precio) {
            var price = el('span', 'badge bg-success flex-shrink-0',
                '$' + Math.round(p.precio).toLocaleString('es-CO'));
            row.appendChild(price);
        }
        b.appendChild(row);
        return b;
    }

    /**
     * Motor generico de autocompletado. Opciones:
     *   input, results, fetchResults(term) -> Promise<array>, renderItem(item) -> Node,
     *   onPick(item), minLength, debounceMs, maxItems, loadingText, emptyText,
     *   errorText, listClass, onSearch (hook), channel (prefijo eventos).
     * Devuelve { destroy, search, clear }.
     */
    function attachAutocomplete(opts) {
        var input = resolveEl(opts.input);
        if (!input) return null;
        var cfg = {
            minLength: opts.minLength !== undefined ? opts.minLength : DEFAULTS.minLength,
            debounceMs: opts.debounceMs || DEFAULTS.debounceMs,
            maxItems: opts.maxItems || DEFAULTS.maxItems,
            loadingText: opts.loadingText || DEFAULTS.loadingText,
            emptyText: opts.emptyText || DEFAULTS.emptyText,
            errorText: opts.errorText || DEFAULTS.errorText,
            channel: opts.channel || 'search',
            successEvent: opts.successEvent || null,
            errorEvent: opts.errorEvent || null
        };
        var box = ensureResults(input, opts.results, opts.listClass);
        setBoxVisible(box, false);

        var seq = 0;            // guardia anti-respuestas tardias
        var items = [];
        var activeIndex = -1;
        var destroyed = false;

        function setLoading() {
            box.innerHTML = '';
            var wrap = el('div', 'list-group-item text-muted small d-flex align-items-center gap-2');
            var sp = el('span', 'spinner-border spinner-border-sm text-primary');
            sp.setAttribute('role', 'status');
            wrap.appendChild(sp);
            wrap.appendChild(el('span', null, cfg.loadingText));
            box.appendChild(wrap);
            setBoxVisible(box, true);
        }

        function setEmpty() {
            box.innerHTML = '';
            box.appendChild(el('div', 'list-group-item text-muted small', cfg.emptyText));
            setBoxVisible(box, true);
        }

        function setError(message) {
            box.innerHTML = '';
            box.appendChild(el('div', 'list-group-item list-group-item-danger small',
                message || cfg.errorText));
            setBoxVisible(box, true);
        }

        function paintActive() {
            var nodes = box.querySelectorAll('[data-appot-idx]');
            Array.prototype.forEach.call(nodes, function (n, i) {
                n.classList.toggle('active', i === activeIndex);
            });
            if (nodes[activeIndex] && nodes[activeIndex].scrollIntoView) {
                nodes[activeIndex].scrollIntoView({ block: 'nearest' });
            }
        }

        function pick(i) {
            if (i < 0 || i >= items.length) return;
            var item = items[i];
            clear();
            try { if (typeof opts.onPick === 'function') opts.onPick(item); } catch (e) {
                if (window.console) console.error('[AppOTSearch] onPick:', e);
            }
        }

        function render(list) {
            items = (list || []).slice(0, cfg.maxItems);
            activeIndex = items.length ? 0 : -1;
            box.innerHTML = '';
            if (!items.length) { setEmpty(); return; }
            items.forEach(function (item, i) {
                var node = opts.renderItem(item);
                node.setAttribute('data-appot-idx', String(i));
                node.addEventListener('mousedown', function (e) {
                    e.preventDefault(); // ganar al blur del input
                    pick(i);
                });
                box.appendChild(node);
            });
            paintActive();
            setBoxVisible(box, true);
        }

        function clear() {
            seq++;
            items = [];
            activeIndex = -1;
            setBoxVisible(box, false);
        }

        function run(term) {
            term = (term || '').trim();
            if (term.length < cfg.minLength) { clear(); return; }
            var my = ++seq;
            setLoading();
            if (typeof opts.onSearch === 'function') {
                try { opts.onSearch(term); } catch (e) { /* noop */ }
            }
            opts.fetchResults(term).then(function (list) {
                if (destroyed || my !== seq) return; // respuesta tardia: ignorar
                render(list);
                emit(cfg.successEvent || (cfg.channel + ':success'), { term: term, results: list });
            }).catch(function (err) {
                if (destroyed || my !== seq) return;
                setError(err && err.message ? String(err.message) : cfg.errorText);
                emit(cfg.errorEvent || (cfg.channel + ':error'), { term: term, error: String(err && err.message || err) });
            });
        }

        var debounced = debounce(function () { run(input.value); }, cfg.debounceMs);

        function onInput() { debounced(); }
        function onKey(e) {
            if (box.style.display === 'none') {
                if (e.key === 'Enter' && typeof opts.onEnter === 'function') {
                    e.preventDefault();
                    opts.onEnter(input.value);
                }
                return;
            }
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (activeIndex < items.length - 1) { activeIndex++; paintActive(); }
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (activeIndex > 0) { activeIndex--; paintActive(); }
            } else if (e.key === 'Enter') {
                if (activeIndex >= 0) { e.preventDefault(); pick(activeIndex); }
                else if (typeof opts.onEnter === 'function') { e.preventDefault(); opts.onEnter(input.value); }
            } else if (e.key === 'Escape') {
                clear();
            }
        }
        function onDocClick(e) {
            if (box.style.display === 'none') return;
            if (box.contains(e.target) || input.contains(e.target)) return;
            setBoxVisible(box, false);
        }

        input.addEventListener('input', onInput);
        input.addEventListener('keydown', onKey);
        document.addEventListener('click', onDocClick);

        return {
            search: run,
            clear: clear,
            hide: function () { setBoxVisible(box, false); },
            element: box,
            destroy: function () {
                destroyed = true;
                input.removeEventListener('input', onInput);
                input.removeEventListener('keydown', onKey);
                document.removeEventListener('click', onDocClick);
            }
        };
    }

    /* Atajo: buscador de clientes contra GET /clients/buscar?q=. */
    function initClientSearch(opts) {
        opts = opts || {};
        var hidden = opts.hiddenId ? resolveEl(opts.hiddenId) : null;
        var engine = attachAutocomplete({
            input: opts.input,
            results: opts.results,
            minLength: opts.minLength !== undefined ? opts.minLength : 1,
            debounceMs: opts.debounceMs,
            maxItems: opts.maxItems,
            channel: 'clients',
            successEvent: 'clients:search-success',
            errorEvent: 'clients:search-error',
            onSearch: opts.onSearch,
            onEnter: opts.onEnter,
            renderItem: opts.renderItem || renderClientItem,
            fetchResults: function (term) {
                var url = (opts.endpoint || '/clients/buscar') + '?q=' + encodeURIComponent(term);
                return fetchJSON(url).then(function (data) {
                    return unwrapList(data, 'clients').map(normalizeClient);
                });
            },
            onPick: function (client) {
                if (hidden) hidden.value = client.id !== undefined ? client.id : '';
                if (typeof opts.onSelect === 'function') opts.onSelect(client);
                emit('clients:selected', client);
            }
        });
        return engine;
    }

    /* Atajo: buscador de productos contra GET /products/buscar?q=. */
    function initProductSearch(opts) {
        opts = opts || {};
        var engine = attachAutocomplete({
            input: opts.input,
            results: opts.results,
            minLength: opts.minLength !== undefined ? opts.minLength : 1,
            debounceMs: opts.debounceMs,
            maxItems: opts.maxItems,
            channel: 'products',
            successEvent: 'products:search-success',
            errorEvent: 'products:search-error',
            onSearch: opts.onSearch,
            onEnter: opts.onEnter,
            renderItem: opts.renderItem || renderProductItem,
            fetchResults: function (term) {
                var url = (opts.endpoint || '/products/buscar') + '?q=' + encodeURIComponent(term);
                return fetchJSON(url).then(function (data) {
                    return unwrapList(data, 'productos').map(normalizeProduct);
                });
            },
            onPick: function (product) {
                if (typeof opts.onSelect === 'function') opts.onSelect(product);
                emit('products:selected', product);
            }
        });
        return engine;
    }

    return {
        version: '1.0.0',
        debounce: debounce,
        fetchJSON: fetchJSON,
        escapeHtml: escapeHtml,
        normalizeClient: normalizeClient,
        normalizeProduct: normalizeProduct,
        attachAutocomplete: attachAutocomplete,
        initClientSearch: initClientSearch,
        initProductSearch: initProductSearch
    };
})();
