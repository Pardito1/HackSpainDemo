# Auditoría de materiales · 19 septiembre 2026

Los cinco archivos aportados coinciden byte por byte con las versiones revisadas. Los **500 PDFs aportados están importados y extraídos**, con una decisión por archivo. No hay PDFs ausentes ni diferencias entre originales y blobs conservados. Informe reproducible: `materials-audit.json`; script: `scripts/audit_materials.py`.

| Material | Uso real | Qué no hacemos |
|---|---|---|
| 500 PDFs de facturas | Extracción nativa/OCR, páginas y coordenadas; original por hash y nombre exacto para exportar | No ejecutamos instrucciones dentro de facturas ni completamos datos con el maestro |
| FINAL_v7_DEFINITIVO_ahorasi.xlsx | Maestro, pedidos y referencia textual de la norma v3; copia original conservada | No recalculamos ni usamos hojas antiguas para tomar decisiones |
| alberto_erp.py | Servicio oficial independiente consultado por HTTP/XML, con sesiones, paginación y fallos reales | No sustituimos el ERP por lectura de sus datos internos; no escribimos ni pagamos |
| MANUAL_ERP_2009.md | Contrato del conector y pruebas de sesión, errores, codificación y autoridad contable | No es una fuente factual por factura |
| Makefile | Revisado como guía de arranque y opciones de segundo lote. Ejecutar Python es equivalente a su objetivo de arranque | No se ingiere en el motor ni hace falta ejecutar todos sus targets |
| README.md | Requisitos de salidas, defensa y documentación, contrastados con capturas y aclaración humana | No sustituye la norma de negocio; conservamos discrepancia de horario |

## Excel: usar lo pertinente, no todas las celdas

Inspección de lectura, sin modificar el archivo: 14 hojas. `Proveedores` tiene 12 filas y 11 IDs (P007 repetido idéntico); `Pedidos_2026` contiene 516 pedidos; `Norma_Pagos_v3` conserva sus celdas de texto como evidencia.

- Proveedores A:D: ID, nombre, NIF, IBAN. Ciudad/condiciones del resto de columnas se conservan en el original, pero no gobiernan la decisión implementada.
- Pedidos A:E: pedido, proveedor, NIF, importe y estado. Identidad se contrasta; importe/estado contable se toman del ERP conforme a la precedencia documentada, no se oculta una identidad contradictoria.
- Norma_Pagos_v3: texto/celdas conservados; implementación revisada en código y política JSON. No ejecutamos texto libre.
- Hojas excluidas de decisión: Pedidos_2025_OLD, NO_TOCAR, backup_marzo, Hoja1, Hoja1 (2), notas_alberto, pendiente_revisar, MACROS_ROTAS, v6_deprecated, tablas_dinamicas y Sheet3.
- Se detectó `#REF!` en MACROS_ROTAS!A2. Esa hoja no es normativa. No tratamos una fórmula o una nota de una hoja antigua como una orden.

El diagnóstico de checksum IBAN no bloquea porque los números sintéticos del maestro no son válidos bajo ese checksum. Se verifica igualdad frente al maestro; esto no sería una política aceptable sin revisión para datos bancarios reales.

## Qué falta

El lote adicional oficial, su ERP/norma actualizados y la referencia privada no están incluidos. No podemos declarar APTO ni precisión oficial. La captura nueva fija domingo 20 a las 11:00 (Madrid); el README aportado aún dice 10:30. Usar 10:30 como margen interno y confirmar con organización.

## Auditoría repetible

```bash
python scripts/audit_materials.py --source ../500-sombras-de-alberto --data data --batch ID_DEL_LOTE --report auditoria.json
```

El informe estático de materiales muestra qué versión revisamos; no es una promesa de que cualquier archivo futuro sea idéntico. Los cambios se revisan en la pantalla «Fuentes y cambios».
