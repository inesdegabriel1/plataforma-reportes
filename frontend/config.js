// Configuración del frontend. Este fichero es público: NO pongas aquí contraseñas ni datos.
//
// API_URL = dirección del backend.
//  - Si la web la sirve el propio backend (http://localhost:8000): "" (mismo servidor).
//  - Si la web se abre desde GitHub Pages: el backend que corre en TU PC (http://localhost:8000).
//    Solo funciona en el ordenador donde está arrancado el backend; los datos no salen de él.
window.APP_CONFIG = {
  API_URL: location.hostname.endsWith("github.io") ? "http://localhost:8000" : "",
};
