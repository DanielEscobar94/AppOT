// Global auth interceptor for fetch/XHR responses
(function(window){
    'use strict';

    // Default behavior: on 401 redirect to login, on 403 show toast
    function defaultOnUnauthorized(){
        // preserve the current path for redirect after login
        var next = encodeURIComponent(window.location.pathname + window.location.search || '/');
        window.location.href = '/users/login?next=' + next;
    }

    function defaultOnForbidden(json){
        try{ window.showToast((json && json.message) || 'Acceso denegado', 'danger'); }catch(e){ alert((json && json.message) || 'Acceso denegado'); }
    }

    // CSRF: token desde <meta name="csrf-token"> (inyectado por Flask-WTF).
    // Usar en peticiones POST/PUT/PATCH/DELETE: headers: window.csrfHeaders({...})
    function csrfToken(){
        try{
            var m = document.querySelector('meta[name="csrf-token"]');
            if (m) return m.getAttribute('content') || '';
            var i = document.querySelector('input[name="csrf_token"]');
            if (i) return i.value || '';
        }catch(e){}
        return '';
    }

    function csrfHeaders(extra){
        var h = {};
        if (extra){
            for (var k in extra){ if (Object.prototype.hasOwnProperty.call(extra, k)) h[k] = extra[k]; }
        }
        var t = csrfToken();
        if (t) h['X-CSRFToken'] = t;
        return h;
    }

    // Wrapper around fetch
    async function authFetch(input, init){
        init = init || {};
        init.headers = init.headers || {};
        // CSRF para metodos inseguros (los formularios FormData ya traen el campo)
        try{
            var method = (init.method || 'GET').toUpperCase();
            if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS'){
                var hasToken = init.headers['X-CSRFToken'] || init.headers['x-csrftoken'];
                var isFormData = (typeof FormData !== 'undefined') && (init.body instanceof FormData);
                if (!hasToken && !isFormData){
                    var t = csrfToken();
                    if (t) init.headers['X-CSRFToken'] = t;
                }
            }
        }catch(e){}
        // mark as AJAX for the server
        if (!init.headers['X-Requested-With'] && !init.headers['x-requested-with']){
            init.headers['X-Requested-With'] = 'XMLHttpRequest';
        }
        try{
            const res = await fetch(input, init);
            if (res.status === 401){
                // try parse json body
                let json = null;
                try { json = await res.json(); } catch(e){}
                // allow custom handler if set
                if (window.__auth_on_unauthorized){
                    try{ window.__auth_on_unauthorized(res, json); return res; }catch(e){}
                }
                defaultOnUnauthorized();
                return res;
            }
            if (res.status === 403){
                let json = null;
                try { json = await res.json(); } catch(e){}
                if (window.__auth_on_forbidden){
                    try{ window.__auth_on_forbidden(res, json); return res; }catch(e){}
                }
                defaultOnForbidden(json);
                return res;
            }
            return res;
        }catch(err){
            // network error
            throw err;
        }
    }

    // Expose globally
    window.authFetch = authFetch;
    window.csrfToken = csrfToken;
    window.csrfHeaders = csrfHeaders;

    // Parche defensivo global: inyecta X-CSRFToken en peticiones inseguras
    // same-origin (cubre todos los fetch inline de las plantillas). Los GET,
    // HEAD, OPTIONS y URLs cross-origin no se tocan.
    if (!window._csrfFetchPatched && window.fetch) {
        try {
            window._csrfFetchPatched = true;
            var nativeFetch = window.fetch.bind(window);
            window.fetch = function(input, init) {
                try {
                    var url = (typeof input === 'string') ? input : ((input && input.url) || '');
                    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
                    var unsafe = (method === 'POST' || method === 'PUT' || method === 'PATCH' || method === 'DELETE');
                    var sameOrigin = !/^(https?:)?\/\//i.test(url) || (url.indexOf(window.location.origin) === 0);
                    if (unsafe && sameOrigin) {
                        var token = csrfToken();
                        if (token) {
                            if (input instanceof window.Request && (!init || !init.headers)) {
                                var merged = {};
                                input.headers.forEach(function (v, k) { merged[k] = v; });
                                merged['X-CSRFToken'] = token;
                                input = new window.Request(input, { headers: merged });
                            } else {
                                init = init || {};
                                if (init.headers instanceof window.Headers) {
                                    if (!init.headers.has('X-CSRFToken')) init.headers.set('X-CSRFToken', token);
                                } else if (Array.isArray(init.headers)) {
                                    var found = init.headers.some(function (p) {
                                        return String(p[0]).toLowerCase() === 'x-csrftoken';
                                    });
                                    if (!found) init.headers.push(['X-CSRFToken', token]);
                                } else {
                                    init.headers = init.headers || {};
                                    if (!init.headers['X-CSRFToken'] && !init.headers['x-csrftoken']) {
                                        init.headers['X-CSRFToken'] = token;
                                    }
                                }
                            }
                        }
                    }
                } catch(e) { /* nunca romper la peticion por el parche */ }
                return nativeFetch(input, init);
            };
        } catch(e) { /* noop */ }
    }
    // Allow apps to override default handlers:
    // window.__auth_on_unauthorized = function(response, json) { ... }
    // window.__auth_on_forbidden = function(response, json) { ... }

    // Optional: monkeypatch window.fetch if desired
    // window._nativeFetch = window.fetch; window.fetch = authFetch;

})(window);
