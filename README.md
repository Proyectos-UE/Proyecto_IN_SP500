# Proyecto IN SP500

## Obtención de datos
Para obtener los datos sobre el Sp500 y sus empresas es necesario ejecutar el archivo "sp500_yahoo.py".
Este tardará bastante, más de 1 h y 30 min, si se ejecuta por primera vez para obtener los datos. Si ya se ha ejecutado anteriormente tardará unos pocos minutos.

- La primera ejecución es más lenta, ya que tenemos que pedir toda la información por yahoo_finance y tiene un límite de peticiones así que se han aplicado sleeps y se hace por baches para intentar evitar llegar a este límite. Al hacer las peticiones por baches las aprovechamos para guardar esa información y no perderla en caso de que haya algún error.
- Las ejecuciones posteriores continua desde la última fecha así que el tiempo requerido es mucho menor.

El resultado serán dos archivos .csv con la informacion del precio del SP500 y el otro con detalles de cada empresa que pertenece a este.

## Ejemplos de peticiones

Con la API arrancada (`python -m uvicorn app:app --reload`).
También se pueden probar desde http://127.0.0.1:8000/docs

### Casos correctos

```bash
curl "http://127.0.0.1:8000/v1/companies?limit=5"                               # 200
curl "http://127.0.0.1:8000/v1/companies?sector=Technology&limit=5"             # 200
curl http://127.0.0.1:8000/v1/companies/AAPL                                    # 200
curl "http://127.0.0.1:8000/v1/companies/AAPL/prices?start=2025-01-01&end=2025-01-31"  # 200
curl http://127.0.0.1:8000/v1/sectors                                           # 200
```

### Casos inválidos

```bash
curl http://127.0.0.1:8000/v1/companies/ZZZZ                                    # 404 empresa inexistente
curl 'http://127.0.0.1:8000/v1/companies/AA$PL'                                 # 422 ticker mal formado
curl "http://127.0.0.1:8000/v1/companies?limit=0"                               # 422 fuera de rango
curl "http://127.0.0.1:8000/v1/companies/AAPL/prices?start=hola"                # 422 fecha inválida
curl "http://127.0.0.1:8000/v1/companies/AAPL/prices?start=2025-05-01&end=2025-01-01"  # 422 rango invertido
```

### Acceso no autorizado (webhook)

```bash
# Sin firma -> 403
curl -X POST http://127.0.0.1:8000/verificacion \
  -H "Content-Type: application/json" \
  -d '{"event_id": "evt-001", "event_type": "verification.simple"}'

# Firma falsa -> 403
curl -X POST http://127.0.0.1:8000/verificacion \
  -H "Content-Type: application/json" -H "x-signature: sha256=falsa" \
  -d '{"event_id": "evt-001", "event_type": "verification.simple"}'
```

Para el caso correcto (202) la firma se calcula con `WEBHOOK_SECRET`:
ver el apartado *Verificación* (Postman) o el script `enviar_webhook.py`.

## Tests

```bash
python -m pytest -v
```

No necesitan la API arrancada ni los CSV reales: usan datos de ejemplo.
Cubren casos correctos, inválidos (404/422/503) y no autorizados del webhook (403/413).

### Verificación
Se ha implementado verificación con una clave en la cabecera de las peticiones que de momento solo está disponible en /verificacion.

Para una validación exitosa será necesario lo siguietne:
- El tamaño de la petición no puede ser superior a unos 70kb.
- Tener un esquema de petición concreto que se pueden encontrar en models.py. Para /verificacion el esquema es "ValidacionBase"
- Tener en la cabecera una clave valida. Para tener una clave valida se requiere lo siguiente
    - Añadir el campo "x-signature" a la cabecera
    - Tener la variable secreta con la que se lanza la API. Conocida en el archivo app.py como "secretWH"
    - Una vez terminado el cuerpo de la petición generar un hash criptográfico HMAC SHA256, añadirle el prefijo "sha256=" y asignar el resultado al valor de "x-signature".
    Para postman esto se puede hacer de forma sencilla en el apartado de Scripts Before Request
   
    ```
    //Clave con la que se inicializa la API
    const secret = "Clave_Exacta";

    //Obtenemos el cuerpo de la petición 
    const body = pm.request.body.toString();
    
    // Creamos el hash con el cuerpo y la clave
    const hash = CryptoJS.HmacSHA256(body, secret).toString(CryptoJS.enc.Hex);
    
    // Añadimos el prefijo
    const signature = "sha256=" + hash;
    
    // Y la asignamos a una variable para usar en la cabecera
    pm.variables.set("computed_signature", signature);
    ````
    Y por último en el valor de "x-signature" le asignamos computed_signature usando {{computed_signature}} como valor

Si las validaciones anteriores pasan se devolverá un 202 con json indicando que ha pasado la validación y el cuerpo de la ptición.



