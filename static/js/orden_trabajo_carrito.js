/**
 * Sistema de Carrito de Productos para Órdenes de Trabajo
 * Versión simplificada y funcional - Se integra con el sistema de artículos
 */

(function () {
    'use strict';

    // Escape HTML defensivo (usa el centralizado si esta cargado)
    var esc = (window.AppOTSearch && window.AppOTSearch.escapeHtml) ||
              window.escapeHtml ||
              function (s) {
                  return String(s === null || s === undefined ? '' : s)
                      .replace(/[&<>"']/g, function (c) {
                          return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
                      });
              };

    // Limpiar localStorage si hay mensaje de éxito (orden guardada)
    document.addEventListener('DOMContentLoaded', function() {
        const successAlert = document.querySelector('.alert-success');
        if (successAlert && (successAlert.textContent.includes('creada correctamente') || 
            successAlert.textContent.includes('actualizada correctamente'))) {
            try {
                localStorage.removeItem('orden_trabajo_temp');
                localStorage.removeItem('ot_formulario_create_temp');
                localStorage.removeItem('ot_formulario_edit_temp');
                console.log('LocalStorage limpiado después de guardar exitosamente');
            } catch(e) {
                console.error('Error limpiando localStorage:', e);
            }
        }
    });

    // Variables globales
    let carritoProductos = [];
    let articulos = [];

    // Elementos del DOM - Carrito
    let modalElement = null;
    let skuInput = null;
    let cantidadInput = null;
    let descuentoInput = null;
    let precioInput = null;
    let btnAgregarCarrito = null;
    let listaCarrito = null;
    let totalCarrito = null;
    let sugerenciasDiv = null;

    // Elementos del DOM - Artículos
    let formArticulo = null;
    let listaArticulos = null;
    let totalArticulos = null;
    let articulosJsonInput = null;

    // Timeout para búsqueda
    let searchTimeout = null;

    /**
     * Guardar datos en localStorage
     */
    function guardarEnLocalStorage() {
        const datos = {
            articulos: articulos,
            clienteId: document.getElementById('client-id')?.value || '',
            clienteNombre: document.getElementById('buscar-cliente')?.value || '',
            clienteCedula: document.getElementById('cliente-cedula')?.value || '',
            clienteTelefono: document.getElementById('cliente-telefono-hidden')?.value || '',
            fechaIngreso: document.querySelector('[name="fecha_ingreso"]')?.value || '',
            anticipoMonto: document.getElementById('anticipo_monto')?.value || '',
            anticipoMetodo: document.getElementById('anticipo_metodo')?.value || '',
            numeroFacturaSiigo: document.getElementById('numero_factura_siigo')?.value || '',
            responsable: document.querySelector('[name="responsable"]')?.value || ''
        };
        localStorage.setItem('orden_trabajo_temp', JSON.stringify(datos));
    }

    /**
     * Cargar datos desde localStorage
     */
    function cargarDesdeLocalStorage() {
        const datosGuardados = localStorage.getItem('orden_trabajo_temp');
        if (!datosGuardados) return;

        try {
            const datos = JSON.parse(datosGuardados);

            // Restaurar artículos
            if (datos.articulos && Array.isArray(datos.articulos)) {
                articulos = datos.articulos;
                if (articulosJsonInput) {
                    articulosJsonInput.value = JSON.stringify(articulos);
                }
            }

            // Restaurar datos del cliente
            if (datos.clienteId) {
                const clientIdInput = document.getElementById('client-id');
                const buscarClienteInput = document.getElementById('buscar-cliente');
                const clienteCedulaInput = document.getElementById('cliente-cedula');
                const clienteTelefonoInput = document.getElementById('cliente-telefono-hidden');
                const datosClienteDiv = document.getElementById('datos-cliente');
                const clienteNombreDisplay = document.getElementById('cliente-nombre-display');
                const clienteCedulaDisplay = document.getElementById('cliente-cedula-display');
                const clienteTelefonoDisplay = document.getElementById('cliente-telefono-display');

                if (clientIdInput) clientIdInput.value = datos.clienteId;
                if (buscarClienteInput) buscarClienteInput.value = datos.clienteNombre;
                if (clienteCedulaInput) clienteCedulaInput.value = datos.clienteCedula;
                if (clienteTelefonoInput) clienteTelefonoInput.value = datos.clienteTelefono;

                if (datosClienteDiv) datosClienteDiv.style.display = 'block';
                if (clienteNombreDisplay) clienteNombreDisplay.textContent = datos.clienteNombre;
                if (clienteCedulaDisplay) clienteCedulaDisplay.textContent = datos.clienteCedula;
                if (clienteTelefonoDisplay) clienteTelefonoDisplay.textContent = datos.clienteTelefono;
            }

            // Restaurar otros campos
            if (datos.fechaIngreso) {
                const fechaInput = document.querySelector('[name="fecha_ingreso"]');
                if (fechaInput) fechaInput.value = datos.fechaIngreso;
            }
            if (datos.anticipoMonto) {
                const anticipoMontoInput = document.getElementById('anticipo_monto');
                if (anticipoMontoInput) anticipoMontoInput.value = datos.anticipoMonto;
            }
            if (datos.anticipoMetodo) {
                const anticipoMetodoSelect = document.getElementById('anticipo_metodo');
                if (anticipoMetodoSelect) anticipoMetodoSelect.value = datos.anticipoMetodo;
            }
            if (datos.numeroFacturaSiigo) {
                const numeroFacturaInput = document.getElementById('numero_factura_siigo');
                if (numeroFacturaInput) numeroFacturaInput.value = datos.numeroFacturaSiigo;
            }
            if (datos.responsable) {
                const responsableInput = document.querySelector('[name="responsable"]');
                if (responsableInput) responsableInput.value = datos.responsable;
            }

            console.log('Datos restaurados desde localStorage');
        } catch (e) {
            console.error('Error al cargar datos desde localStorage:', e);
            localStorage.removeItem('orden_trabajo_temp');
        }
    }

    /**
     * Limpiar localStorage
     */
    function limpiarLocalStorage() {
        localStorage.removeItem('orden_trabajo_temp');
        console.log('LocalStorage limpiado');
    }

    /**
     * Inicializar el sistema cuando el DOM esté listo
     */
    function inicializar() {
        // Obtener elementos del DOM - Carrito
        modalElement = document.getElementById('modalArticulo');
        skuInput = document.getElementById('producto-sku');
        cantidadInput = document.getElementById('producto-cantidad');
        descuentoInput = document.getElementById('producto-descuento');
        precioInput = document.getElementById('producto-precio');
        btnAgregarCarrito = document.getElementById('btn-agregar-al-carrito');
        listaCarrito = document.getElementById('productos-articulo-lista');
        totalCarrito = document.getElementById('productos-articulo-total');
        sugerenciasDiv = document.getElementById('productos-sugerencias');

        // Obtener elementos del DOM - Artículos
        formArticulo = document.getElementById('form-articulo');
        listaArticulos = document.getElementById('articulos-lista');
        totalArticulos = document.getElementById('articulos-total');
        articulosJsonInput = document.getElementById('articulos-json');

        // Cargar datos guardados
        cargarDesdeLocalStorage();

        // Configurar event listeners
        configurarEventListeners();

        // Configurar modal
        if (modalElement) {
            configurarModal();
        }

        // Configurar formulario de artículo
        if (formArticulo) {
            configurarFormularioArticulo();
        }

        // Configurar guardado automático
        configurarGuardadoAutomatico();

        // Renderizar artículos al inicio
        renderizarArticulos();
    }

    /**
     * Configurar guardado automático
     */
    function configurarGuardadoAutomatico() {
        // Guardar cuando cambien campos del cliente
        const buscarClienteInput = document.getElementById('buscar-cliente');
        if (buscarClienteInput) {
            buscarClienteInput.addEventListener('input', guardarEnLocalStorage);
        }

        // Guardar cuando cambien otros campos
        const camposAObservar = [
            '[name="fecha_ingreso"]',
            '#anticipo_monto',
            '#anticipo_metodo',
            '#numero_factura_siigo',
            '[name="responsable"]'
        ];

        camposAObservar.forEach(selector => {
            const campo = document.querySelector(selector);
            if (campo) {
                campo.addEventListener('change', guardarEnLocalStorage);
                campo.addEventListener('input', guardarEnLocalStorage);
            }
        });
    }

    /**
     * Configurar el modal
     */
    function configurarModal() {
        // Detectar cuando se abre el modal con el botón "Agregar Artículo"
        const btnAgregarArticulo = document.getElementById('btn-agregar-articulo');
        if (btnAgregarArticulo) {
            btnAgregarArticulo.addEventListener('click', function () {
                console.log('🆕 Abriendo modal para NUEVO artículo - limpiando carrito');
                // Limpiar solo los campos del artículo, sin tocar datos del cliente
                if (formArticulo) {
                    // Limpiar campos del artículo específicamente
                    const tipoSelect = formArticulo.querySelector('[name="tipo"]');
                    const marcaInput = formArticulo.querySelector('[name="marca"]');
                    const referenciaInput = formArticulo.querySelector('[name="referencia"]');
                    const descripcionInput = formArticulo.querySelector('[name="descripcion"]');
                    const valorInput = formArticulo.querySelector('[name="valor"]');
                    const sitioSelect = document.getElementById('articulo-sitio');
                    const articuloIdxInput = formArticulo.querySelector('[name="articulo_idx"]');

                    if (tipoSelect) tipoSelect.value = '';
                    if (marcaInput) marcaInput.value = '';
                    if (referenciaInput) referenciaInput.value = '';
                    if (descripcionInput) descripcionInput.value = '';
                    if (valorInput) valorInput.value = '';
                    if (sitioSelect) sitioSelect.value = '';
                    if (articuloIdxInput) articuloIdxInput.value = '';

                    // Limpiar características seleccionadas
                    const checkboxes = formArticulo.querySelectorAll('input[name="caracteristicas"]');
                    checkboxes.forEach(cb => cb.checked = false);

                    // Limpiar campos de texto adicionales
                    const textosAdicionales = formArticulo.querySelectorAll('.caracteristica-texto');
                    textosAdicionales.forEach(input => input.value = '');

                    // Ocultar todos los checklists de características
                    const checklistReloj = document.getElementById('check_list_reloj');
                    const checklistBateria = document.getElementById('check_list_bateria');
                    const checklistAE = document.getElementById('check_list_ae');
                    if (checklistReloj) checklistReloj.style.display = 'none';
                    if (checklistBateria) checklistBateria.style.display = 'none';
                    if (checklistAE) checklistAE.style.display = 'none';
                }

                // Limpiar carrito de productos completamente
                carritoProductos = [];
                console.log('🧹 Carrito limpiado para nuevo artículo');
                renderizarCarrito();

                // Restaurar título original
                const modalTitle = document.getElementById('modalArticuloLabel');
                if (modalTitle) {
                    modalTitle.innerHTML = '<i class="bi bi-box-seam"></i> Agregar Artículo';
                }
            });
        }

        modalElement.addEventListener('shown.bs.modal', function () {
            // Enfocar campo SKU
            if (skuInput) {
                setTimeout(() => skuInput.focus(), 100);
            }
        });

        modalElement.addEventListener('hidden.bs.modal', function () {
            // Restaurar título cuando se cierra
            const modalTitle = document.getElementById('modalArticuloLabel');
            if (modalTitle) {
                modalTitle.innerHTML = '<i class="bi bi-box-seam"></i> Agregar/Editar Artículo';
            }
        });
    }

    /**
     * Configurar todos los event listeners
     */
    function configurarEventListeners() {
        // Formatear precio mientras se escribe (solo números)
        if (precioInput) {
            precioInput.addEventListener('input', function (e) {
                let valor = this.value.replace(/[^\d]/g, ''); // Solo dígitos
                this.value = valor;
            });
        }

        // Búsqueda en tiempo real
        if (skuInput) {
            skuInput.addEventListener('input', function () {
                const termino = this.value.trim();

                clearTimeout(searchTimeout);

                if (termino.length >= 2) {
                    searchTimeout = setTimeout(() => buscarProductos(termino), 300);
                } else {
                    ocultarSugerencias();
                }
            });
        }

        // Navegación con teclado
        if (skuInput) {
            skuInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    // Si hay solo una sugerencia visible, seleccionarla automáticamente
                    const sugerenciasVisibles = sugerenciasDiv && sugerenciasDiv.style.display !== 'none' && sugerenciasDiv.style.display !== '';
                    if (sugerenciasVisibles) {
                        const items = sugerenciasDiv.querySelectorAll('li.list-group-item-action');
                        console.log('🔍 Enter presionado - Sugerencias visibles:', items.length);
                        if (items.length === 1) {
                            console.log('✅ Solo una coincidencia, seleccionando automáticamente');
                            items[0].click(); // Simular click en la única sugerencia
                            return;
                        } else if (items.length > 1) {
                            console.log('⚠️ Múltiples coincidencias, debe seleccionar manualmente');
                        }
                    } else {
                        console.log('ℹ️ No hay sugerencias visibles');
                    }
                    // Si no hay sugerencias o hay múltiples, pasar al siguiente campo
                    if (cantidadInput) cantidadInput.focus();
                }
            });
        }

        if (cantidadInput) {
            cantidadInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    if (descuentoInput) descuentoInput.focus();
                }
            });
        }

        if (descuentoInput) {
            descuentoInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    if (precioInput) precioInput.focus();
                }
            });
        }

        if (precioInput) {
            precioInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    agregarAlCarrito();
                }
            });
        }

        // Botón agregar al carrito
        if (btnAgregarCarrito) {
            btnAgregarCarrito.addEventListener('click', function (e) {
                e.preventDefault();
                agregarAlCarrito();
            });
        }
    }

    /**
     * Buscar productos en el servidor
     */
    async function buscarProductos(termino) {
        try {
            // GET (el endpoint tambien acepta POST, pero GET evita CSRF)
            const response = await fetch('/products/buscar?q=' + encodeURIComponent(termino), {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error(`Error ${response.status}`);
            }

            const data = await response.json();
            const productos = data.productos || [];
            mostrarSugerencias(productos);

        } catch (error) {
            mostrarError('Error al buscar productos: ' + error.message);
        }
    }

    /**
     * Mostrar sugerencias de productos
     */
    function mostrarSugerencias(productos) {
        if (!sugerenciasDiv) return;

        sugerenciasDiv.innerHTML = '';

        if (productos.length === 0) {
            sugerenciasDiv.innerHTML = '<div class="p-2 text-muted small">No se encontraron productos</div>';
            sugerenciasDiv.style.display = 'block';
            return;
        }

        const ul = document.createElement('ul');
        ul.className = 'list-group';

        productos.forEach((producto, index) => {
            const li = document.createElement('li');
            li.className = 'list-group-item list-group-item-action';
            li.style.cursor = 'pointer';

            // Si solo hay un producto, resaltarlo para indicar que se puede presionar Enter
            if (productos.length === 1) {
                li.classList.add('active');
                li.style.backgroundColor = '#0d6efd';
                li.style.color = 'white';
            }

            const precio = producto.precio ? `$${parseFloat(producto.precio).toFixed(0)}` : '';
            const textoProducto = `${producto.nombre} (${producto.sku}) ${precio}`;

            // Si solo hay un producto, agregar indicador de Enter
            if (productos.length === 1) {
                li.textContent = textoProducto + ' ';
                var kbdHint = document.createElement('small');
                kbdHint.className = 'float-end';
                kbdHint.innerHTML = '<kbd>Enter</kbd> para seleccionar';
                li.appendChild(kbdHint);
            } else {
                li.textContent = textoProducto;
            }

            li.addEventListener('click', function () {
                seleccionarProducto(producto);
            });

            ul.appendChild(li);
        });

        sugerenciasDiv.appendChild(ul);
        sugerenciasDiv.style.display = 'block';

        console.log(`📦 Mostrando ${productos.length} sugerencia(s)`);
    }

    /**
     * Seleccionar un producto de las sugerencias
     */
    function seleccionarProducto(producto) {
        if (skuInput) skuInput.value = producto.nombre + ' (' + producto.sku + ')';

        // Auto-poblar el nombre personalizado con el nombre del producto para facilitar edición
        const nombreCustomInput = document.getElementById('producto-nombre-custom');
        if (nombreCustomInput) {
            nombreCustomInput.value = producto.nombre;
        }

        // Precio sin formato, solo números
        if (precioInput) precioInput.value = Math.round(parseFloat(producto.precio || 0));
        if (cantidadInput) cantidadInput.value = 1;
        if (descuentoInput) descuentoInput.value = 0;

        ocultarSugerencias();

        // Enfocar cantidad
        setTimeout(() => {
            if (cantidadInput) {
                cantidadInput.focus();
                cantidadInput.select();
            }
        }, 100);
    }

    /**
     * Ocultar sugerencias
     */
    function ocultarSugerencias() {
        if (sugerenciasDiv) {
            sugerenciasDiv.style.display = 'none';
            sugerenciasDiv.innerHTML = '';
        }
    }

    /**
     * Mostrar mensaje de error
     */
    function mostrarError(mensaje) {
        if (sugerenciasDiv) {
            sugerenciasDiv.textContent = '';
            var alertBox = document.createElement('div');
            alertBox.className = 'alert alert-danger m-2 p-2 small';
            alertBox.textContent = mensaje;
            sugerenciasDiv.appendChild(alertBox);
            sugerenciasDiv.style.display = 'block';
            setTimeout(ocultarSugerencias, 3000);
        }
    }

    /**
     * Agregar producto al carrito
     */
    function agregarAlCarrito() {
        const sku = skuInput ? skuInput.value.trim() : '';
        const nombreCustomInput = document.getElementById('producto-nombre-custom');
        const nombreCustom = nombreCustomInput ? nombreCustomInput.value.trim() : '';
        const cantidad = cantidadInput ? parseInt(cantidadInput.value) || 1 : 1;
        const descuento = descuentoInput ? parseFloat(descuentoInput.value) || 0 : 0;
        // Eliminar separadores de miles antes de parsear
        const precioStr = precioInput ? precioInput.value.replace(/\./g, '').replace(/,/g, '') : '0';
        const precio = parseFloat(precioStr) || 0;

        // Validaciones
        if (!sku) {
            alert('Por favor ingrese el nombre o SKU del producto');
            if (skuInput) skuInput.focus();
            return;
        }

        if (precio <= 0) {
            alert('Por favor ingrese un precio válido');
            if (precioInput) precioInput.focus();
            return;
        }

        if (cantidad <= 0) {
            alert('La cantidad debe ser mayor a 0');
            if (cantidadInput) cantidadInput.focus();
            return;
        }

        // Crear objeto producto con ID verdaderamente único
        const producto = {
            id: Date.now() + Math.random(), // ID único con componente aleatorio
            sku: sku,
            nombreCustom: nombreCustom,
            cantidad: cantidad,
            descuento: descuento,
            precio: precio
        };

        // Log para debugging
        console.log('➕ Agregando producto al carrito:', {
            id: producto.id,
            sku: producto.sku,
            nombreCustom: producto.nombreCustom,
            cantidad: producto.cantidad,
            precio: producto.precio
        });

        // Agregar al carrito
        carritoProductos.push(producto);

        // Actualizar vista
        renderizarCarrito();

        // Limpiar formulario
        limpiarFormulario();

        // Enfocar SKU para siguiente producto
        if (skuInput) {
            skuInput.focus();
        }
    }

    /**
     * Eliminar producto del carrito
     */
    window.eliminarProductoCarrito = function (id) {
        carritoProductos = carritoProductos.filter(p => p.id !== id);
        renderizarCarrito();
    };

    /**
     * Renderizar el carrito
     */
    function renderizarCarrito() {
        if (!listaCarrito || !totalCarrito) {
            return;
        }

        listaCarrito.innerHTML = '';
        let total = 0;

        if (carritoProductos.length === 0) {
            listaCarrito.innerHTML = '<div class="text-muted small text-center py-2"><i class="bi bi-cart-x"></i> No hay productos agregados</div>';
        } else {
            carritoProductos.forEach(producto => {
                const subtotalSinDesc = producto.cantidad * producto.precio;
                const descuentoMonto = subtotalSinDesc * (producto.descuento / 100);
                const subtotal = subtotalSinDesc - descuentoMonto;
                total += subtotal;

                // Determinar qué nombre mostrar
                const nombreMostrar = producto.nombreCustom || producto.sku;
                const esNombreCustom = producto.nombreCustom && producto.nombreCustom.trim() !== '';

                const div = document.createElement('div');
                div.className = 'd-flex justify-content-between align-items-center border-bottom py-2';

                const descBadge = producto.descuento > 0 ?
                    `<span class="badge bg-warning text-dark ms-1">-${producto.descuento}%</span>` : '';

                const customIcon = '<i class="bi bi-pencil-fill text-primary ms-1" title="Click para editar nombre" style="cursor: pointer;"></i>';

                div.innerHTML = `
                    <div class="flex-grow-1">
                        <strong>
                            <i class="bi bi-box-seam"></i> 
                            <span class="nombre-producto-editable" data-producto-id="${producto.id}" style="cursor: pointer; text-decoration: underline dotted;" title="Click para editar nombre">${esc(nombreMostrar)}</span>${customIcon}
                        </strong>
                        <span class="badge bg-secondary ms-1">${producto.cantidad}x</span>
                        ${descBadge}
                        <br>
                        <small class="text-muted">
                            $${producto.precio.toLocaleString('es-CO')} c/u = 
                            <strong class="text-success">$${Math.round(subtotal).toLocaleString('es-CO')}</strong>
                        </small>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-danger" 
                            onclick="eliminarProductoCarrito(${producto.id})" 
                            title="Eliminar">
                        <i class="bi bi-trash"></i>
                    </button>
                `;

                listaCarrito.appendChild(div);

                // Agregar evento de click para editar nombre
                const nombreSpan = div.querySelector('.nombre-producto-editable');
                const iconoEditar = div.querySelector('.bi-pencil-fill');

                const editarNombre = () => {
                    // Obtener el modal
                    const modal = document.getElementById('modalEditarNombreProducto');
                    const inputNombre = document.getElementById('input-nombre-producto-edit');
                    const btnGuardar = document.getElementById('btn-guardar-nombre-producto');

                    if (!modal || !inputNombre || !btnGuardar) {
                        console.error('Modal de edición no encontrado');
                        return;
                    }

                    // Establecer el valor actual
                    inputNombre.value = nombreMostrar;

                    // Abrir el modal
                    const modalInstance = new bootstrap.Modal(modal);
                    modalInstance.show();

                    // Enfocar el input después de que se abra el modal
                    modal.addEventListener('shown.bs.modal', function focusInput() {
                        inputNombre.focus();
                        inputNombre.select();
                        modal.removeEventListener('shown.bs.modal', focusInput);
                    });

                    // Manejar el guardado
                    const guardarNombre = () => {
                        const nuevoNombre = inputNombre.value.trim().toUpperCase();
                        if (nuevoNombre !== '') {
                            const productoEnCarrito = carritoProductos.find(p => p.id === producto.id);
                            if (productoEnCarrito) {
                                productoEnCarrito.nombreCustom = nuevoNombre;
                                renderizarCarrito();
                            }
                        }
                        modalInstance.hide();
                        btnGuardar.removeEventListener('click', guardarNombre);
                    };

                    // Remover listeners anteriores y agregar nuevo
                    btnGuardar.replaceWith(btnGuardar.cloneNode(true));
                    const nuevoBtn = document.getElementById('btn-guardar-nombre-producto');
                    nuevoBtn.addEventListener('click', guardarNombre);

                    // Permitir guardar con Enter
                    inputNombre.addEventListener('keypress', function manejarEnter(e) {
                        if (e.key === 'Enter') {
                            e.preventDefault();
                            guardarNombre();
                            inputNombre.removeEventListener('keypress', manejarEnter);
                        }
                    });
                };

                if (nombreSpan) nombreSpan.addEventListener('click', editarNombre);
                if (iconoEditar) iconoEditar.addEventListener('click', editarNombre);
            });
        }

        // Actualizar total
        totalCarrito.textContent = Math.round(total).toLocaleString('es-CO');

        // Actualizar campo oculto valor del artículo
        const valorArticuloInput = document.getElementById('valor-articulo');
        if (valorArticuloInput) {
            valorArticuloInput.value = Math.round(total);
        }
    }

    /**
     * Limpiar formulario de productos
     */
    function limpiarFormulario() {
        if (skuInput) skuInput.value = '';
        const nombreCustomInput = document.getElementById('producto-nombre-custom');
        if (nombreCustomInput) nombreCustomInput.value = '';
        if (cantidadInput) cantidadInput.value = '1';
        if (descuentoInput) descuentoInput.value = '0';
        if (precioInput) precioInput.value = '';
        ocultarSugerencias();
    }

    /**
     * Obtener productos del carrito (para guardar con el artículo)
     */
    window.obtenerProductosCarrito = function () {
        return carritoProductos;
    };

    /**
     * Configurar formulario de artículo
     */
    function configurarFormularioArticulo() {
        if (!formArticulo) return;

        formArticulo.addEventListener('submit', function (e) {
            e.preventDefault();

            // Obtener datos del formulario
            const tipo = formArticulo.querySelector('[name="tipo"]').value;
            const marca = formArticulo.querySelector('[name="marca"]').value;
            const referencia = formArticulo.querySelector('[name="referencia"]').value;
            const descripcion = formArticulo.querySelector('[name="descripcion"]').value;
            const valorArticuloInput = document.getElementById('valor-articulo');
            const valor = valorArticuloInput ? parseFloat(valorArticuloInput.value) || 0 : 0;

            // Obtener sitio de reparación
            const sitioSelect = document.getElementById('articulo-sitio');
            const sitioReparacionId = sitioSelect ? sitioSelect.value : null;

            // Validaciones
            if (!tipo || !marca || !referencia) {
                alert('Por favor complete todos los campos obligatorios del artículo');
                return;
            }

            if (!sitioReparacionId) {
                alert('Por favor seleccione el sitio de reparación para este artículo');
                return;
            }

            if (carritoProductos.length === 0) {
                alert('Por favor agregue al menos un producto al artículo');
                return;
            }

            // Capturar CARACTERÍSTICAS
            const modalArticulo = document.getElementById('modalArticulo');
            const caracteristicasChecks = Array.from(modalArticulo.querySelectorAll('input[name="caracteristicas"]:checked')).map(i => i.value.trim());

            // Recopilar campos adicionales de características
            const todasCaracteristicas = [...caracteristicasChecks];

            const eslabones = document.getElementById('eslabones_numero')?.value;
            if (eslabones) todasCaracteristicas.push(`Eslabones: ${eslabones.trim()}`);

            const tapaTipo = modalArticulo.querySelector('input[name="tapa_tipo"]:checked');
            if (tapaTipo) todasCaracteristicas.push(`Reloj: ${tapaTipo.value}`);

            const garantia = modalArticulo.querySelector('input[name="garantia"]:checked');
            if (garantia) todasCaracteristicas.push(`Garantía: ${garantia.value}`);

            const bateriaVoltaje = document.getElementById('bateria_voltaje')?.value;
            if (bateriaVoltaje) todasCaracteristicas.push(`Voltaje: ${bateriaVoltaje.trim()}`);

            const bateriaAmperaje = document.getElementById('bateria_amperaje')?.value;
            if (bateriaAmperaje) todasCaracteristicas.push(`Amperaje: ${bateriaAmperaje.trim()}`);

            const bateriaCeldas = document.getElementById('bateria_celdas')?.value;
            if (bateriaCeldas) todasCaracteristicas.push(`Celdas: ${bateriaCeldas.trim()}`);

            const bateriaAplicacion = document.querySelector('input[name="bateria_aplicacion"]:checked');
            if (bateriaAplicacion) todasCaracteristicas.push(`Aplicación: ${bateriaAplicacion.value}`);

            // Crear objeto artículo con productos Y CARACTERÍSTICAS Y SITIO
            const articulo = {
                tipo: tipo,
                marca: marca,
                referencia: referencia,
                descripcion: descripcion,
                valor: valor,
                sitio_reparacion_id: parseInt(sitioReparacionId),
                caracteristicas: todasCaracteristicas,
                productos: carritoProductos.map(p => ({
                    sku: p.sku,
                    nombreCustom: p.nombreCustom || '',
                    cantidad: p.cantidad,
                    descuento: p.descuento,
                    precio: p.precio
                }))
            };

            // Verificar si estamos editando o creando nuevo
            const articuloIdx = formArticulo.querySelector('[name="articulo_idx"]')?.value;
            if (articuloIdx !== '' && articuloIdx !== null && !isNaN(articuloIdx)) {
                // EDITAR artículo existente
                const idx = parseInt(articuloIdx);
                articulos[idx] = articulo;
                console.log('Artículo editado en posición', idx);
            } else {
                // AGREGAR nuevo artículo
                articulos.push(articulo);
                console.log('Nuevo artículo agregado');
            }

            // Actualizar el input hidden con JSON
            if (articulosJsonInput) {
                articulosJsonInput.value = JSON.stringify(articulos);
            }

            // Guardar en localStorage
            guardarEnLocalStorage();

            // Renderizar lista de artículos
            renderizarArticulos();

            // Cerrar modal
            if (modalElement && window.bootstrap) {
                const modal = bootstrap.Modal.getInstance(modalElement);
                if (modal) modal.hide();
            }

            // Limpiar formulario
            formArticulo.reset();
            carritoProductos = [];
            renderizarCarrito();
        });
    }

    /**
     * Renderizar lista de artículos
     */
    function renderizarArticulos() {
        if (!listaArticulos) {
            return;
        }

        listaArticulos.innerHTML = '';
        let totalGeneral = 0;

        if (articulos.length === 0) {
            listaArticulos.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No hay artículos agregados.</td></tr>';
        } else {
            articulos.forEach((art, idx) => {
                totalGeneral += parseFloat(art.valor) || 0;

                // Mostrar productos del artículo
                let productosDisplay = '-';
                if (art.productos && art.productos.length > 0) {
                    productosDisplay = art.productos.map(p =>
                        `${p.sku} (${p.cantidad}x)`
                    ).join(', ');
                }

                // Obtener nombre del sitio de reparación
                let sitioDisplay = '-';
                if (art.sitio_reparacion_id && window.sitiosReparacion) {
                    const sitio = window.sitiosReparacion.find(s => s[0] === art.sitio_reparacion_id);
                    if (sitio) {
                        sitioDisplay = `<span class="badge bg-primary">${esc(sitio[1])}</span>`;
                    }
                }

                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><span class="badge bg-secondary">${idx + 1}</span></td>
                    <td><i class="bi bi-box"></i> <span class="fw-bold">${esc(art.tipo)}</span></td>
                    <td><span class="badge bg-info text-dark">${esc(art.marca)}</span></td>
                    <td><span class="badge bg-light text-dark">${esc(art.referencia)}</span></td>
                    <td>${esc(art.descripcion) || '-'}</td>
                    <td>${sitioDisplay}</td>
                    <td><small>${esc(productosDisplay)}</small></td>
                    <td class="text-end fw-bold text-success">$${Math.round(art.valor).toLocaleString('es-CO')}</td>
                    <td class="text-center">
                        <div class="btn-group btn-group-sm" role="group">
                            <button type="button" class="btn btn-outline-primary" 
                                    onclick="editarArticuloCompleto(${idx})" 
                                    title="Editar artículo completo">
                                <i class="bi bi-pencil-square"></i>
                            </button>
                            <button type="button" class="btn btn-outline-danger" 
                                    onclick="confirmarEliminarArticulo(${idx})" 
                                    title="Eliminar artículo">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </td>
                `;
                listaArticulos.appendChild(row);
            });
        }

        // Actualizar total
        if (totalArticulos) {
            totalArticulos.textContent = Math.round(totalGeneral).toLocaleString('es-CO');
        }

        // Actualizar total final si existe la función (modo edición)
        if (typeof window.actualizarTotalFinal === 'function') {
            window.actualizarTotalFinal();
        }
    }

    /**
     * Eliminar artículo
     */
    window.eliminarArticulo = function (idx) {
        articulos.splice(idx, 1);

        // Actualizar JSON
        if (articulosJsonInput) {
            articulosJsonInput.value = JSON.stringify(articulos);
        }

        // Guardar en localStorage
        guardarEnLocalStorage();

        renderizarArticulos();
    };

    /**
     * Confirmar eliminación de artículo
     */
    window.confirmarEliminarArticulo = function (idx) {
        const articulo = articulos[idx];
        const info = `${articulo.tipo || 'Artículo'} - ${articulo.marca || ''} ${articulo.referencia || ''}`.trim();

        if (confirm(`¿Eliminar este artículo?\n\n${info}\n\nEsta acción no se puede deshacer.`)) {
            window.eliminarArticulo(idx);
        }
    };

    /**
     * Editar artículo completo (características + productos)
     */
    window.editarArticuloCompleto = function (idx) {
        const articulo = articulos[idx];

        // Verificar elementos del DOM
        const modal = document.getElementById('modalArticulo');
        const form = document.getElementById('form-articulo');
        if (!modal || !form) {
            alert('No se encontró el modal de artículos');
            return;
        }

        // Llenar datos básicos del artículo
        form['tipo'].value = articulo.tipo || '';
        form['marca'].value = articulo.marca || '';
        form['referencia'].value = articulo.referencia || '';
        form['descripcion'].value = articulo.descripcion || '';
        form['articulo_idx'].value = idx;

        // Cargar sitio de reparación
        const sitioSelect = document.getElementById('articulo-sitio');
        if (sitioSelect && articulo.sitio_reparacion_id) {
            sitioSelect.value = articulo.sitio_reparacion_id;
        }

        // Cambiar título del modal
        const modalTitle = document.getElementById('modalArticuloLabel');
        if (modalTitle) {
            modalTitle.textContent = '';
            var titleIcon = document.createElement('i');
            titleIcon.className = 'bi bi-pencil-square';
            modalTitle.appendChild(titleIcon);
            modalTitle.appendChild(document.createTextNode(
                ' Editar: ' + (articulo.tipo || 'Artículo') + ' - ' +
                (articulo.marca || '') + ' ' + (articulo.referencia || '')));
        }

        // Cargar productos del artículo en el carrito con IDs únicos
        carritoProductos = [];
        if (articulo.productos && Array.isArray(articulo.productos)) {
            articulo.productos.forEach((p, idx) => {
                carritoProductos.push({
                    id: Date.now() + idx + Math.random(), // ID único
                    sku: p.sku || '',
                    nombreCustom: p.nombreCustom || '',
                    cantidad: p.cantidad || 1,
                    descuento: p.descuento || 0,
                    precio: p.precio || 0
                });
            });
        }
        renderizarCarrito();

        // Limpiar campos de búsqueda
        const skuInput = document.getElementById('producto-sku');
        const cantidadInput = document.getElementById('producto-cantidad');
        const descuentoInput = document.getElementById('producto-descuento');
        const precioInput = document.getElementById('producto-precio');
        if (skuInput) skuInput.value = '';
        if (cantidadInput) cantidadInput.value = '1';
        if (descuentoInput) descuentoInput.value = '0';
        if (precioInput) precioInput.value = '';

        // Limpiar TODAS las características
        document.querySelectorAll('input[name="caracteristicas"]').forEach(cb => cb.checked = false);
        document.querySelectorAll('input[name="tapa_tipo"]').forEach(rb => rb.checked = false);
        document.querySelectorAll('input[name="garantia"]').forEach(rb => rb.checked = false);
        document.querySelectorAll('input[name="bateria_aplicacion"]').forEach(rb => rb.checked = false);

        const eslabones = document.getElementById('eslabones_numero');
        const voltaje = document.getElementById('bateria_voltaje');
        const amperaje = document.getElementById('bateria_amperaje');
        const celdas = document.getElementById('bateria_celdas');
        if (eslabones) eslabones.value = '';
        if (voltaje) voltaje.value = '';
        if (amperaje) amperaje.value = '';
        if (celdas) celdas.value = '';

        // Restaurar características del artículo
        if (articulo.caracteristicas && Array.isArray(articulo.caracteristicas)) {
            articulo.caracteristicas.forEach(caracteristica => {
                // Buscar checkbox exacto
                const checkbox = document.querySelector(`input[name="caracteristicas"][value="${caracteristica}"]`);
                if (checkbox) {
                    checkbox.checked = true;
                }

                // Campos especiales
                if (caracteristica.startsWith('Eslabones: ')) {
                    const num = caracteristica.replace('Eslabones: ', '');
                    if (eslabones) eslabones.value = num;
                }
                else if (caracteristica.startsWith('Reloj: ')) {
                    const tipo = caracteristica.replace('Reloj: ', '');
                    const radio = document.querySelector(`input[name="tapa_tipo"][value="${tipo}"]`);
                    if (radio) radio.checked = true;
                }
                else if (caracteristica.startsWith('Garantía: ')) {
                    const tipo = caracteristica.replace('Garantía: ', '');
                    const radio = document.querySelector(`input[name="garantia"][value="${tipo}"]`);
                    if (radio) radio.checked = true;
                }
                else if (caracteristica.startsWith('Voltaje: ')) {
                    const val = caracteristica.replace('Voltaje: ', '');
                    if (voltaje) voltaje.value = val;
                }
                else if (caracteristica.startsWith('Amperaje: ')) {
                    const val = caracteristica.replace('Amperaje: ', '');
                    if (amperaje) amperaje.value = val;
                }
                else if (caracteristica.startsWith('Celdas: ')) {
                    const val = caracteristica.replace('Celdas: ', '');
                    if (celdas) celdas.value = val;
                }
                else if (caracteristica.startsWith('Aplicación: ')) {
                    const tipo = caracteristica.replace('Aplicación: ', '');
                    const radio = document.querySelector(`input[name="bateria_aplicacion"][value="${tipo}"]`);
                    if (radio) radio.checked = true;
                }
            });
        }

        // Abrir modal
        if (window.bootstrap) {
            const modalInstance = new bootstrap.Modal(modal);
            modalInstance.show();
        }
    };

    /**
     * Cargar productos existentes al carrito (para modo edición)
     */
    window.cargarProductosExistentes = function (productos) {
        if (!productos || !Array.isArray(productos)) {
            return;
        }

        // Verificar elementos del DOM
        if (!listaCarrito) {
            listaCarrito = document.getElementById('productos-articulo-lista');
        }
        if (!totalCarrito) {
            totalCarrito = document.getElementById('productos-articulo-total');
        }

        if (!listaCarrito || !totalCarrito) {
            return;
        }

        // Limpiar carrito actual
        carritoProductos = [];

        // Convertir productos existentes al formato del carrito
        productos.forEach((prod, index) => {
            const nombreProducto = prod.nombre_producto ||
                (prod.producto ? prod.producto.nombre : 'Producto') ||
                'Producto sin nombre';
            const sku = prod.producto && prod.producto.sku ?
                `${nombreProducto} (${prod.producto.sku})` :
                nombreProducto;

            const productoCarrito = {
                id: prod.id || Date.now() + index, // Usar ID real o generar uno
                sku: sku,
                cantidad: prod.cantidad || 1,
                descuento: 0, // Los productos guardados no tienen descuento en el formato actual
                precio: parseFloat(prod.precio_unitario) || 0
            };

            carritoProductos.push(productoCarrito);
        });

        // Renderizar el carrito con los productos cargados
        renderizarCarrito();
    };

    /**
     * Cargar artículos existentes (para modo edición)
     */
    window.cargarArticulosExistentes = function (articulosJson) {
        if (!articulosJson) {
            return;
        }

        // Verificar elementos del DOM
        if (!listaArticulos) {
            listaArticulos = document.getElementById('articulos-lista');
        }
        if (!totalArticulos) {
            totalArticulos = document.getElementById('articulos-total');
        }
        if (!articulosJsonInput) {
            articulosJsonInput = document.getElementById('articulos-json');
        }

        if (!listaArticulos || !totalArticulos) {
            return;
        }

        try {
            // Parsear JSON si es string
            const articulosData = typeof articulosJson === 'string' ?
                JSON.parse(articulosJson) : articulosJson;

            if (!Array.isArray(articulosData) || articulosData.length === 0) {
                return;
            }

            // Cargar artículos al array
            articulos = articulosData;

            // Actualizar el input hidden
            if (articulosJsonInput) {
                articulosJsonInput.value = JSON.stringify(articulos);
            }

            // Renderizar artículos
            renderizarArticulos();

        } catch (e) {
            console.error('❌ Error al cargar artículos:', e);
        }
    };

    /**
     * Auto-guardar formulario en localStorage para prevenir pérdida de datos
     */
    function autoGuardarFormulario() {
        try {
            // Usar clave diferente para crear vs editar
            const storageKey = window.ordenExistente ? 'ot_formulario_edit_temp' : 'ot_formulario_create_temp';

            const formData = {
                // Campos básicos
                categoria: document.getElementById('categoria')?.value || '',
                marca: document.getElementById('marca')?.value || '',
                referencia: document.getElementById('referencia')?.value || '',
                descripcion: document.getElementById('descripcion')?.value || '',
                tecnico_id: document.getElementById('tecnico_id')?.value || '',

                // Cliente - datos completos
                client_id: document.getElementById('client-id')?.value || '',
                cliente_nombre: document.getElementById('buscar-cliente')?.value || '',
                cliente_documento: document.getElementById('cliente-documento')?.textContent || '',
                cliente_telefono: document.getElementById('cliente-telefono')?.textContent || '',
                cliente_correo: document.getElementById('cliente-correo')?.textContent || '',

                // Artículos y datos complejos
                articulos: articulos,
                timestamp: new Date().getTime()
            };

            localStorage.setItem(storageKey, JSON.stringify(formData));
        } catch (e) {
            console.warn('No se pudo guardar en localStorage:', e);
        }
    }

    // Exponer globalmente para uso desde otros scripts
    window.autoGuardarFormulario = autoGuardarFormulario;

    /**
     * Restaurar formulario desde localStorage
     */
    function restaurarFormulario() {
        try {
            // Usar clave diferente para crear vs editar
            const storageKey = window.ordenExistente ? 'ot_formulario_edit_temp' : 'ot_formulario_create_temp';

            const stored = localStorage.getItem(storageKey);
            if (!stored) return;

            const formData = JSON.parse(stored);

            // Verificar que no sea muy antiguo (más de 24 horas)
            const now = new Date().getTime();
            if (formData.timestamp && (now - formData.timestamp) > 86400000) {
                localStorage.removeItem(storageKey);
                return;
            }

            // Solo restaurar si los campos están vacíos (evitar sobrescribir en edición)
            const categoriaField = document.getElementById('categoria');
            if (categoriaField && !categoriaField.value && formData.categoria) {
                categoriaField.value = formData.categoria;
            }

            const marcaField = document.getElementById('marca');
            if (marcaField && !marcaField.value && formData.marca) {
                marcaField.value = formData.marca;
            }

            const referenciaField = document.getElementById('referencia');
            if (referenciaField && !referenciaField.value && formData.referencia) {
                referenciaField.value = formData.referencia;
            }

            const descripcionField = document.getElementById('descripcion');
            if (descripcionField && !descripcionField.value && formData.descripcion) {
                descripcionField.value = formData.descripcion;
            }

            const tecnicoField = document.getElementById('tecnico_id');
            if (tecnicoField && !tecnicoField.value && formData.tecnico_id) {
                tecnicoField.value = formData.tecnico_id;
            }

            // Restaurar cliente si existe
            if (formData.client_id && formData.cliente_nombre) {
                const clientIdField = document.getElementById('client-id');
                const buscarClienteField = document.getElementById('buscar-cliente');
                const datosClienteDiv = document.getElementById('datos-cliente');
                const clienteNombreDisplay = document.getElementById('cliente-nombre-display');

                if (clientIdField && !clientIdField.value) {
                    clientIdField.value = formData.client_id;
                    if (buscarClienteField) {
                        buscarClienteField.value = formData.cliente_nombre;
                    }
                    if (datosClienteDiv) {
                        datosClienteDiv.style.display = 'block';
                    }
                    if (clienteNombreDisplay) {
                        clienteNombreDisplay.textContent = formData.cliente_nombre;
                    }

                    // Si hay más datos del cliente guardados, restaurarlos también
                    if (formData.cliente_documento) {
                        const clienteDocumento = document.getElementById('cliente-documento');
                        if (clienteDocumento) clienteDocumento.textContent = formData.cliente_documento;
                    }
                    if (formData.cliente_telefono) {
                        const clienteTelefono = document.getElementById('cliente-telefono');
                        if (clienteTelefono) clienteTelefono.textContent = formData.cliente_telefono;
                    }
                    if (formData.cliente_correo) {
                        const clienteCorreo = document.getElementById('cliente-correo');
                        const clienteCorreoContainer = document.getElementById('cliente-correo-container');
                        if (clienteCorreo) clienteCorreo.textContent = formData.cliente_correo;
                        if (clienteCorreoContainer) clienteCorreoContainer.style.display = 'block';
                    }

                    console.log('✅ Cliente restaurado:', formData.cliente_nombre);
                }
            }

            // Restaurar artículos si existen
            if (formData.articulos && formData.articulos.length > 0 && articulos.length === 0) {
                articulos = formData.articulos;
                if (articulosJsonInput) {
                    articulosJsonInput.value = JSON.stringify(articulos);
                }
                renderizarArticulos();
            }

            console.log('✅ Formulario restaurado desde auto-guardado');
        } catch (e) {
            console.warn('No se pudo restaurar desde localStorage:', e);
        }
    }

    /**
     * Limpiar localStorage después de guardar exitosamente
     */
    window.limpiarAutoGuardado = function () {
        try {
            // Limpiar ambas claves posibles
            localStorage.removeItem('ot_formulario_create_temp');
            localStorage.removeItem('ot_formulario_edit_temp');
        } catch (e) {
            console.warn('No se pudo limpiar localStorage:', e);
        }
    };

    /**
     * Configurar auto-guardado en cambios de formulario
     */
    function configurarAutoGuardado() {
        const campos = ['categoria', 'marca', 'referencia', 'descripcion', 'tecnico_id'];

        campos.forEach(campoId => {
            const campo = document.getElementById(campoId);
            if (campo) {
                campo.addEventListener('input', autoGuardarFormulario);
                campo.addEventListener('change', autoGuardarFormulario);
            }
        });

        // Auto-guardar cuando se selecciona un cliente
        if (window.EventBus) {
            window.EventBus.on('clients:selected', function (client) {
                console.log('🔔 Cliente seleccionado, auto-guardando:', client.nombre);
                setTimeout(autoGuardarFormulario, 100);
            });
        }

        // Auto-guardar cuando se modifican artículos
        const originalRenderizar = renderizarArticulos;
        renderizarArticulos = function () {
            originalRenderizar();
            autoGuardarFormulario();
        };
    }

    /**
     * Inicializar cuando el DOM esté listo
     */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            inicializar();

            // Restaurar datos si existen
            // Si estamos en página de crear y NO hay parámetros en URL, limpiar localStorage
            // Esto evita que datos de edición anterior se carguen en nueva OT
            const urlParams = new URLSearchParams(window.location.search);
            const hasParams = urlParams.toString().length > 0;
            if (!hasParams) {
                limpiarLocalStorage();
                window.limpiarAutoGuardado();
            }

            setTimeout(restaurarFormulario, 100);

            // Configurar auto-guardado
            configurarAutoGuardado();

            // Limpiar auto-guardado al enviar el formulario exitosamente
            const form = document.querySelector('form[action*="crear"]');
            if (form) {
                form.addEventListener('submit', function () {
                    // Limpiar inmediatamente al hacer submit
                    setTimeout(() => {
                        limpiarLocalStorage();
                        window.limpiarAutoGuardado();
                    }, 500);
                });
            }
        });
    } else {
        inicializar();
        setTimeout(restaurarFormulario, 100);
        configurarAutoGuardado();
        
        // También limpiar localStorage al guardar en modo edición
        const formEditar = document.querySelector('form[action*="editar"]');
        if (formEditar) {
            formEditar.addEventListener('submit', function () {
                setTimeout(() => {
                    limpiarLocalStorage();
                    window.limpiarAutoGuardado();
                }, 500);
            });
        }
    }

    // Exponer función de limpieza globalmente
    window.limpiarOrdenTrabajoTemp = limpiarLocalStorage;

})();
