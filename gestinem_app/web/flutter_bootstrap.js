{{flutter_js}}
{{flutter_build_config}}

// Evita que pdfx abra el primer documento antes de cargar su motor web.
(async () => {
  try {
    await globalThis.gestinemPdfJsReady;
  } catch (error) {
    console.error('No se pudo cargar el motor de previsualizacion PDF.', error);
  }
  // Conservar la actualizacion de la cache que usa el arranque de Flutter.
  _flutter.loader.load({
    serviceWorkerSettings: {
      serviceWorkerVersion: {{flutter_service_worker_version}},
    },
  });
})();
