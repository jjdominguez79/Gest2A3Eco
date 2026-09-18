# Motor PDF web

PDF.js 4.6.82, version compatible con pdfx 2.11.0.
Origen: paquete oficial `pdfjs-dist@4.6.82` del registro npm.
Licencia Apache-2.0 incluida en `4.6.82/LICENSE`.

Se incluyen el motor, el worker, los mapas CMap y las fuentes estandar.
El motor y el worker deben usar la misma version. No se cargan scripts de CDN
ni se envian documentos a servicios externos para previsualizarlos.
`web/index.html` configura los recursos y desactiva la evaluacion de codigo;
`web/flutter_bootstrap.js` espera a la inicializacion antes de arrancar Flutter.
