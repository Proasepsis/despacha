# Roles, Permisos y Usuarios — Despacha

Guía de referencia para entender cómo funciona el control de acceso en la aplicación.

---

## Los tres roles (grupos de Django)

| Rol | Para quién es |
|-----|--------------|
| `operario` | Personal que sube archivos y edita cortes |
| `admin` | Coordinadores / supervisores con poderes extra |
| `consulta` | Solo pueden leer, no pueden cambiar nada |

> Los superusuarios de Django tienen acceso total a todo, incluyendo el panel de administración.

---

## Qué puede hacer cada rol

| Acción | operario | consulta | admin |
|--------|:--------:|:--------:|:-----:|
| Ver lista de cortes | ✓ | ✓ | ✓ |
| Subir un corte nuevo | ✓ | — | ✓ |
| Editar documentos y líneas | ✓ * | — | ✓ * |
| Generar archivo XLS | ✓ * | — | ✓ * |
| Tomar el bloqueo de un corte | ✓ | — | ✓ |
| **Editar sin tener el bloqueo** | — | — | ✓ |
| **Forzar liberación del bloqueo** | — | — | ✓ |
| Ver auditoría | — | — | ✓ |
| Configurar parámetros y reglas | — | — | ✓ |
| Administrar notificaciones | — | — | ✓ |
| Eliminar registros en el admin | — | — | ✓ |

`*` = Requiere tener el bloqueo activo (ver sección siguiente).

---

## El sistema de bloqueo (lock)

### Por qué existe

Cuando dos personas abren el mismo corte al mismo tiempo podrían pisarse los cambios. El bloqueo garantiza que solo una persona edita a la vez.

### Cómo funciona

1. **Al abrir un corte** — si nadie lo tiene bloqueado y el usuario es `operario` o `admin`, el sistema le asigna automáticamente el bloqueo por **30 minutos**.

2. **Mientras editas** — cada vez que guardas un campo (autosave), el bloqueo se renueva otros 30 minutos. No hay que hacer nada manual.

3. **Si el tiempo vence** — el bloqueo se libera solo. El próximo usuario que abra el corte lo tomará.

4. **Si otro ya lo tiene** — verás el nombre de quien lo tiene. No podrás editar (a menos que seas `admin`).

### Campos en la base de datos

El modelo `Corte` tiene dos campos para esto:

```
bloqueado_por   → quién tiene el bloqueo (FK a User, puede ser null)
bloqueado_hasta → hasta cuándo es válido (datetime, puede ser null)
```

### Admin puede saltarse el bloqueo

Un usuario `admin` puede:
- **Editar aunque no tenga el bloqueo** — útil si alguien se fue y dejó el corte bloqueado.
- **Forzar la liberación** — hay un botón "Liberar bloqueo" visible en el detalle del corte. Queda registrado en la auditoría.

---

## Flujo completo de una edición

```
Usuario abre detalle del corte
         │
         ▼
¿Tiene bloqueo activo otro usuario?
     │               │
    SÍ              NO
     │               │
     ▼               ▼
¿Es admin?    Sistema le da el bloqueo
  │     │     (30 min, automático)
 SÍ    NO           │
  │     │            ▼
  │     ▼      Modo EDITOR activo
  │   Solo     (puede cambiar campos)
  │   lectura
  ▼
Puede editar de todas formas
(bypass de bloqueo)
```

---

## Cómo se crean los usuarios

### Superusuario (automático al arrancar Docker)

Se configura en el archivo `.env`:

```
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=contraseña_segura
DJANGO_SUPERUSER_EMAIL=correo@empresa.com
```

Al arrancar el contenedor, si el usuario no existe lo crea y lo agrega al grupo `admin`. Si ya existe, no hace nada (no sobreescribe la contraseña).

### Usuarios normales (desde el panel admin)

1. Ir a `https://despacha.proasepsis.com.co/admin/`
2. Entrar con el superusuario
3. **Auth → Usuarios → Agregar usuario**
4. Crear el usuario con nombre y contraseña
5. En la sección **Grupos**, agregar `operario`, `admin` o `consulta` según corresponda

> Sin asignar un grupo, el usuario puede iniciar sesión pero no puede hacer nada en la app.

---

## Notificaciones por correo

Las notificaciones **no están atadas a los usuarios de la app**. Son listas de correos independientes que se configuran en el admin.

### Eventos que disparan notificaciones

| Evento | Cuándo ocurre |
|--------|--------------|
| `corte_generado` | Primera vez que se genera el XLS de un corte |
| `corte_regenerado` | Cuando se genera una versión nueva (v2, v3…) |
| `sin_maestro_detectado` | Al subir un archivo con productos no encontrados en la maestra |

### Cómo configurarlas

1. Ir al admin → **Core → Notificación destinatarios**
2. Editar el evento deseado
3. En el campo **Correos**, poner las direcciones separadas por coma o por línea:
   ```
   gerencia@empresa.com
   logistica@empresa.com, bodega@empresa.com
   ```
4. El checkbox **Activo** permite pausar un evento sin borrar los correos.

---

## Auditoría

Todo cambio queda registrado automáticamente: quién, cuándo, qué campo cambió, valor anterior y nuevo.

Se puede consultar en **Admin → Cortes → Auditorías** o en el panel de la app (solo `admin`).

Tipos de evento registrados:

| Tipo | Cuándo |
|------|--------|
| `edicion` | Se cambia cualquier campo de documento o línea |
| `bloqueo` | Se toma el bloqueo de un corte |
| `liberacion` | Se libera el bloqueo normalmente |
| `forzar_liberacion` | Un admin fuerza la liberación del bloqueo de otro |
| `generacion` | Se genera el archivo XLS |

---

## Resumen rápido para el día a día

**Quiero dar acceso a alguien nuevo:**
→ Crear usuario en admin → asignar grupo `operario`.

**Un operario dice que no puede editar:**
→ Verificar que está en el grupo `operario`. Verificar si alguien más tiene el bloqueo activo. Si es urgente, usar "Liberar bloqueo" (requiere `admin`).

**Quiero que alguien solo consulte:**
→ Asignar grupo `consulta`. No podrá cambiar nada ni subir archivos.

**Se me olvidó la contraseña del superusuario:**
→ Desde el servidor: `docker compose exec web python manage.py changepassword <usuario>`
