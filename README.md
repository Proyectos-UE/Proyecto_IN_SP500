# Proyecto IN SP500

## Obtención de datos
Para obtener los datos sobre el Sp500 y sus empresas es necesario ejecutar el archivo "sp500_yahoo.py".
Este tardará bastante, más de 1 h y 30 min, si se ejecuta por primera vez para obtener los datos. Si ya se ha ejecutado anteriormente tardará unos pocos minutos.

- La primera ejecución es más lenta, ya que tenemos que pedir toda la información por yahoo_finance y tiene un límite de peticiones así que se han aplicado sleeps y se hace por baches para intentar evitar llegar a este límite. Al hacer las peticiones por baches las aprovechamos para guardar esa información y no perderla en caso de que haya algún error.
- Las ejecuciones posteriores continua desde la última fecha así que el tiempo requerido es mucho menor.

El resultado serán dos archivos .csv con la informacion del precio del SP500 y el otro con detalles de cada empresa que pertenece a este.

## Peticiones
Nota: De momento no está implementado para poder rellenar los campos en /docs y es necesario usar una forma externa de hacer las peticiones como Postman.

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



