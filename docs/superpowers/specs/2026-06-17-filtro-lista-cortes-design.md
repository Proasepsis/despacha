# Spec: Filtro de lista de cortes

**Fecha:** 2026-06-17
**Estado:** aprobado

## Problema

La lista de cortes muestra siempre los últimos 30 días sin posibilidad de filtrar. Si un usuario necesita encontrar un corte con una factura específica de hace más de 30 días, no tiene forma de hacerlo desde la UI.

## Solución

Barra de filtros encima de la grilla con búsqueda por texto (factura/NIT), estado, usuario y rango de fechas. Implementada como form GET — sin nuevas dependencias, sin nuevo endpoint.

## Comportamiento de fechas

| Situación | Rango aplicado |
|---|---|
| Sin ningún filtro activo | Últimos 30 días (default actual) |
| Cualquier filtro activo sin fechas explícitas | Toda la historia |
| `desde` y/o `hasta` explícitos | Ese rango (desde solo → hasta hoy; hasta solo → desde el inicio) |

## Filtros

| Param GET | Campo ORM | Tipo |
|---|---|---|
| `q` | `documentos__factura__icontains` ó `documentos__nit__icontains` | texto libre, OR, `.distinct()` |
| `estado` | `estado` | uno de: `cargado`, `en_revision`, `generado`, `con_error` |
| `usuario` | `usuario_carga_id` | id entero |
| `desde` | `fecha__gte` | fecha ISO |
| `hasta` | `fecha__lte` | fecha ISO |

Complejidad de búsqueda: O(N) sobre `cortes_documento` — aceptable para el volumen esperado. Sin índice adicional por ahora.

## Aviso de resultados

Cuando hay al menos un filtro activo, se muestra sobre la grilla:
- `"Se encontró 1 corte"` / `"Se encontraron N cortes"` en texto pequeño y discreto.
- Si no hay resultados: `"No se encontraron cortes con esos filtros."` (en lugar del mensaje actual de 30 días vacíos).

## Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [🔍 Factura o NIT...] [Estado ▾] [Usuario ▾] [Desde] [Hasta]  │
│                                               [✕ Limpiar filtros]│
└─────────────────────────────────────────────────────────────────┘
  Se encontraron 3 cortes    ← solo si hay filtros activos

  Corte   Tipo   Estado   Facturas · Versión · Usuario
  ───────────────────────────────────────────────────
  ...filas paginadas de 20...
```

El botón `✕ Limpiar filtros` solo aparece cuando al menos un param GET está activo. Redirige a `?` (sin params).

En móvil los controles se apilan verticalmente (el buscador ocupa el ancho completo, luego el resto en filas).

## Comportamiento JS

- **Input de texto `q`:** debounce de 400ms — al dejar de escribir se hace submit del form.
- **Selectores y fechas:** submit inmediato al cambiar (`change` event).
- **Degradación:** sin JS el form funciona igual con el botón de submit nativo del navegador (o Enter).

~20 líneas de JS inline en el template, sin librerías.

## Archivos a modificar

- `cortes/views.py` — `ListaCortesView.get_queryset()` y `get_context_data()`
- `cortes/templates/cortes/lista.html` — form de filtros, aviso de resultados, JS

## No incluido

- Resaltado de factura dentro del detalle (spec separado si se requiere)
- Índice trigram en PostgreSQL (optimización futura si el volumen crece)
- Filtro por tipo de comprobante (ya se muestra como columna informativa)
