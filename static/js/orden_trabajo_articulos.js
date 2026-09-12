// Nueva UI profesional para artículos OT
function initArticulos() {
	console.log('=== INICIANDO ORDEN_TRABAJO_ARTICULOS ===');
	// Escape HTML defensivo para datos del servidor/usuario (XSS)
	function esc(s) {
		return String(s === null || s === undefined ? '' : s)
			.replace(/[&<>"']/g, function (c) {
				return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
			});
	}
	let articulos = [];
	let editIdx = null;
	let productosArticulo = []; // Productos del artículo actual

	const lista = document.getElementById('articulos-lista');
	const totalSpan = document.getElementById('articulos-total');
	const btnAgregar = document.getElementById('btn-agregar-articulo');
	const modalEl = document.getElementById('modalArticulo');
	let modal = null;

	if (window.bootstrap && modalEl) {
		// Configurar el modal para prevenir cierre por backdrop y teclado
		modal = new bootstrap.Modal(modalEl, {
			backdrop: 'static',
			keyboard: false
		});
		console.log('Modal configurado correctamente');
	}

	const form = document.getElementById('form-articulo');
	const btnAgregarAlCarrito = document.getElementById('btn-agregar-al-carrito');

	console.log('Elementos encontrados:', {
		lista, totalSpan, btnAgregar, modalEl, form, btnAgregarAlCarrito
	});

	// Configurar event listeners cuando se abre el modal
	if (modalEl) {
		modalEl.addEventListener('shown.bs.modal', function() {
			console.log('=== MODAL ABIERTO - CONFIGURANDO BUSCADOR ===');
			setupProductSearch();
			
			// Enfocar automáticamente el campo SKU
			setTimeout(() => {
				const skuInput = document.getElementById('producto-sku');
				if (skuInput) {
					skuInput.focus();
					console.log('✅ Campo SKU enfocado automáticamente');
				}
			}, 150);
		});

		// Interceptar clic en el backdrop
		modalEl.addEventListener('click', function(e) {
			if (e.target === modalEl) {
				console.log('Previniendo clic en backdrop');
				e.preventDefault();
				e.stopPropagation();
				return false;
			}
		});

		modalEl.addEventListener('hide.bs.modal', function(e) {
			const cancelButton = document.getElementById('btn-cancelar-articulo');
			const isFromCancelButton = e.relatedTarget === cancelButton;

			console.log('Intentando cerrar modal:', { relatedTarget: e.relatedTarget, cancelButton, isFromCancelButton });

			if (!isFromCancelButton) {
				console.log('Previniendo cierre - solo botón cancelar permitido');
				e.preventDefault();
				e.stopPropagation();
				return false;
			}
		});

		// Remover data-bs-dismiss del botón X
		const btnCerrar = modalEl.querySelector('.btn-close');
		if (btnCerrar) {
			btnCerrar.removeAttribute('data-bs-dismiss');
			btnCerrar.addEventListener('click', function(e) {
				console.log('Previniendo clic en botón X');
				e.preventDefault();
				e.stopPropagation();
			});
		}
	}

	// Interceptar Escape
	document.addEventListener('keydown', function(e) {
		if (e.key === 'Escape' && modal && modal._isShown) {
			console.log('Previniendo Escape');
			e.preventDefault();
			e.stopPropagation();
		}
	});	// Función para actualizar indicador visual de datos sin guardar
	function actualizarIndicadorDatos() {
		const header = modalEl.querySelector('.modal-header');
		let indicador = header.querySelector('.datos-sin-guardar');
		
		if (tieneDatosSinGuardar()) {
			if (!indicador) {
				indicador = document.createElement('span');
				indicador.className = 'datos-sin-guardar badge bg-warning text-dark ms-2';
				indicador.textContent = 'Datos sin guardar';
				header.querySelector('.modal-title').appendChild(indicador);
			}
		} else {
			if (indicador) {
				indicador.remove();
			}
		}
	}

	// Actualizar indicador cuando cambien los campos
	const camposParaMonitorear = [
		form['tipo'], form['marca'], form['referencia'], form['descripcion'],
		document.getElementById('producto-sku'), 
		document.getElementById('producto-precio'),
		document.getElementById('producto-cantidad'),
		document.getElementById('producto-descuento')
	];

	camposParaMonitorear.forEach(campo => {
		if (campo) {
			campo.addEventListener('input', actualizarIndicadorDatos);
			campo.addEventListener('change', actualizarIndicadorDatos);
		}
	});

	function renderProductosArticulo() {
		const listaProductos = document.getElementById('productos-articulo-lista');
		const totalSpan = document.getElementById('productos-articulo-total');
		const valorArticulo = document.getElementById('valor-articulo');
		
		if (!listaProductos) {
			console.error('❌ Elemento productos-articulo-lista no encontrado');
			return;
		}
		
		listaProductos.innerHTML = '';
		let total = 0;
		
		if (productosArticulo.length === 0) {
			listaProductos.innerHTML = '<div class="text-muted small text-center py-2"><i class="bi bi-cart-x"></i> No hay productos agregados aún</div>';
		} else {
			productosArticulo.forEach((prod, idx) => {
				const precioUnitario = prod.precio;
				const subtotalSinDescuento = prod.cantidad * precioUnitario;
				const descuentoMonto = subtotalSinDescuento * (prod.descuento / 100);
				const subtotal = subtotalSinDescuento - descuentoMonto;
				total += subtotal;
				
				const descuentoTexto = prod.descuento > 0 ? ` <span class="badge bg-warning text-dark">-${prod.descuento}%</span>` : '';
				
				const div = document.createElement('div');
				div.className = 'd-flex justify-content-between align-items-center border-bottom py-2 hover-bg-light';
				div.innerHTML = `
					<div class="flex-grow-1">
						<div class="d-flex align-items-center">
							<strong class="me-2"><i class="bi bi-box"></i> ${esc(prod.sku) || 'Sin SKU'}</strong> 
							<span class="badge bg-secondary">${prod.cantidad}x</span>
							${descuentoTexto}
						</div>
						<small class="text-muted">
							$${precioUnitario.toLocaleString()} c/u
							${prod.descuento > 0 ? ` → <del>$${subtotalSinDescuento.toLocaleString()}</del> <strong class="text-success">$${Math.round(subtotal).toLocaleString()}</strong>` : ` = <strong>$${Math.round(subtotal).toLocaleString()}</strong>`}
						</small>
					</div>
					<div class="d-flex align-items-center gap-2">
						<span class="fw-bold text-success fs-6">$${Math.round(subtotal).toLocaleString()}</span>
						<button type="button" class="btn btn-sm btn-outline-danger" onclick="window.eliminarProductoArticulo(${idx})" title="Eliminar producto">
							<i class="bi bi-trash"></i>
						</button>
					</div>
				`;
				listaProductos.appendChild(div);
			});
		}
		
		const totalFormateado = Math.round(total).toLocaleString();
		if (totalSpan) totalSpan.textContent = totalFormateado;
		if (valorArticulo) valorArticulo.value = Math.round(total);
		
		console.log('📦 Productos renderizados:', productosArticulo.length, '| Total: $' + totalFormateado);
		
		// Actualizar indicador visual
		actualizarIndicadorDatos();
	}

	// Funciones para autocompletado de productos (igual que en POS)
	async function buscarProductos(term) {
		const sugerenciasDiv = document.getElementById('productos-sugerencias');
		if (term.length < 1) {
			if (sugerenciasDiv) sugerenciasDiv.style.display = 'none';
			return;
		}

		try {
			console.log('🔍 Buscando productos con term:', term);
			console.log('📡 URL:', '/products/buscar');
			console.log('📦 Payload:', { query: term });
			
			// GET (el endpoint tambien acepta POST, pero GET evita CSRF)
			const response = await fetch('/products/buscar?q=' + encodeURIComponent(term), {
				method: 'GET',
				headers: {
					'Accept': 'application/json',
				},
				credentials: 'include'
			});

			console.log('📊 Response status:', response.status, response.statusText);
			
			if (!response.ok) {
				const errorText = await response.text();
				console.error('❌ Error en respuesta:', response.status, errorText);
				throw new Error(`HTTP ${response.status}: ${errorText}`);
			}

			const data = await response.json();
			console.log('📦 Data recibida:', data);
			
			const productos = data.productos || data || [];
			console.log('✅ Productos encontrados:', productos.length, productos);
			mostrarResultados(productos);
		} catch (error) {
			console.error('❌ Error buscando productos:', error);
			console.error('Stack trace:', error.stack);
			if (sugerenciasDiv) {
				sugerenciasDiv.innerHTML = '<div class="alert alert-danger m-2 p-2 small">Error al buscar: ' + esc(error.message) + '</div>';
				sugerenciasDiv.style.display = 'block';
			}
		}
	}

	function mostrarResultados(productos) {
		const sugerenciasDiv = document.getElementById('productos-sugerencias');
		if (!sugerenciasDiv) {
			console.error('❌ Elemento productos-sugerencias no encontrado');
			return;
		}

		console.log('📋 Mostrando resultados:', productos.length, 'productos');

		if (productos.length === 0) {
			sugerenciasDiv.innerHTML = '<div class="alert alert-info m-2 p-2 small">No se encontraron productos</div>';
			sugerenciasDiv.style.display = 'block';
			return;
		}

		sugerenciasDiv.innerHTML = '';

		const lista = document.createElement('ul');
		lista.className = 'list-group';
		lista.style.cssText = 'position: static; max-height: 200px; overflow-y: auto; margin: 0;';

		productos.forEach((producto, index) => {
			const li = document.createElement('li');
			li.className = 'list-group-item list-group-item-action';
			li.style.cursor = 'pointer';
			li.dataset.index = index;

			// Formato igual que en POS: nombre (SKU) $precio
			const nombre = producto.nombre || producto.label || '';
			const sku = producto.sku || '';
			const precio = producto.precio ? `$${Math.round(parseFloat(producto.precio))}` : '';
			li.textContent = `${nombre} ${sku ? '(' + sku + ')' : ''} ${precio}`.trim();
			li.tabIndex = 0;

			li.addEventListener('mousedown', function(e) {
				e.preventDefault();
				console.log('🖱️ Producto seleccionado:', producto);
				seleccionarProducto(producto);
				sugerenciasDiv.style.display = 'none';
			});

			lista.appendChild(li);
		});

		sugerenciasDiv.appendChild(lista);
		sugerenciasDiv.style.display = 'block';

		console.log('✅ Sugerencias mostradas:', productos.length, 'productos');
	}

	function seleccionarProducto(producto) {
		const skuInput = document.getElementById('producto-sku');
		const precioInput = document.getElementById('producto-precio');

		if (skuInput) {
			// Mostrar SKU en el input
			skuInput.value = producto.sku || producto.label || '';
		}
		if (precioInput) {
			precioInput.value = Math.round(parseFloat(producto.precio || 0));
		}

		// Reset descuento y cantidad
		const descuentoInput = document.getElementById('producto-descuento');
		const cantidadInput = document.getElementById('producto-cantidad');
		if (descuentoInput) descuentoInput.value = 0;
		if (cantidadInput) cantidadInput.value = 1;

		// Enfocar cantidad (igual que en POS)
		setTimeout(() => {
			if (cantidadInput) {
				cantidadInput.focus();
				cantidadInput.select();
			}
		}, 0);
	}

	function ocultarSugerencias() {
		setTimeout(() => {
			sugerenciasDiv.style.display = 'none';
		}, 150);
	}

	// Función para verificar si hay datos sin guardar
	function tieneDatosSinGuardar() {
		// Verificar campos del formulario principal
		const tipo = form['tipo'].value;
		const marca = form['marca'].value;
		const referencia = form['referencia'].value;
		const descripcion = form['descripcion'].value;
		
		// Verificar productos agregados al artículo
		const tieneProductos = productosArticulo.length > 0;
		
		// Verificar campos del formulario de producto (datos sin agregar al carrito)
		const skuProducto = document.getElementById('producto-sku').value.trim();
		const precioProducto = document.getElementById('producto-precio').value.trim();
		const cantidadProducto = document.getElementById('producto-cantidad').value.trim();
		const descuentoProducto = document.getElementById('producto-descuento').value.trim();
		
		// Considerar que hay datos si hay algo escrito en los campos de producto
		const tieneDatosProductoPendientes = skuProducto || precioProducto || 
			(cantidadProducto && cantidadProducto !== '1') || 
			(descuentoProducto && descuentoProducto !== '0');
		
		return tipo || marca || referencia || descripcion || tieneProductos || tieneDatosProductoPendientes;
	}

	// Función para confirmar cierre del modal
	function confirmarCierreModal() {
		if (tieneDatosSinGuardar()) {
			return confirm('¿Estás seguro de cerrar? Se perderán los datos no guardados.');
		}
		return true;
	}

	function renderArticulos() {
		lista.innerHTML = '';
		let total = 0;
		if (articulos.length === 0) {
			lista.innerHTML = `<tr><td colspan="8" class="text-center text-muted">No hay artículos agregados.</td></tr>`;
		} else {
			articulos.forEach((art, idx) => {
				total += Number(art.valor) || 0;
				let descripcionDisplay = art.descripcion || '-';
				
				// Agregar características si es un reloj
				if (art.tipo === 'reloj' && art.caracteristicas && art.caracteristicas.length > 0) {
					descripcionDisplay += ` (${art.caracteristicas.join(', ')})`;
				}
				
				// Mostrar productos del artículo
				let productosDisplay = '-';
				if (art.productos && art.productos.length > 0) {
					productosDisplay = art.productos.map(p => `${p.sku} (${p.cantidad}x)`).join(', ');
				}
				
			const row = document.createElement('tr');
			row.innerHTML = `
				<td><span class="badge bg-secondary">${idx + 1}</span></td>
				<td><i class="bi bi-box"></i> <span class="fw-bold">${esc(art.tipo)}</span></td>
				<td><span class="badge bg-info text-dark">${esc(art.marca)}</span></td>
				<td><span class="badge bg-light text-dark">${esc(art.referencia)}</span></td>
				<td>${esc(descripcionDisplay)}</td>
				<td><small>${esc(productosDisplay)}</small></td>
					<td class="text-end fw-bold text-success">$${art.valor || 0}</td>
					<td class="text-center">
						<div class="btn-group" role="group">
							<button type="button" class="btn btn-sm btn-primary" title="Editar artículo y productos" onclick="window.editarArticulo(${idx})">
								<i class="bi bi-pencil"></i> Editar
							</button>
							<button type="button" class="btn btn-sm btn-danger" title="Eliminar artículo" onclick="window.confirmarEliminarArticulo(${idx})">
								<i class="bi bi-trash"></i>
							</button>
						</div>
					</td>
				`;
				lista.appendChild(row);
			});
		}
		totalSpan.textContent = total;
		const jsonString = JSON.stringify(articulos);
		const articulosJsonInput = document.getElementById('articulos-json');
		if (articulosJsonInput) articulosJsonInput.value = jsonString;
	}

	window.eliminarProductoArticulo = function(idx) {
		productosArticulo.splice(idx, 1);
		renderProductosArticulo();
	};

	window.editarArticulo = function(idx) {
		const art = articulos[idx];
		form['tipo'].value = art.tipo;
		form['marca'].value = art.marca;
		form['referencia'].value = art.referencia;
		form['descripcion'].value = art.descripcion;
		form['articulo_idx'].value = idx;
		editIdx = idx;
		
		// Cambiar título del modal para indicar que se está editando
		const modalTitle = document.getElementById('modalArticuloLabel');
		if (modalTitle) {
			const tipoArticulo = art.tipo || 'artículo';
			const marcaReferencia = `${art.marca || ''} ${art.referencia || ''}`.trim();
			const descripcion = marcaReferencia ? ` - ${marcaReferencia}` : '';
			modalTitle.innerHTML = `<i class="bi bi-pencil-square"></i> Editar ${tipoArticulo}${descripcion}`;
		}
		
		// Cargar productos del artículo
		productosArticulo = art.productos ? [...art.productos] : [];
		renderProductosArticulo();
		
		// Limpiar campos del formulario de producto
		document.getElementById('producto-sku').value = '';
		document.getElementById('producto-cantidad').value = '1';
		document.getElementById('producto-descuento').value = '0';
		document.getElementById('producto-precio').value = '';
		
		// Limpiar todos los campos de características
		document.querySelectorAll('input[name="caracteristicas"]').forEach(cb => cb.checked = false);
		document.querySelectorAll('input[name="tapa_tipo"]').forEach(rb => rb.checked = false);
		document.querySelectorAll('input[name="garantia"]').forEach(rb => rb.checked = false);
		document.querySelectorAll('input[name="bateria_aplicacion"]').forEach(rb => rb.checked = false);
		document.getElementById('eslabones_numero').value = '';
		document.getElementById('bateria_voltaje').value = '';
		document.getElementById('bateria_amperaje').value = '';
		document.getElementById('bateria_celdas').value = '';
		
		// Restaurar características si existen
		if (art.caracteristicas && Array.isArray(art.caracteristicas)) {
			art.caracteristicas.forEach(caracteristica => {
				// Buscar checkboxes por valor exacto
				const checkbox = document.querySelector(`input[name="caracteristicas"][value="${caracteristica}"]`);
				if (checkbox) {
					checkbox.checked = true;
				}
				
				// Manejar campos especiales
				if (caracteristica.startsWith('Eslabones: ')) {
					const numero = caracteristica.replace('Eslabones: ', '');
					document.getElementById('eslabones_numero').value = numero;
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
					const valor = caracteristica.replace('Voltaje: ', '');
					document.getElementById('bateria_voltaje').value = valor;
				}
				else if (caracteristica.startsWith('Amperaje: ')) {
					const valor = caracteristica.replace('Amperaje: ', '');
					document.getElementById('bateria_amperaje').value = valor;
				}
				else if (caracteristica.startsWith('Celdas: ')) {
					const valor = caracteristica.replace('Celdas: ', '');
					document.getElementById('bateria_celdas').value = valor;
				}
				else if (caracteristica.startsWith('Aplicación: ')) {
					const tipo = caracteristica.replace('Aplicación: ', '');
					const radio = document.querySelector(`input[name="bateria_aplicacion"][value="${tipo}"]`);
					if (radio) radio.checked = true;
				}
			});
		}
		
		modal.show();
	};

	window.eliminarArticulo = function(idx) {
		articulos.splice(idx, 1);
		renderArticulos();
	};

	window.confirmarEliminarArticulo = function(idx) {
		const articulo = articulos[idx];
		const tipoArticulo = articulo.tipo || 'artículo';
		const marcaReferencia = `${articulo.marca || ''} ${articulo.referencia || ''}`.trim();
		const descripcion = marcaReferencia ? ` (${marcaReferencia})` : '';
		
		if (confirm(`¿Estás seguro de eliminar este ${tipoArticulo}${descripcion}?\n\nEsta acción no se puede deshacer.`)) {
			window.eliminarArticulo(idx);
		}
	};

	if (!btnAgregar) {
		console.warn('btn-agregar-articulo not found');
	} else {
		btnAgregar.addEventListener('click', function() {
			form.reset();
			form['articulo_idx'].value = '';
			editIdx = null;
			
			// Restaurar título original del modal
			const modalTitle = document.getElementById('modalArticuloLabel');
			if (modalTitle) {
				modalTitle.innerHTML = '<i class="bi bi-box-seam"></i> Agregar/Editar Artículo';
			}
			
			// Limpiar productos del artículo
			productosArticulo = [];
			renderProductosArticulo();
			
			// Limpiar campos del formulario de producto
			document.getElementById('producto-sku').value = '';
			document.getElementById('producto-cantidad').value = '1';
			document.getElementById('producto-descuento').value = '0';
			document.getElementById('producto-precio').value = '';
			
			// Limpiar todos los campos de características
			document.querySelectorAll('input[name="caracteristicas"]').forEach(cb => cb.checked = false);
			document.querySelectorAll('input[name="tapa_tipo"]').forEach(rb => rb.checked = false);
			document.querySelectorAll('input[name="garantia"]').forEach(rb => rb.checked = false);
			document.querySelectorAll('input[name="bateria_aplicacion"]').forEach(rb => rb.checked = false);
			document.getElementById('eslabones_numero').value = '';
			document.getElementById('bateria_voltaje').value = '';
			document.getElementById('bateria_amperaje').value = '';
			document.getElementById('bateria_celdas').value = '';
			
				try {
					if (!modal && window.bootstrap && modalEl) modal = bootstrap.Modal.getOrCreateInstance(modalEl);
					modal?.show();
					// Inicializar indicador cuando se abre el modal
					setTimeout(actualizarIndicadorDatos, 100);
				} catch (err) {
					console.error('Error showing modal:', err);
					// Create a new instance if something's wrong and try again
					if (window.bootstrap && modalEl) {
						const newModal = new bootstrap.Modal(modalEl);
						newModal.show();
						modal = newModal;
						setTimeout(actualizarIndicadorDatos, 100);
					}
				}
		});
	}
	
	// Manejar cambio de tipo de artículo
	form['tipo'].addEventListener('change', function() {
		const tipo = this.value;
		const relojCaracteristicas = document.getElementById('check_list_reloj');
		const bateriaCaracteristicas = document.getElementById('check_list_bateria');
		const electronicoCaracteristicas = document.getElementById('check_list_electronico');
		
		// Ocultar todas las características primero
		if (relojCaracteristicas) relojCaracteristicas.style.display = 'none';
		if (bateriaCaracteristicas) bateriaCaracteristicas.style.display = 'none';
		if (electronicoCaracteristicas) electronicoCaracteristicas.style.display = 'none';
		
		// Mostrar características según el tipo seleccionado
		if (tipo === 'reloj') {
			if (relojCaracteristicas) relojCaracteristicas.style.display = 'block';
		} else if (tipo === 'bateria') {
			if (bateriaCaracteristicas) bateriaCaracteristicas.style.display = 'block';
		} else if (tipo === 'electronico') {
			if (electronicoCaracteristicas) electronicoCaracteristicas.style.display = 'block';
		}
	});
	
	form.addEventListener('submit', function(e) {
		e.preventDefault();
		
		// Recopilar todas las características seleccionadas desde el MODAL específico
		const modalArticulo = document.getElementById('modalArticulo');
		const caracteristicasChecks = Array.from(modalArticulo.querySelectorAll('input[name="caracteristicas"]:checked')).map(i => i.value.trim());
		
		// Recopilar campos adicionales
		const eslabones = (document.getElementById('eslabones_numero') && document.getElementById('eslabones_numero').value) 
			? `Eslabones: ${document.getElementById('eslabones_numero').value.trim()}` : null;
		
		const tapaTipo = (modalArticulo.querySelector('input[name="tapa_tipo"]:checked')) 
			? `Reloj: ${modalArticulo.querySelector('input[name="tapa_tipo"]:checked').value}` : null;
		
		const garantia = (modalArticulo.querySelector('input[name="garantia"]:checked')) 
			? `Garantía: ${modalArticulo.querySelector('input[name="garantia"]:checked').value}` : null;
		
		// Recopilar datos de batería
		const bateriaVoltaje = (document.getElementById('bateria_voltaje') && document.getElementById('bateria_voltaje').value)
			? `Voltaje: ${document.getElementById('bateria_voltaje').value.trim()}` : null;
		
		const bateriaAmperaje = (document.getElementById('bateria_amperaje') && document.getElementById('bateria_amperaje').value)
			? `Amperaje: ${document.getElementById('bateria_amperaje').value.trim()}` : null;
		
		const bateriaCeldas = (document.getElementById('bateria_celdas') && document.getElementById('bateria_celdas').value)
			? `Celdas: ${document.getElementById('bateria_celdas').value.trim()}` : null;
		
		const bateriaAplicacion = (document.querySelector('input[name="bateria_aplicacion"]:checked'))
			? `Aplicación: ${document.querySelector('input[name="bateria_aplicacion"]:checked').value}` : null;
		
		// Combinar todas las características
		const todasCaracteristicas = [];
		todasCaracteristicas.push(...caracteristicasChecks);
		if(eslabones) todasCaracteristicas.push(eslabones);
		if(tapaTipo) todasCaracteristicas.push(tapaTipo);
		if(garantia) todasCaracteristicas.push(garantia);
		if(bateriaVoltaje) todasCaracteristicas.push(bateriaVoltaje);
		if(bateriaAmperaje) todasCaracteristicas.push(bateriaAmperaje);
		if(bateriaCeldas) todasCaracteristicas.push(bateriaCeldas);
		if(bateriaAplicacion) todasCaracteristicas.push(bateriaAplicacion);
		
		const art = {
			tipo: form['tipo'].value,
			marca: form['marca'].value,
			referencia: form['referencia'].value,
			descripcion: form['descripcion'].value,
			productos: [...productosArticulo],
			valor: document.getElementById('valor-articulo').value || 0,
			caracteristicas: todasCaracteristicas
		};
		
		const idx = form['articulo_idx'].value;
		if (idx === '' || isNaN(idx)) {
			articulos.push(art);
		} else {
			articulos[idx] = art;
		}
		
		// Limpiar solo el índice de edición y productos
		form['articulo_idx'].value = '';
		productosArticulo = [];
		renderProductosArticulo();
		
		// Cerrar modal
		modal.hide();
		renderArticulos();
	});
	
	// Función para configurar la búsqueda de productos (se ejecuta cuando se abre el modal)
	function setupProductSearch() {
		console.log('=== SETUP PRODUCT SEARCH START ===');

		const skuInput = document.getElementById('producto-sku');
		const sugerenciasDiv = document.getElementById('productos-sugerencias');
		const cantidadInput = document.getElementById('producto-cantidad');
		const descuentoInput = document.getElementById('producto-descuento');
		const precioInput = document.getElementById('producto-precio');
		const btnAgregar = document.getElementById('btn-agregar-al-carrito');

		console.log('Elementos encontrados en setupProductSearch:', {
			skuInput,
			sugerenciasDiv,
			cantidadInput,
			descuentoInput,
			precioInput,
			btnAgregar
		});

		if (!skuInput) {
			console.error('❌ SKU input no encontrado en el modal');
			return;
		}

		console.log('✅ Configurando event listeners para SKU input');

		// Configurar botón agregar al carrito
		if (btnAgregar) {
			// Remover listeners previos
			const newBtn = btnAgregar.cloneNode(true);
			btnAgregar.parentNode.replaceChild(newBtn, btnAgregar);
			
			newBtn.addEventListener('click', function(e) {
				console.log('🛒 Click en botón agregar al carrito');
				e.preventDefault();
				agregarProductoAlCarrito();
			});
			console.log('✅ Event listener configurado para botón agregar al carrito');
		} else {
			console.error('❌ Botón agregar al carrito no encontrado');
		}

		let timeoutId;

		// Configurar búsqueda en tiempo real
		skuInput.addEventListener('input', function() {
			console.log('📝 Input event en SKU, valor:', this.value);
			clearTimeout(timeoutId);
			const term = this.value.trim();

			if (term.length >= 1) {  // Buscar desde 1 carácter como en POS
				console.log('🔍 Buscando productos con term:', term);
				timeoutId = setTimeout(() => buscarProductos(term), 300);
			} else {
				if (sugerenciasDiv) sugerenciasDiv.style.display = 'none';
			}
		});

		skuInput.addEventListener('blur', ocultarSugerencias);

		// Enter inteligente: si hay resultados selecciona el primero, si no pasa a cantidad
		skuInput.addEventListener('keydown', function(e) {
			console.log('⌨️ Keydown en SKU:', e.key);
			
			// Navegación con flechas en sugerencias
			if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
				const lista = sugerenciasDiv?.querySelector('ul.list-group');
				if (lista && lista.children.length > 0) {
					e.preventDefault();
					const items = Array.from(lista.children);
					const currentIndex = items.findIndex(item => item.classList.contains('active'));
					
					// Remover active de todos
					items.forEach(item => item.classList.remove('active', 'bg-primary', 'text-white'));
					
					let newIndex;
					if (e.key === 'ArrowDown') {
						newIndex = currentIndex < items.length - 1 ? currentIndex + 1 : 0;
					} else {
						newIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1;
					}
					
					items[newIndex].classList.add('active', 'bg-primary', 'text-white');
					items[newIndex].scrollIntoView({ block: 'nearest' });
				}
				return;
			}
			
			if (e.key === 'Enter') {
				e.preventDefault();
				const lista = sugerenciasDiv?.querySelector('ul.list-group');
				
				if (lista && lista.children.length > 0) {
					// Buscar item activo o usar el primero
					const activeItem = lista.querySelector('li.active');
					const targetItem = activeItem || lista.children[0];
					
					if (targetItem) {
						console.log('🎯 Seleccionando resultado');
						targetItem.dispatchEvent(new MouseEvent('mousedown'));
					}
				} else {
					// Si no hay resultados, pasar a cantidad
					console.log('➡️ Pasando a cantidad');
					if (cantidadInput) {
						cantidadInput.focus();
						cantidadInput.select();
					}
				}
			}
		});

		// Secuencia de foco con Enter (igual que en POS)
		if (cantidadInput) {
			cantidadInput.addEventListener('keydown', function(e) {
				if (e.key === 'Enter') {
					e.preventDefault();
					if (descuentoInput) {
						descuentoInput.focus();
						descuentoInput.select();
					}
				}
			});
		}

		if (descuentoInput) {
			descuentoInput.addEventListener('keydown', function(e) {
				if (e.key === 'Enter') {
					e.preventDefault();
					if (precioInput) {
						precioInput.focus();
						precioInput.select();
					}
				}
			});
		}

		// Permitir agregar producto con Enter en el campo precio
		if (precioInput) {
			precioInput.addEventListener('keydown', function(e) {
				if (e.key === 'Enter') {
					e.preventDefault();
					agregarProductoAlCarrito();
				}
			});
		}

		console.log('=== SETUP PRODUCT SEARCH COMPLETE ===');
	}

	function agregarProductoAlCarrito() {
		console.log('🛒 Agregando producto al carrito');
		
		const skuInput = document.getElementById('producto-sku');
		const cantidadInput = document.getElementById('producto-cantidad');
		const descuentoInput = document.getElementById('producto-descuento');
		const precioInput = document.getElementById('producto-precio');
		
		const sku = skuInput.value.trim();
		const cantidad = parseInt(cantidadInput.value) || 1;
		const descuento = parseFloat(descuentoInput.value) || 0;
		const precio = parseFloat(precioInput.value) || 0;
		
		if (!sku) {
			alert('Por favor ingrese el nombre o SKU del producto');
			skuInput.focus();
			return;
		}
		
		if (precio <= 0) {
			alert('Por favor ingrese un precio válido');
			precioInput.focus();
			return;
		}
		
		if (cantidad <= 0) {
			alert('La cantidad debe ser mayor a 0');
			cantidadInput.focus();
			return;
		}
		
		const producto = {
			sku: sku,
			cantidad: cantidad,
			descuento: descuento,
			precio: precio
		};
		
		console.log('✅ Producto agregado:', producto);
		productosArticulo.push(producto);
		renderProductosArticulo();
		
		// Limpiar campos después de agregar
		skuInput.value = '';
		cantidadInput.value = '1';
		descuentoInput.value = '0';
		precioInput.value = '';
		
		// Enfocar el campo SKU para agregar el siguiente producto
		skuInput.focus();
		
		console.log('📦 Total productos en carrito:', productosArticulo.length);
	}

	renderArticulos();
}

function startInitWhenReady() {
	if (window.bootstrap && window.bootstrap.Modal) {
		initArticulos();
		return;
	}
	// Wait for load event or poll until bootstrap is available
	if (document.readyState === 'complete') {
		// Window already loaded; attempt to init
		initArticulos();
		return;
	}
	window.addEventListener('load', () => initArticulos());
	// Fallback polling (in case 'load' already fired before this code runs)
	let attempts = 0;
	const poll = setInterval(() => {
		attempts += 1;
		if (window.bootstrap && window.bootstrap.Modal) {
			clearInterval(poll);
			initArticulos();
		} else if (attempts > 50) { // stop after ~5 seconds
			clearInterval(poll);
			console.warn('Bootstrap not available; order UI not initialised');
		}
	}, 100);
}

document.addEventListener('DOMContentLoaded', startInitWhenReady);
