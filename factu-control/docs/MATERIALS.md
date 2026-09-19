# Auditoría de materiales · 19 septiembre 2026

Los cinco materiales base de Lote 1 coinciden byte por byte con las versiones
revisadas. Los **500 PDFs aportados están importados y extraídos**, con una
decisión por archivo. No hay PDFs ausentes ni diferencias entre originales y
blobs conservados. Informe reproducible para esa base:
`materials-audit.json`; script: `scripts/audit_materials.py`.

Lote 2 añade 40 PDFs públicos y tres fuentes incrementales. El runner
`factu lote2` comprueba antes de escribir que existen exactamente 40 nombres
únicos, el Excel, ambos CSV y el export ERP con 40 filas/esquema esperado; sus
hashes, blobs, filas de origen y perfil de extracción quedan vinculados al lote.
No sustituye el ERP por el CSV: exige que el snapshot HTTP contenga su
actualización.

| Material | Uso real | Qué no hacemos |
|---|---|---|
| 500 PDFs de facturas | Extracción nativa/OCR, páginas y coordenadas; original por hash y nombre exacto para exportar | No ejecutamos instrucciones dentro de facturas ni completamos datos con el maestro |
| FINAL_v7_DEFINITIVO_ahorasi.xlsx | Maestro, pedidos actuales, histórico parcial y referencia textual de la norma v3; copia original conservada | No recalculamos fórmulas ni confundimos un pedido histórico con un pago confirmado |
| alberto_erp.py | Servicio oficial independiente consultado por HTTP/XML, con sesiones, paginación y fallos reales | No sustituimos el ERP por lectura de sus datos internos; no escribimos ni pagamos |
| MANUAL_ERP_2009.md | Contrato del conector y pruebas de sesión, errores, codificación y autoridad contable | No es una fuente factual por factura |
| Makefile | Revisado como guía de arranque y opciones de segundo lote. Ejecutar Python es equivalente a su objetivo de arranque | No se ingiere en el motor ni hace falta ejecutar todos sus targets |
| README.md | Requisitos de salidas, defensa y documentación, contrastados con capturas y aclaración humana | No sustituye la norma de negocio; conservamos discrepancia de horario |
| `facturas_primin/` (40 PDFs) | Perfil `lote2_ocr_v1`, evidencia de lectura nativa/RapidOCR, decisiones y exportación del Lote 2 | No se infiere moneda por idioma, país o dirección; anotaciones/tachones se escalan |
| `proveedores_nuevos.csv` + `pedidos_nuevos.csv` | Incremento de proveedor/pedido, con archivo, hash, columna y fila de procedencia | No sobrescriben la copia del Excel ni convierten texto libre en una regla |
| `erp_export_lote2.csv` | Contrato de presencia de los pedidos incrementales en el snapshot HTTP | No se usa como ERP local ni se confunde con una autorización de pago |

## Excel: usar lo pertinente, no todas las celdas

Inspección de lectura, sin modificar el archivo: 14 hojas. `Proveedores` tiene 12 filas y 11 IDs (P007 repetido idéntico); `Pedidos_2026` contiene 516 pedidos; `Norma_Pagos_v3` conserva sus celdas de texto como evidencia.

- Proveedores A:D: ID, nombre, NIF, IBAN. Ciudad/condiciones del resto de columnas se conservan en el original, pero no gobiernan la decisión implementada.
- Pedidos A:E: pedido, proveedor, NIF, importe y estado. Identidad se contrasta; importe/estado contable se toman del ERP conforme a la precedencia documentada, no se oculta una identidad contradictoria.
- Norma_Pagos_v3: texto/celdas conservados; implementación revisada en código y política JSON. No ejecutamos texto libre.
- Pedidos_2025_OLD: dos pedidos e importes, con aviso explícito de archivo parcial. Una coincidencia exacta de pedido requiere revisión humana; no contiene NIF, número de factura ni estado de pago. Un importe coincidente, por sí solo, no demuestra duplicidad.
- Hojas excluidas de decisión: NO_TOCAR, backup_marzo, Hoja1, Hoja1 (2), notas_alberto, pendiente_revisar, MACROS_ROTAS, v6_deprecated, tablas_dinamicas y Sheet3.
- Se detectó `#REF!` en MACROS_ROTAS!A2. Esa hoja no es normativa. No tratamos una fórmula o una nota de una hoja antigua como una orden.

El diagnóstico de checksum IBAN no bloquea porque los números sintéticos del maestro no son válidos bajo ese checksum. Se verifica igualdad frente al maestro; esto no sería una política aceptable sin revisión para datos bancarios reales.

## Qué falta

La referencia privada del jurado y cualquier norma/lote posterior no están
disponibles. No podemos declarar APTO ni precisión oficial. La captura nueva
fija domingo 20 a las 11:00 (Madrid); el README aportado aún dice 10:30. Usar
10:30 como margen interno y confirmar con organización.

## Auditoría repetible

```bash
python scripts/audit_materials.py --source ../500-sombras-de-alberto --data data --batch ID_DEL_LOTE --report auditoria.json
```

El informe estático de materiales muestra qué versión revisamos; no es una promesa de que cualquier archivo futuro sea idéntico. Los cambios se revisan en la pantalla «Datos y actualizaciones».
