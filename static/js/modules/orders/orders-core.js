/**
 * Orders Module - Namespace aislado para ordenes de trabajo
 * Evita conflictos con otros modulos
 */
window.OrdersModule = (function() {
    'use strict';
    
    // Variables privadas del modulo
    let formData = {};
    let cartData = [];
    let isInitialized = false;
    
    // Configuracion del modulo
    const config = {
        storageKeys: {
            form: 'ot_form',
            cart: 'ot_cart'
        },
        autoSave: true
    };
    
    // Funciones privadas
    function saveFormData() {
        if (!config.autoSave) return;
        
        try {
            const formElements = document.querySelectorAll('#ot-form input, #ot-form select, #ot-form textarea');
            const data = {};
            
            formElements.forEach(element => {
                if (element.name) {
                    data[element.name] = element.value;
                }
            });
            
            localStorage.setItem(config.storageKeys.form, JSON.stringify(data));
            window.EventBus.emit('orders:form-saved', data);
        } catch (error) {
            console.error('Error guardando formulario OT:', error);
        }
    }
    
    function restoreFormData() {
        try {
            const savedData = localStorage.getItem(config.storageKeys.form);
            if (!savedData) return;
            
            const data = JSON.parse(savedData);
            
            Object.keys(data).forEach(name => {
                const element = document.querySelector(`[name="${name}"]`);
                if (element && data[name]) {
                    element.value = data[name];
                }
            });
            
            window.EventBus.emit('orders:form-restored', data);
        } catch (error) {
            console.error('Error restaurando formulario OT:', error);
        }
    }
    
    function saveCartData() {
        if (!config.autoSave) return;
        
        try {
            localStorage.setItem(config.storageKeys.cart, JSON.stringify(cartData));
            window.EventBus.emit('orders:cart-saved', cartData);
        } catch (error) {
            console.error('Error guardando carrito OT:', error);
        }
    }
    
    function restoreCartData() {
        try {
            const savedCart = localStorage.getItem(config.storageKeys.cart);
            if (!savedCart) return;
            
            cartData = JSON.parse(savedCart);
            renderCart();
            window.EventBus.emit('orders:cart-restored', cartData);
        } catch (error) {
            console.error('Error restaurando carrito OT:', error);
        }
    }
    
    function renderCart() {
        const cartContainer = document.getElementById('carrito-productos');
        if (!cartContainer) return;
        
        cartContainer.innerHTML = '';
        
        cartData.forEach((item, index) => {
            const cartItem = createCartItem(item, index);
            cartContainer.appendChild(cartItem);
        });
        
        updateCartTotal();
    }
    
    function esc(s) {
        return String(s === null || s === undefined ? '' : s)
            .replace(/[&<>"']/g, function (c) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
            });
    }

    function createCartItem(item, index) {
        const div = document.createElement('div');
        div.className = 'tarjeta-producto mb-2 p-2 border rounded';
        div.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div class="flex-grow-1">
                    <input type="text" class="form-control orders-product-name" 
                           value="${esc(item.nombre)}" 
                           onchange="window.OrdersModule.updateProductName(${index}, this.value)"
                           placeholder="Nombre del producto">
                    <small class="text-muted">
                        ${item.cantidad || 1} x $${item.precio_unitario || 0} = $${(item.cantidad || 1) * (item.precio_unitario || 0)}
                    </small>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger" 
                        onclick="window.OrdersModule.removeFromCart(${index})">
                    Eliminar
                </button>
            </div>
        `;
        return div;
    }
    
    function updateCartTotal() {
        const total = cartData.reduce((sum, item) => {
            return sum + ((item.cantidad || 1) * (item.precio_unitario || 0));
        }, 0);
        
        const totalElement = document.getElementById('total-productos');
        if (totalElement) {
            totalElement.textContent = `$${total}`;
        }
        
        window.EventBus.emit('orders:total-updated', { total, items: cartData.length });
    }
    
    function initializeFormAutoSave() {
        const form = document.getElementById('ot-form');
        if (!form) return;
        
        // Auto-guardar al cambiar campos
        form.addEventListener('input', function() {
            clearTimeout(window.ordersFormSaveTimeout);
            window.ordersFormSaveTimeout = setTimeout(saveFormData, 1000);
        });
        
        // Restaurar datos al cargar
        restoreFormData();
    }
    
    function clearStorageOnSuccess() {
        // Solo limpiar cuando la orden se cree exitosamente
        window.EventBus.on('orders:created-successfully', function() {
            try {
                localStorage.removeItem(config.storageKeys.form);
                localStorage.removeItem(config.storageKeys.cart);
                cartData = [];
                console.log('Storage limpiado despues de crear orden exitosamente');
            } catch (error) {
                console.error('Error limpiando storage:', error);
            }
        });
    }
    
    // API publica del modulo
    return {
        init: function() {
            if (isInitialized) {
                console.warn('OrdersModule ya esta inicializado');
                return;
            }
            
            console.log('Inicializando Orders Module...');
            
            initializeFormAutoSave();
            restoreCartData();
            clearStorageOnSuccess();
            
            isInitialized = true;
            
            // Registrar el modulo
            window.ModuleRegistry.register('orders', this);
            
            // Emitir evento de inicializacion
            window.EventBus.emit('orders:initialized', { module: 'orders' });
        },
        
        addToCart: function(product) {
            cartData.push({
                id: product.id,
                nombre: product.nombre,
                cantidad: product.cantidad || 1,
                precio_unitario: product.precio_unitario || 0,
                nombre_personalizado: product.nombre_personalizado || null
            });
            
            saveCartData();
            renderCart();
            window.EventBus.emit('orders:product-added', product);
        },
        
        removeFromCart: function(index) {
            if (index >= 0 && index < cartData.length) {
                const removedItem = cartData.splice(index, 1)[0];
                saveCartData();
                renderCart();
                window.EventBus.emit('orders:product-removed', { item: removedItem, index });
            }
        },
        
        updateProductName: function(index, newName) {
            if (index >= 0 && index < cartData.length) {
                cartData[index].nombre_personalizado = newName.trim() || null;
                saveCartData();
                window.EventBus.emit('orders:product-name-updated', { 
                    index, 
                    newName, 
                    item: cartData[index] 
                });
            }
        },
        
        clearCart: function() {
            cartData = [];
            saveCartData();
            renderCart();
            window.EventBus.emit('orders:cart-cleared');
        },
        
        getCartData: function() {
            return [...cartData]; // Retornar copia para evitar mutacion externa
        },
        
        // Control de storage
        enableAutoSave: function() {
            config.autoSave = true;
        },
        
        disableAutoSave: function() {
            config.autoSave = false;
        },
        
        clearStorage: function() {
            try {
                localStorage.removeItem(config.storageKeys.form);
                localStorage.removeItem(config.storageKeys.cart);
                cartData = [];
                renderCart();
                window.EventBus.emit('orders:storage-cleared');
            } catch (error) {
                console.error('Error limpiando storage:', error);
            }
        },
        
        isInitialized: function() {
            return isInitialized;
        },
        
        version: '2.0.0'
    };
})();

// Auto-inicializar solo si estamos en paginas de ordenes
document.addEventListener('DOMContentLoaded', function() {
    const isOrdersPage = document.body.classList.contains('orders-module') || 
                        window.location.pathname.includes('/ordenes/') ||
                        document.getElementById('ot-form') !== null;
    
    if (isOrdersPage) {
        // Esperar a que el EventBus este disponible
        if (window.EventBus && window.ModuleRegistry) {
            window.OrdersModule.init();
        } else {
            setTimeout(() => {
                if (window.OrdersModule && window.OrdersModule.init) {
                    window.OrdersModule.init();
                }
            }, 100);
        }
    }
});