# Proyecto IN SP500

## Obtención de datos
Para obtener los datos sobre el Sp500 y sus empresas es necesario ejecutar el archivo "sp500_yahoo.py".
Este tardará bastante, más de 1 h y 30 min, si se ejecuta por primera vez para obtener los datos. Si ya se ha ejecutado anteriormente tardará unos pocos minutos.

- La primera ejecución es más lenta, ya que tenemos que pedir toda la información por yahoo_finance y tiene un límite de peticiones así que se han aplicado sleeps y se hace por baches para intentar evitar llegar a este límite. Al hacer las peticiones por baches las aprovechamos para guardar esa información y no perderla en caso de que haya algún error.
- Las ejecuciones posteriores continua desde la última fecha así que el tiempo requerido es mucho menor.

El resultado serán dos archivos .csv con la informacion del precio del SP500 y el otro con detalles de cada empresa que pertenece a este.