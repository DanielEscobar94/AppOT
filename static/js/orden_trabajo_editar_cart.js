// JS independiente para editar orden de trabajo
// Basado en orden_trabajo_producto_cart.js pero adaptado para editar con anticipos

document.addEventListener("DOMContentLoaded", function() {
  // Escape HTML defensivo para datos del servidor/usuario (XSS)
  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
  }
  // Start contador from server-provided INITIAL_CART_COUNT when editing, otherwise 0
  let contador = (window.INITIAL_CART_COUNT !== undefined) ? parseInt(window.INITIAL_CART_COUNT, 10) || 0 : 0;
  const CART_STORAGE_KEY = "ot_cart";
  const inputProducto = document.getElementById("buscar-producto");
  const btnAgregar = document.getElementById("btn-agregar-carrito");
  const cantidadInput = document.getElementById("producto-cantidad");
  const precioInput = document.getElementById("producto-precio");
  const productoIdInput = document.getElementById("producto-id");
  const carritoDiv = document.getElementById("carrito-productos");
  const totalDiv = document.getElementById("total-productos");
  const form = document.querySelector("form[action]");

  // If the essential elements for product search/cart are missing, bail out early.
  // This avoids runtime errors on pages that include this script but not the cart UI.
  if (!inputProducto || !cantidadInput || !precioInput || !productoIdInput || !btnAgregar || !carritoDiv || !form) {
    try { if (cantidadInput) cantidadInput.value = ""; } catch (e) {}
    return;
  }

  cantidadInput.value = "";

  const FORM_STORAGE_KEY = 'ot_form';

  function persistForm() {
    try {
      const payload = {
        client_id: (document.getElementById('client-id') && document.getElementById('client-id').value) || '',
        branch_id: (document.getElementById('branch-id') && document.getElementById('branch-id').value) || '',
        categoria: (document.getElementById('categoria') && document.getElementById('categoria').value) || '',
        marca: (document.getElementById('marca') && document.getElementById('marca').value) || '',
        referencia: (document.getElementById('referencia') && document.getElementById('referencia').value) || '',
        descripcion: (document.getElementById('descripcion') && document.getElementById('descripcion').value) || '',
        tecnico_id: (document.getElementById('tecnico_id') && document.getElementById('tecnico_id').value) || ''
      };
      localStorage.setItem(FORM_STORAGE_KEY, JSON.stringify(payload));
    } catch (e) { /* noop */ }
  }

  function restoreForm() {
    try {
      // do not restore if server already populated (editing case)
      const existingClient = document.getElementById('client-id') && document.getElementById('client-id').value;
      if (existingClient) return;
      const raw = localStorage.getItem(FORM_STORAGE_KEY);
      if (!raw) return;
      const obj = JSON.parse(raw);
      if (!obj) return;
      if (obj.client_id) document.getElementById('client-id').value = obj.client_id;
      if (obj.branch_id && document.getElementById('branch-id')) document.getElementById('branch-id').value = obj.branch_id;
      if (obj.categoria && document.getElementById('categoria')) document.getElementById('categoria').value = obj.categoria;
  // estado_equipo removed from UI: do not attempt to restore it
      if (obj.marca && document.getElementById('marca')) document.getElementById('marca').value = obj.marca;
      if (obj.referencia && document.getElementById('referencia')) document.getElementById('referencia').value = obj.referencia;
      if (obj.descripcion && document.getElementById('descripcion')) document.getElementById('descripcion').value = obj.descripcion;
      if (obj.tecnico_id && document.getElementById('tecnico_id')) document.getElementById('tecnico_id').value = obj.tecnico_id;
    } catch (e) { /* noop */ }
  }

  function crearHidden(name, value) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    return input;
  }

  function actualizarTotal() {
    let total = 0;
    document.querySelectorAll('.tarjeta-producto').forEach(tarjeta => {
      total += (parseInt(tarjeta.dataset.cantidad) || 0) * (parseInt(tarjeta.dataset.precio) || 0);
    });

    // Anticipo: sumar todas las tarjetas de anticipo
    let anticipoVal = 0;
    document.querySelectorAll('.tarjeta-anticipo').forEach(card => {
      anticipoVal += Math.round(parseFloat(card.dataset.monto) || 0);
    });

    const saldo = Math.max(0, Math.round(total) - Math.round(anticipoVal));

    // Formatear números con separadores de miles
    const totalFormateado = typeof formatearNumero === 'function' ? formatearNumero(total) : total.toLocaleString('es-CO');
    const anticipoFormateado = typeof formatearNumero === 'function' ? formatearNumero(anticipoVal) : anticipoVal.toLocaleString('es-CO');
    const saldoFormateado = typeof formatearNumero === 'function' ? formatearNumero(saldo) : saldo.toLocaleString('es-CO');

    // Update UI: total productos, total anticipos y saldo
    if (totalDiv) {
      totalDiv.textContent = `Total $${totalFormateado}`;
      // ensure elements for anticipos and saldo exist
      let ta = document.getElementById('total-anticipos');
      if (!ta) {
        ta = document.createElement('div'); ta.id = 'total-anticipos'; ta.className = 'fw-bold mt-1'; totalDiv.insertAdjacentElement('afterend', ta);
      }
      ta.textContent = `Anticipo $${anticipoFormateado}`;
      let sd = document.getElementById('saldo-orden');
      if (!sd) {
        sd = document.createElement('div'); sd.id = 'saldo-orden'; sd.className = 'fw-bold mt-1'; ta.insertAdjacentElement('afterend', sd);
      }
      sd.textContent = `Saldo $${saldoFormateado}`;
    }
  }

  // Exponer actualizarTotal globalmente
  window.actualizarTotal = actualizarTotal;

  function persistCart() {
    const items = [];
    document.querySelectorAll('.tarjeta-producto').forEach(tarjeta => {
      items.push({
        nombre: tarjeta.querySelector('strong')?.textContent || '',
        productoId: tarjeta.dataset.productoId || '',
        cantidad: parseInt(tarjeta.dataset.cantidad) || 0,
        precio: parseInt(tarjeta.dataset.precio) || 0
      });
    });
    try {
      localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(items));
    } catch (e) { /* noop */ }
  }

  function addCard(nombre, productoId, cantidad, precio) {
    const subtotal = cantidad * precio;
    const precioFormateado = typeof formatearNumero === 'function' ? formatearNumero(precio) : precio.toLocaleString('es-CO');
    const subtotalFormateado = typeof formatearNumero === 'function' ? formatearNumero(subtotal) : subtotal.toLocaleString('es-CO');
    
    const tarjeta = document.createElement("div");
    tarjeta.className = "tarjeta-producto mb-2 p-2 border rounded d-flex justify-content-between align-items-center";
    tarjeta.id = "tarjeta-producto-" + contador;
    tarjeta.dataset.cantidad = cantidad;
    tarjeta.dataset.precio = precio;
    tarjeta.dataset.productoId = productoId;
    tarjeta.dataset.index = contador;
    tarjeta.innerHTML = `
      <div style="flex-grow: 1; margin-right: 10px;">
        <input type="text" class="form-control form-control-sm mb-1 nombre-producto-editable" 
               value="${esc(nombre)}" data-index="${contador}" 
               placeholder="Nombre del producto" style="font-weight: bold;">
        <small class="detalle-subtotal">${cantidad} x $${precioFormateado} = $${subtotalFormateado}</small>
      </div>
      <div class="text-end">
        <label class="form-label mb-1">Cant</label>
        <input type="number" min="1" class="form-control form-control-sm input-cantidad-inline" value="${cantidad}" data-index="${contador}" style="width:80px; display:inline-block;">
  <button type="button" class="btn btn-sm btn-outline-danger ms-2" onclick="eliminarProducto(${contador})">Eliminar</button>
      </div>
    `;
    carritoDiv.appendChild(tarjeta);
    // Inputs ocultos con IDs para poder removerlos
    const hidProd = crearHidden(`producto_id_${contador}`, productoId);
    hidProd.id = `input-producto_id-${contador}`;
    const hidCant = crearHidden(`cantidad_${contador}`, cantidad);
    hidCant.id = `input-cantidad-${contador}`;
    const hidPrecio = crearHidden(`precio_unitario_${contador}`, precio);
    hidPrecio.id = `input-precio_unitario-${contador}`;
    const hidNombre = crearHidden(`nombre_producto_${contador}`, nombre);
    hidNombre.id = `input-nombre_producto-${contador}`;
    
    // Agregar listeners
    const nombreInput = tarjeta.querySelector('.nombre-producto-editable');
    nombreInput.addEventListener('input', function() {
      // Convertir a mayúsculas automáticamente
      this.value = this.value.toUpperCase();
      hidNombre.value = this.value;
      persistCart();
    });
    
    form.appendChild(hidProd);
    form.appendChild(hidCant);
    form.appendChild(hidPrecio);
    form.appendChild(hidNombre);
    
    // Attach change handler to inline quantity input
    const inlineQty = tarjeta.querySelector('.input-cantidad-inline');
    if (inlineQty) {
      inlineQty.addEventListener('input', function(e) {
        const idx = this.dataset.index;
        const newVal = Math.max(1, parseInt(this.value) || 1);
        // Update tarjeta dataset
        const tar = document.getElementById(`tarjeta-producto-${idx}`);
        if (tar) {
          tar.dataset.cantidad = newVal;
          const precioVal = parseFloat(tar.dataset.precio) || 0;
          const subtotal = Math.round(newVal * precioVal);
          const precioFormateado = typeof formatearNumero === 'function' ? formatearNumero(precioVal) : precioVal.toLocaleString('es-CO');
          const subtotalFormateado = typeof formatearNumero === 'function' ? formatearNumero(subtotal) : subtotal.toLocaleString('es-CO');
          const det = tar.querySelector('.detalle-subtotal');
          if (det) det.textContent = `${newVal} x $${precioFormateado} = $${subtotalFormateado}`;
        }
        // Update hidden input
        const hid = document.getElementById(`input-cantidad-${idx}`);
        if (hid) hid.value = newVal;
        actualizarTotal();
        persistCart();
      });
    }
    contador++;
    actualizarTotal();
    persistCart();
  }

  // Función para agregar anticipos nuevos (no existentes) al carrito
  function agregarAnticipoNuevo(monto, metodo) {
    const m = Math.round(parseFloat(monto) || 0);
    const tarjetaId = 'tarjeta-anticipo-new';
    let existing = document.getElementById(tarjetaId);
    if (existing) existing.remove();
    const carritoDivLocal = document.getElementById('carrito-productos');
    if (!carritoDivLocal) return;
    const tarjeta = document.createElement('div');
    tarjeta.className = 'tarjeta-anticipo mb-2 p-2 border rounded d-flex justify-content-between align-items-center bg-light';
    tarjeta.id = tarjetaId;
    tarjeta.dataset.monto = m;
    tarjeta.innerHTML = `
      <div>
        <strong>Anticipo</strong><br>
        <small class="detalle-subtotal">${m} — ${esc(metodo) || '—'}</small>
      </div>
      <div class="text-end">
        <button type="button" class="btn btn-sm btn-outline-danger btn-eliminar-anticipo-nuevo">Quitar</button>
      </div>
    `;
    carritoDivLocal.appendChild(tarjeta);

    // Handler para eliminar (solo UI, ya que no está en DB aún)
    const btn = tarjeta.querySelector('.btn-eliminar-anticipo-nuevo');
    if (btn) {
      btn.addEventListener('click', function(){
        if (confirm('Quitar anticipo?')) {
          tarjeta.remove();
          actualizarTotal();
        }
      });
    }
    actualizarTotal();
  }

  // Función específica para editar: agregar anticipos existentes al carrito
  function agregarAnticipoExistente(monto, metodo, anticipoId) {
    const m = Math.round(parseFloat(monto) || 0);
    const tarjetaId = 'tarjeta-anticipo-' + anticipoId;
    let existing = document.getElementById(tarjetaId);
    if (existing) existing.remove();
    const carritoDivLocal = document.getElementById('carrito-productos');
    if (!carritoDivLocal) return;
    const tarjeta = document.createElement('div');
    tarjeta.className = 'tarjeta-anticipo mb-2 p-2 border rounded d-flex justify-content-between align-items-center bg-light';
    tarjeta.id = tarjetaId;
    tarjeta.dataset.monto = m;
    tarjeta.innerHTML = `
      <div>
        <strong>Anticipo</strong><br>
        <small class="detalle-subtotal">${m} — ${esc(metodo) || '—'}</small>
      </div>
      <div class="text-end">
        <button type="button" class="btn btn-sm btn-outline-danger btn-eliminar-anticipo-existente" data-anticipo-id="${anticipoId}">Quitar</button>
      </div>
    `;
    carritoDivLocal.appendChild(tarjeta);

    // Handler para eliminar
    const btn = tarjeta.querySelector('.btn-eliminar-anticipo-existente');
    if (btn) {
      btn.addEventListener('click', function(){
        if (confirm('¿Eliminar este anticipo?')) {
          fetch('/anticipos/' + anticipoId + '/delete', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
          }).then(resp => {
            if (resp.ok) {
              tarjeta.remove();
              actualizarTotal();
              // Recargar página para actualizar la lista estática
              window.location.reload();
            } else {
              alert('Error eliminando anticipo');
            }
          }).catch(err => {
            console.error('Error eliminando anticipo', err);
            alert('Error eliminando anticipo');
          });
        }
      });
    }
    actualizarTotal();
  }

  // Exponer funciones globalmente
  window.agregarAnticipoNuevo = agregarAnticipoNuevo;
  window.agregarAnticipoExistente = agregarAnticipoExistente;

  function agregarAlCarrito() {
    const nombre = inputProducto.value.trim();
    const productoId = productoIdInput.value;
    const precioValue = precioInput.value;
    // Limpiar el precio: eliminar puntos y comas, convertir a número entero
    const precioLimpio = precioValue.toString().replace(/\./g, '').replace(/,/g, '');
    const precio = parseInt(precioLimpio) || 0;
    const cantidad = cantidadInput.value === "" ? 1 : parseInt(cantidadInput.value) || 0;
    if (!nombre || !productoId || cantidad <= 0 || precio <= 0) {
      alert("Completa los datos del producto antes de agregar.");
      return;
    }
    addCard(nombre, productoId, cantidad, precio);
    inputProducto.value = "";
    productoIdInput.value = "";
    precioInput.value = "";
    cantidadInput.value = "";
    btnAgregar.classList.add("d-none");
  }

  // Persist form on changes of inputs we care about
      ['client-id','branch-id','categoria','marca','referencia','descripcion','tecnico_id'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', persistForm);
    if (el) el.addEventListener('change', persistForm);
  });

  window.eliminarProducto = function(index) {
    const tarjeta = document.getElementById("tarjeta-producto-" + index);
    if (tarjeta) tarjeta.remove();
    // Remover inputs ocultos asociados
    const hidProd = document.getElementById(`input-producto_id-${index}`);
    const hidCant = document.getElementById(`input-cantidad-${index}`);
    const hidPrecio = document.getElementById(`input-precio_unitario-${index}`);
    const hidNombre = document.getElementById(`input-nombre_producto-${index}`);
    const hidProdOrden = document.getElementById(`input-producto_orden_id-${index}`);
    if (hidProd) hidProd.remove();
    if (hidCant) hidCant.remove();
    if (hidPrecio) hidPrecio.remove();
    if (hidNombre) hidNombre.remove();
    if (hidProdOrden) hidProdOrden.remove();
    actualizarTotal();
    persistCart();
  };

  function mostrarResultados(elemento, data, callbackSeleccion) {
    const parent = elemento.parentNode;
    let prevList = parent.querySelector("ul.list-group");
    if (prevList) prevList.remove();
    const lista = document.createElement("ul");
    lista.className = "list-group";
    lista.style.display = 'block';
    if (!data || data.length === 0) {
      const li = document.createElement("li");
      li.className = "list-group-item text-muted";
      li.textContent = "Sin resultados";
      lista.appendChild(li);
    } else {
      data.forEach((item, index) => {
        const li = document.createElement("li");
        li.className = "list-group-item list-group-item-action";
        let nombre = item.nombre || (item.label ? item.label.split('(')[0].trim() : '');
        let sku = item.sku || (item.label ? item.label.split('(')[1]?.replace(')', '').trim() : '');
        let precio = item.precio !== undefined ? `$${parseInt(item.precio)}` : '';
        li.textContent = `${nombre} ${sku ? '(' + sku + ')' : ''} ${precio}`.trim();
        li.tabIndex = 0;
        li.dataset.index = index;
        li.addEventListener("mousedown", function(e) {
          e.preventDefault();
          callbackSeleccion(item, lista);
          if (lista && lista.parentNode) lista.parentNode.removeChild(lista);
          setTimeout(() => {
            if (elemento.classList.contains("buscar-producto")) {
              cantidadInput.focus();
              cantidadInput.select();
            }
          }, 0);
        });
        lista.appendChild(li);
      });
    }
    parent.appendChild(lista);
    let currentIndex = 0;
    if (lista.children.length > 0) {
      lista.children[currentIndex].classList.add("active");
    }
    elemento.addEventListener("keydown", function(e) {
      if (!lista.parentNode) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (currentIndex < lista.children.length - 1) {
          lista.children[currentIndex].classList.remove("active");
          currentIndex++;
          lista.children[currentIndex].classList.add("active");
          lista.children[currentIndex].scrollIntoView({block: "nearest"});
        }
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        if (currentIndex > 0) {
          lista.children[currentIndex].classList.remove("active");
          currentIndex--;
          lista.children[currentIndex].classList.add("active");
          lista.children[currentIndex].scrollIntoView({block: "nearest"});
        }
      }
      if (e.key === "Enter") {
        e.preventDefault();
        if (lista.children.length > 0 && lista.children[currentIndex]) {
          lista.children[currentIndex].dispatchEvent(new MouseEvent("mousedown"));
          if (lista && lista.parentNode) lista.parentNode.removeChild(lista);
        }
      }
      if (e.key === "Escape") {
        lista.remove();
        elemento.focus();
      }
    });
  }

  inputProducto.addEventListener("input", function() {
    const term = this.value.trim();
    let lista = this.parentNode.querySelector("ul.list-group");
    if (term.length < 1) {
      if (lista) lista.remove();
      btnAgregar.classList.add("d-none");
      return;
    }
    fetch(`/products/buscar?q=${encodeURIComponent(term)}`)
      .then(res => res.json())
      .then(data => {
        mostrarResultados(
          this,
          data,
          (item, lista) => {
            inputProducto.value = item.label;
            productoIdInput.value = item.id;
            precioInput.value = parseInt(item.precio);
            cantidadInput.value = 1;
            btnAgregar.classList.remove("d-none");
            lista.remove();
            cantidadInput.focus();
            cantidadInput.select();
          }
        );
      });
  });

  inputProducto.addEventListener("keydown", function(e) {
    if (e.key === "Enter") {
      let lista = this.parentNode.querySelector("ul.list-group");
      if (lista && lista.style.display !== "none" && lista.children.length > 0) {
        lista.children[0].dispatchEvent(new MouseEvent("mousedown"));
        e.preventDefault();
      } else if (productoIdInput.value) {
        cantidadInput.focus();
        cantidadInput.select();
        e.preventDefault();
      }
    }
  });

  cantidadInput.addEventListener("keydown", function(e) {
    if (e.key === "Enter") {
      precioInput.focus();
      precioInput.select();
      e.preventDefault();
    }
  });

  precioInput.addEventListener("keydown", function(e) {
    if (e.key === "Enter") {
      if (!btnAgregar.classList.contains("d-none")) {
        btnAgregar.click();
        inputProducto.focus();
        inputProducto.select();
      }
      e.preventDefault();
    }
  });

  btnAgregar.addEventListener("click", agregarAlCarrito);

  cantidadInput.addEventListener("input", actualizarTotal);
  precioInput.addEventListener("input", actualizarTotal);

  // Restaurar carrito desde localStorage
  (function restoreCartFromStorage() {
    try {
      // If server already populated hidden inputs for productos, do not restore from localStorage
      const existingHidden = form.querySelector('input[type="hidden"][name^="producto_id_"]');
      if (existingHidden) { actualizarTotal(); return; }
      const raw = localStorage.getItem(CART_STORAGE_KEY);
      if (!raw) { actualizarTotal(); return; }
      const items = JSON.parse(raw);
      if (Array.isArray(items)) {
        // Reiniciar
        carritoDiv.innerHTML = "";
        // Quitar inputs ocultos previos por si acaso
        Array.from(form.querySelectorAll('input[type="hidden"][name^="producto_id_"]')).forEach(n => n.remove());
        Array.from(form.querySelectorAll('input[type="hidden"][name^="cantidad_"]')).forEach(n => n.remove());
        Array.from(form.querySelectorAll('input[type="hidden"][name^="precio_unitario_"]')).forEach(n => n.remove());
        // Reset contador to 0 and repopulate
        contador = 0;
        items.forEach(it => {
          if (it && it.productoId && it.cantidad > 0 && it.precio > 0) {
            addCard(it.nombre || "Producto", String(it.productoId), parseInt(it.cantidad), parseInt(it.precio));
          }
        });
      }
    } catch (e) { /* noop */ }
    actualizarTotal();
  })();

});