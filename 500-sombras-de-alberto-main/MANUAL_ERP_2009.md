# MANUAL DEL BRIDGE ERP · Sistemas (rev. 2009, vigente)

> Documento recuperado de la intranet del cliente. Última edición: 11/2009.
> Estado: VIGENTE. Responsable: J.M. (ya no trabaja aquí).

El ERP corporativo no se toca. Para consultas existe el **bridge HTTP**, instalado
en 2009 sobre el AS/400. Alberto lo usa desde entonces. Ahora lo usáis vosotros.

## 1 · Arranque

El bridge corre **en vuestra máquina** (no depende de la red del evento):

```bash
python3 alberto_erp.py                 # escucha en http://127.0.0.1:8009
python3 alberto_erp.py --puerto 8010   # si el 8009 está ocupado
```

Si Alberto envía trabajo adicional durante el fin de semana, la actualización
del ERP se carga al arrancar:

```bash
python3 alberto_erp.py --lote2 ruta/al/erp_export_lote2.csv
```

## 2 · Identificación

Las sesiones caducan a los **15 minutos o 300 consultas** (política de 2009;
no está en nuestra mano cambiarla). Renovad el token cuando el bridge
devuelva `SES-401`.

```bash
curl -s -X POST http://127.0.0.1:8009/erp/login \
     -d "usuario=alberto" -d "clave=FACTURAS2009"
```

Respuesta (XML, **ISO-8859-1**, como todo lo que sale del bridge):

```xml
<sesion>
  <token>...</token>
  <caduca_en_segundos>900</caduca_en_segundos>
  <usos_maximos>300</usos_maximos>
</sesion>
```

El token viaja en la cabecera `X-ERP-Token` (o en el parámetro `?token=`).

## 2b · Consulta web (para personal de administración)

Quien no quiera hablar XML puede abrir `http://127.0.0.1:8009/` en el navegador,
identificarse en el formulario y navegar los asientos en `/erp/consulta`
(paginación, y búsqueda por número de asiento). Misma sesión, mismos datos y
las mismas averías: si sale `ORA-00600`, se pulsa Actualizar y ya está.

La consulta web es para mirar. Su sistema debería hablar con los recursos de
la sección 3, que para eso están desde 2009.

## 3 · Consultas

| Recurso | Qué devuelve |
| --- | --- |
| `GET /erp/asientos?pagina=N` | Asientos contables, **20 por página**, `pagina` empieza en 1. El nodo `<meta>` trae `total` y `paginas`. |
| `GET /erp/asientos/AS-00412` | Un asiento concreto. |
| `GET /erp/estado` | Salud del bridge (sin identificación). |

Aviso de Sistemas: durante una descarga completa **verá algún `ORA-00600`**.
No es usted; es el núcleo. Reintente la misma consulta y continúe. Un cliente
que no reintenta no llega a la página 26.

```bash
curl -s -H "X-ERP-Token: $TOKEN" "http://127.0.0.1:8009/erp/asientos?pagina=1"
```

Cada asiento: `id`, `fecha` (**DD/MM/AAAA**), `proveedor`, `nif`, `pedido`,
`importe` (**coma decimal y punto de miles: 12.874,40**) y `estado`
(`PENDIENTE` o `PAGADA`).

## 4 · Códigos de error conocidos

| Código | Significado | Qué hacer |
| --- | --- | --- |
| `SES-401` | Sesión inválida o caducada | Volver a `/erp/login` |
| `ORA-00600` (HTTP 500) | Error interno del núcleo. Es del año de instalación. | **Reintentar la misma consulta.** Funciona. No llame a Mantenimiento. |
| `ERP-429` (HTTP 429) | Demasiadas consultas por segundo | Esperar lo que diga `Retry-After` |
| `ERP-400` | Página fuera de rango o parámetro inválido | Revisar la consulta |
| `ERP-404` | El recurso o asiento no consta | Revisar el identificador |

## 5 · Avisos de Sistemas

- El bridge responde con la calma propia de su época. Planificad las consultas;
  descargarse los asientos una vez y trabajar en local es lo que haría cualquiera
  que haya conocido este sistema.
- Los datos que sirve el bridge son la referencia contable oficial para conciliar.
- Sí, es XML en ISO-8859-1 con fechas y números a la española. En 2009 era lo moderno.
