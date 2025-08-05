# odoo-service/main.py
# Para correr este servidor, ejecuta en tu terminal:
# 1. pip install fastapi "uvicorn[standard]" certifi Pydantic
# 2. uvicorn main:app --reload

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import xmlrpc.client
import ssl
import certifi
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# --- Configuración de Odoo ---
URL = os.getenv("URL")
DB = os.getenv("DB")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

# --- Inicialización de FastAPI ---
app = FastAPI(
    title="Servicio de Integración con Odoo para Voraz",
    description="Una API para conectar el backend de Node.js con Odoo Online.",
    version="1.0.0"
)

# --- Modelos de Datos (Pydantic) ---
# FastAPI usa esto para validar los datos de entrada automáticamente.
# ¡Es una de sus mejores características!
class Producto(BaseModel):
    id: int
    cantidad: float

class Pedido(BaseModel):
    id_cliente: int
    productos: list[Producto]
    # Puedes agregar más campos que necesites desde tu backend
    # por ejemplo: notas, fecha_entrega_solicitada, etc.

# --- Lógica de Conexión a Odoo (reutilizada de tu script) ---
def get_odoo_models():
    """
    Se conecta a Odoo y devuelve el proxy 'models' para operar.
    Maneja la autenticación en cada llamada para asegurar una conexión fresca.
    """
    try:
        # Contexto SSL seguro, como lo tenías en tu script.
        ssl_context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile=certifi.where())
        
        # 1. Conectar a 'common' para obtener el uid
        common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", context=ssl_context)
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})

        if not uid:
            raise HTTPException(status_code=500, detail="Fallo en la autenticación con Odoo. Revisa las credenciales.")

        # 2. Conectar a 'object' para interactuar con los modelos
        models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", context=ssl_context)
        
        return models, uid

    except Exception as e:
        # Captura cualquier error de conexión o autenticación y lo reporta
        print(f"Error conectando a Odoo: {e}")
        raise HTTPException(status_code=503, detail=f"No se pudo conectar o autenticar con Odoo: {e}")


# --- Endpoints de la API ---

@app.get("/")
def read_root():
    """Endpoint de bienvenida para verificar que el servidor está funcionando."""
    return {"mensaje": "El servicio de integración con Odoo para Voraz está activo."}


@app.post("/crear-pedido/")
async def crear_pedido_en_odoo(pedido: Pedido):
    """
    Recibe los datos de un pedido desde el backend de Node.js,
    y lo crea en Odoo como una Orden de Venta.
    """
    print(f"Recibida petición para crear pedido para el cliente ID: {pedido.id_cliente}")

    try:
        models, uid = get_odoo_models()

        # Prepara las líneas del pedido en el formato que Odoo espera
        order_lines = []
        for producto in pedido.productos:
            line_vals = (0, 0, {
                'product_id': producto.id,
                'product_uom_qty': producto.cantidad,
            })
            order_lines.append(line_vals)
        
        # Datos para crear la Orden de Venta ('sale.order')
        order_vals = {
            'partner_id': pedido.id_cliente,
            'order_line': order_lines,
            # Puedes añadir más campos por defecto si lo necesitas
            # 'state': 'draft', # Por defecto se crea como presupuesto
        }

        # Ejecuta el método 'create' en el modelo 'sale.order' de Odoo
        order_id = models.execute_kw(DB, uid, PASSWORD,
            'sale.order', 'create',
            [order_vals]
        )

        if order_id:
            print(f"Pedido creado exitosamente en Odoo con ID: {order_id}")
            # Confirma la orden de venta para pasarla de 'Presupuesto' a 'Orden de Venta'
            models.execute_kw(DB, uid, PASSWORD, 'sale.order', 'action_confirm', [[order_id]])
            print(f"Orden de venta {order_id} confirmada.")
            
            return {
                "status": "exito",
                "mensaje": "Pedido creado y confirmado en Odoo.",
                "odoo_order_id": order_id
            }
        else:
            raise HTTPException(status_code=500, detail="Odoo no devolvió un ID para el pedido creado.")

    except xmlrpc.client.Fault as e:
        print(f"Error de XML-RPC desde Odoo: {e}")
        raise HTTPException(status_code=400, detail=f"Error de Odoo: {e.faultString}")
    except Exception as e:
        # Re-lanza la excepción si ya es una HTTPException
        if isinstance(e, HTTPException):
            raise e
        print(f"Error inesperado procesando el pedido: {e}")
        raise HTTPException(status_code=500, detail=f"Un error inesperado ocurrió: {e}")

# Para probar, puedes agregar más endpoints, por ejemplo para buscar un cliente
@app.get("/buscar-cliente/{telefono}")
async def buscar_cliente_por_telefono(telefono: str):
    """
    Busca un cliente (partner) en Odoo por su número de teléfono.
    """
    try:
        models, uid = get_odoo_models()
        
        # Busca clientes que tengan este teléfono o móvil
        domain = [
            '|',
            ('phone', '=', telefono),
            ('mobile', '=', telefono)
        ]
        fields = ['id', 'name', 'email', 'phone', 'mobile']
        
        partner_data = models.execute_kw(DB, uid, PASSWORD,
            'res.partner', 'search_read',
            [domain],
            {'fields': fields, 'limit': 1}
        )
        
        if not partner_data:
            raise HTTPException(status_code=404, detail=f"No se encontró ningún cliente con el teléfono {telefono}")
            
        return {
            "status": "exito",
            "cliente": partner_data[0]
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Ocurrió un error: {e}")
