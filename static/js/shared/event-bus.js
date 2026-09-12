/**
 * Event Bus Pattern - Comunicacion entre modulos sin acoplamiento directo
 * Permite que los modulos se comuniquen sin conocerse entre si
 */
window.EventBus = (function() {
    'use strict';
    
    const events = {};
    
    return {
        // Suscribirse a un evento
        on: function(eventName, callback) {
            if (!events[eventName]) {
                events[eventName] = [];
            }
            events[eventName].push(callback);
        },
        
        // Desuscribirse de un evento
        off: function(eventName, callback) {
            if (events[eventName]) {
                const index = events[eventName].indexOf(callback);
                if (index > -1) {
                    events[eventName].splice(index, 1);
                }
            }
        },
        
        // Emitir un evento
        emit: function(eventName, data) {
            if (events[eventName]) {
                events[eventName].forEach(callback => {
                    try {
                        callback(data);
                    } catch (error) {
                        console.error(`Error en evento ${eventName}:`, error);
                    }
                });
            }
        },
        
        // Debug: Ver eventos registrados
        getEvents: function() {
            return Object.keys(events);
        }
    };
})();

/**
 * Module Registry - Registro de modulos cargados
 */
window.ModuleRegistry = (function() {
    'use strict';
    
    const modules = {};
    
    return {
        register: function(name, module) {
            modules[name] = module;
            console.log(`Modulo ${name} registrado`);
            
            // Emitir evento de modulo cargado
            window.EventBus.emit('module:loaded', { name, module });
        },
        
        get: function(name) {
            return modules[name];
        },
        
        getAll: function() {
            return modules;
        },
        
        unregister: function(name) {
            delete modules[name];
            window.EventBus.emit('module:unloaded', { name });
        }
    };
})();