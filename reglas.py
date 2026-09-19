import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import datetime
import math
import os

# ==========================================
# INTERFAZ DE ENTRADA
# ==========================================
@dataclass
class FacturaExtraida:
    """
    Datos estructurados extraídos de la factura por el módulo P1.
    """
    proveedor: str
    importe: float
    fecha: datetime.date
    num_factura: str
    iva: Optional[float] = None
    texto_libre: Optional[str] = None
    confianza_ocr: float = 1.0
    sospechoso: bool = False


# ==========================================
# INTERFAZ DE SALIDA
# ==========================================
@dataclass
class DecisionParcial:
    """
    Decisión tomada por este módulo (P2), que será consumida por P3.
    """
    decision: str  # "PAGAR", "NO_PAGAR", "ESCALAR"
    motivo: str    # Siempre presente para cualquier decisión
    razonamiento: List[str] = field(default_factory=list)
    confianza: float = 0.0
    duplicado_sospechoso: bool = False


# ==========================================
# MÓDULO DE REGLAS (P2)
# ==========================================
class EvaluadorFacturas:
    """
    Clase principal que carga los datos del Excel y evalúa las facturas aplicando
    las reglas de negocio deterministas.
    """

    def __init__(self, excel_path: str = "FINAL_v7_DEFINITIVO_ahorasi.xlsx"):
        self.excel_path = excel_path
        self.proveedores_df: Optional[pd.DataFrame] = None
        self.pedidos_2026_df: Optional[pd.DataFrame] = None
        self.normas_pagos_df: Optional[pd.DataFrame] = None
        self.pedidos_2025_old_df: Optional[pd.DataFrame] = None
        
        # Historial de facturas procesadas en la sesión actual para chequeo de duplicados
        self.facturas_procesadas: List[FacturaExtraida] = []
        
        self.cargar_datos()

    def cargar_datos(self):
        """
        Carga las hojas del Excel. 
        Mapeo y suposiciones de columnas usadas por cada regla:
        
        - Hoja "Proveedores": 
          Columnas esperadas: "Nombre", "CIF". (Usada en Regla 1)
        - Hoja "Pedidos_2026": 
          Columnas esperadas: "Proveedor", "Importe_Esperado", "Num_Pedido". (Usada en Regla 2)
        - Hoja "Norma_Pagos_v3": 
          Columnas esperadas: "Proveedor", "Estado_Bloqueo" (Sí/No). (Usada en Regla 3)
        - Hoja "Pedidos_2025_OLD":
          Columnas esperadas: "Proveedor", "Importe", "Fecha", "Num_Factura". (Usada en Regla 6)
        """
        if os.path.exists(self.excel_path):
            try:
                self.proveedores_df = pd.read_excel(self.excel_path, sheet_name="Proveedores")
                self.pedidos_2026_df = pd.read_excel(self.excel_path, sheet_name="Pedidos_2026")
                self.normas_pagos_df = pd.read_excel(self.excel_path, sheet_name="Norma_Pagos_v3")
                self.pedidos_2025_old_df = pd.read_excel(self.excel_path, sheet_name="Pedidos_2025_OLD")
            except Exception as e:
                print(f"Error al cargar el Excel real: {e}. Se usarán stubs.")
                self._cargar_stubs()
        else:
            self._cargar_stubs()

    def _cargar_stubs(self):
        """
        STUB: Carga datos de prueba si el archivo Excel no existe todavía.
        TODO: Eliminar o deshabilitar en producción.
        """
        self.proveedores_df = pd.DataFrame({
            "Nombre": ["PROVEEDOR A", "PROVEEDOR B"],
            "CIF": ["B12345678", "B87654321"]
        })
        self.pedidos_2026_df = pd.DataFrame({
            "Proveedor": ["PROVEEDOR A", "PROVEEDOR A"],
            "Importe_Esperado": [1000.50, 500.00],
            "Num_Pedido": ["PED-2026-001", "PED-2026-002"]
        })
        self.normas_pagos_df = pd.DataFrame({
            "Proveedor": ["PROVEEDOR A", "PROVEEDOR B"],
            "Estado_Bloqueo": ["No", "Sí"]
        })
        self.pedidos_2025_old_df = pd.DataFrame({
            "Proveedor": ["PROVEEDOR A"],
            "Importe": [1000.50],
            "Fecha": [pd.Timestamp("2025-05-10")],
            "Num_Factura": ["FAC-25-001"]
        })

    # ------------------------------------------
    # FUNCIONES DE REGLAS PURAS
    # ------------------------------------------

    def regla_4_confiabilidad(self, factura: FacturaExtraida, umbral: float = 0.7) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Regla 4: Verificar OCR y sospechas.
        Retorna: (pasa_regla, motivo_fallo, evidencia)
        """
        if factura.sospechoso:
            return False, "documento_no_confiable", "El módulo P1 marcó la factura como sospechosa de manipulación."
        if factura.confianza_ocr < umbral:
            return False, "documento_no_confiable", f"Confianza OCR ({factura.confianza_ocr}) por debajo del umbral ({umbral})."
        return True, None, "Documento confiable según P1."

    def regla_1_proveedor_existe(self, factura: FacturaExtraida) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Regla 1: El proveedor debe existir en la hoja "Proveedores".
        Retorna: (pasa_regla, motivo_fallo, evidencia)
        """
        if self.proveedores_df is None or self.proveedores_df.empty:
            return False, "proveedor_no_encontrado", "Hoja Proveedores vacía o no cargada."
        
        match = self.proveedores_df[self.proveedores_df['Nombre'].str.upper() == factura.proveedor.upper()]
        if match.empty:
            return False, "proveedor_no_encontrado", f"Proveedor '{factura.proveedor}' no encontrado en la hoja 'Proveedores'."
        
        return True, None, f"Proveedor '{factura.proveedor}' encontrado en la hoja 'Proveedores'."

    def regla_6_duplicados(self, factura: FacturaExtraida) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Regla 6: Verificar duplicados contra sesión actual y contra "Pedidos_2025_OLD".
        Retorna: (es_duplicado, motivo_fallo, evidencia) -> si es_duplicado=True, la regla FALLA (es malo)
        """
        # 6a. Check contra procesadas en la sesión
        for proc in self.facturas_procesadas:
            if (proc.proveedor.upper() == factura.proveedor.upper() and
                proc.num_factura == factura.num_factura and
                math.isclose(proc.importe, factura.importe, rel_tol=1e-5)):
                return True, "posible_duplicado", "Factura duplicada encontrada en el procesamiento actual (misma sesión)."

        # 6b. Check contra histórico 2025
        if self.pedidos_2025_old_df is not None and not self.pedidos_2025_old_df.empty:
            mask = (
                (self.pedidos_2025_old_df['Proveedor'].str.upper() == factura.proveedor.upper()) &
                (self.pedidos_2025_old_df['Num_Factura'].astype(str) == str(factura.num_factura))
            )
            duplicados_hist = self.pedidos_2025_old_df[mask]
            for _, row in duplicados_hist.iterrows():
                if math.isclose(row['Importe'], factura.importe, abs_tol=0.01):
                    return True, "posible_duplicado", f"Duplicado detectado contra histórico en la hoja 'Pedidos_2025_OLD' (Factura: {row['Num_Factura']})."
                    
        return False, None, "No se encontraron duplicados."

    def regla_3_normas_pagos(self, factura: FacturaExtraida) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Regla 3: Aplicar normas de pago ("Norma_Pagos_v3"). Proveedores bloqueados, etc.
        Retorna: (pasa_regla, motivo_fallo, evidencia)
        """
        if self.normas_pagos_df is None or self.normas_pagos_df.empty:
            # Si no hay normas definidas, asumimos que pasa.
            return True, None, "No hay normas de pago cargadas."

        norma = self.normas_pagos_df[self.normas_pagos_df['Proveedor'].str.upper() == factura.proveedor.upper()]
        if not norma.empty:
            estado_bloqueo = norma.iloc[0]['Estado_Bloqueo']
            if str(estado_bloqueo).strip().lower() in ['sí', 'si', 'true', '1']:
                return False, "norma_incumplida: proveedor_bloqueado", f"Proveedor bloqueado según la hoja 'Norma_Pagos_v3'."
        
        return True, None, "Proveedor cumple con las normas de pago en la hoja 'Norma_Pagos_v3'."

    def regla_2_importe_pedido(self, factura: FacturaExtraida, tolerancia: float = 0.01) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Regla 2: El importe coincide con "Pedidos_2026".
        Retorna: (pasa_regla, motivo_fallo, evidencia)
        """
        if self.pedidos_2026_df is None or self.pedidos_2026_df.empty:
            return False, "importe_no_coincide", "No hay datos en la hoja 'Pedidos_2026' para cruzar."
            
        pedidos_prov = self.pedidos_2026_df[self.pedidos_2026_df['Proveedor'].str.upper() == factura.proveedor.upper()]
        
        if pedidos_prov.empty:
            return False, "importe_no_coincide", f"No existen pedidos para este proveedor en 'Pedidos_2026'."

        for _, row in pedidos_prov.iterrows():
            if math.isclose(factura.importe, float(row['Importe_Esperado']), abs_tol=tolerancia):
                return True, None, f"Importe coincide con el pedido {row['Num_Pedido']} en la hoja 'Pedidos_2026'."
                
        return False, "importe_no_coincide", f"El importe ({factura.importe}) no coincide con ningún pedido activo en 'Pedidos_2026'."

    # ------------------------------------------
    # EVALUACIÓN PRINCIPAL
    # ------------------------------------------
    
    def evaluar_factura(self, factura: FacturaExtraida) -> DecisionParcial:
        """
        Ejecuta todas las reglas sobre una factura extraída y devuelve una decisión consolidada.
        """
        razonamiento = []
        
        # 1. Confiabilidad del documento (Regla 4)
        pasa, motivo, ev_ocr = self.regla_4_confiabilidad(factura)
        razonamiento.append(f"Paso 1: {ev_ocr}")
        if not pasa:
            return DecisionParcial(
                decision="ESCALAR",
                motivo=motivo,
                razonamiento=razonamiento,
                confianza=1.0  # Alta confianza en que NO es confiable para automático
            )

        # 2. Check Duplicados (Regla 6)
        es_dupli, motivo_dup, ev_dup = self.regla_6_duplicados(factura)
        razonamiento.append(f"Paso 2: {ev_dup}")
        if es_dupli:
            return DecisionParcial(
                decision="ESCALAR",
                motivo=motivo_dup,
                razonamiento=razonamiento,
                confianza=0.9,
                duplicado_sospechoso=True
            )

        # 3. Proveedor existe (Regla 1)
        pasa, motivo_prov, ev_prov = self.regla_1_proveedor_existe(factura)
        razonamiento.append(f"Paso 3: {ev_prov}")
        if not pasa:
            return DecisionParcial(
                decision="ESCALAR",
                motivo=motivo_prov,
                razonamiento=razonamiento,
                confianza=0.8
            )
            
        # 4. Normas de Pago (Regla 3)
        pasa, motivo_norma, ev_norma = self.regla_3_normas_pagos(factura)
        razonamiento.append(f"Paso 4: {ev_norma}")
        if not pasa:
            return DecisionParcial(
                decision="NO_PAGAR",
                motivo=motivo_norma,
                razonamiento=razonamiento,
                confianza=1.0
            )
            
        # 5. Importe coincide con pedido (Regla 2)
        pasa, motivo_imp, ev_imp = self.regla_2_importe_pedido(factura)
        razonamiento.append(f"Paso 5: {ev_imp}")
        if not pasa:
            # Si el importe no cuadra pero no es fraude, lo marcamos para revisión
            return DecisionParcial(
                decision="NO_PAGAR",  # Cambiado a NO_PAGAR según requerimiento para discrepancia clara
                motivo=motivo_imp,
                razonamiento=razonamiento,
                confianza=0.8
            )
            
        # Si todo ha ido bien (Regla 5)
        self.facturas_procesadas.append(factura)  # Lo añadimos a procesados
        
        return DecisionParcial(
            decision="PAGAR",
            motivo="proveedor_validado_y_importe_coincide",
            razonamiento=razonamiento,
            confianza=1.0,
            duplicado_sospechoso=False
        )

