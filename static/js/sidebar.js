/**
 * AppOT — Sidebar (barra lateral izquierda)
 * ---------------------------------------------
 * - Toggle unico en el topbar: colapsa/expande en escritorio (>=1200px)
 *   y abre el drawer Offcanvas en movil/tablet (<1200px).
 * - Persistencia del estado en localStorage para evitar parpadeos
 *   (FOUC / layout shift) al navegar entre módulos.
 * - El estado se aplica ANTES del render mediante un script inline
 *   en el <head> de templates/base.html; aquí solo se sincroniza
 *   el icono del toggle y se manejan los eventos de usuario.
 * - JS vanilla — sin dependencias externas.
 */
(function (window, document) {
    'use strict';

    var STORAGE_KEY = 'appot.sidebar';
    var COLLAPSED_CLASS = 'app-sidebar-collapsed';
    var root = document.documentElement;

    /* ¿La barra está colapsada? (estado ya aplicado por el <head> script) */
    function isCollapsed() {
        return root.classList.contains(COLLAPSED_CLASS);
    }

    /* Aplica el estado y lo persiste en localStorage */
    function setCollapsed(collapsed) {
        if (collapsed) {
            root.classList.add(COLLAPSED_CLASS);
        } else {
            root.classList.remove(COLLAPSED_CLASS);
        }
        syncToggle();
        try {
            localStorage.setItem(STORAGE_KEY, collapsed ? 'collapsed' : 'expanded');
        } catch (e) { /* localStorage no disponible: la sesión no persiste */ }
    }

    /* Sincroniza atributos de accesibilidad del toggle unico del topbar.
       En escritorio refleja el colapso; en movil abre el drawer. */
    function syncToggle() {
        var btn = document.getElementById('sidebarToggle');
        if (!btn) return;
        var collapsed = isCollapsed();
        btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        btn.setAttribute('title', collapsed ? 'Expandir menú' : 'Colapsar menú');
        btn.setAttribute('aria-label', collapsed ? 'Expandir menú' : 'Colapsar menú');
    }

    /* Toggle unico del topbar: en movil abre el drawer, en escritorio colapsa */
    function initSidebarToggle() {
        var btn = document.getElementById('sidebarToggle');
        if (!btn) return;
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            if (isMobileDrawer()) {
                openMobileDrawer();
            } else {
                setCollapsed(!isCollapsed());
            }
        });
    }

    /* Panel de notificaciones dentro de la sidebar (toggle propio) */
    function initNotifPanel() {
        var bell = document.getElementById('notifDropdown');
        var panel = document.getElementById('notifPanel');
        if (!bell || !panel) return;

        bell.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var open = panel.classList.toggle('show');
            bell.setAttribute('aria-expanded', open ? 'true' : 'false');
        });

        // Cerrar al hacer clic fuera del panel
        document.addEventListener('click', function (e) {
            if (!panel.classList.contains('show')) return;
            if (e.target === bell || bell.contains(e.target) || panel.contains(e.target)) return;
            panel.classList.remove('show');
            bell.setAttribute('aria-expanded', 'false');
        });

        // Cerrar al seleccionar una notificación
        Array.prototype.forEach.call(panel.querySelectorAll('.notif-item'), function (item) {
            item.addEventListener('click', function () {
                panel.classList.remove('show');
                bell.setAttribute('aria-expanded', 'false');
            });
        });
    }

    /* Drawer movil (<1200px): al navegar se cierra solo para no tapar
       el contenido. En desktop la sidebar es fija y no hace nada. */
    var MOBILE_MAX = '(max-width: 1199.98px)';

    function isMobileDrawer() {
        return window.matchMedia && window.matchMedia(MOBILE_MAX).matches;
    }

    function closeMobileDrawer() {
        var el = document.getElementById('sidebarOffcanvas');
        if (!el || !isMobileDrawer()) return;
        try {
            if (window.bootstrap && window.bootstrap.Offcanvas) {
                var inst = window.bootstrap.Offcanvas.getInstance(el);
                if (inst) inst.hide();
            }
        } catch (e) { /* Bootstrap no cargado: el drawer se cierra por defecto */ }
    }

    function openMobileDrawer() {
        var el = document.getElementById('sidebarOffcanvas');
        if (!el) return;
        try {
            if (window.bootstrap && window.bootstrap.Offcanvas) {
                var inst = window.bootstrap.Offcanvas.getOrCreateInstance(el);
                if (inst) inst.show();
            }
        } catch (e) { /* Bootstrap no cargado: sin drawer movil */ }
    }

    function initMobileAutoClose() {
        var nav = document.querySelector('.app-sidebar-nav');
        if (!nav) return;
        nav.addEventListener('click', function (e) {
            var link = e.target && e.target.closest ? e.target.closest('a[href]') : null;
            if (!link) return;
            if (link.getAttribute('target') === '_blank') return;
            if (link.hasAttribute('data-bs-toggle')) return;
            closeMobileDrawer();
        });
    }

    /* Accesibilidad: Escape cierra el panel de notificaciones */
    function initNotifEscape() {
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape' && e.key !== 'Esc') return;
            var panel = document.getElementById('notifPanel');
            var bell = document.getElementById('notifDropdown');
            if (panel && panel.classList.contains('show')) {
                panel.classList.remove('show');
                if (bell) {
                    bell.setAttribute('aria-expanded', 'false');
                    try { bell.focus(); } catch (err) { /* noop */ }
                }
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        syncToggle();
        initSidebarToggle();
        initNotifPanel();
        initMobileAutoClose();
        initNotifEscape();
    });

})(window, document);