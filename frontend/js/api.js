// Cliente del API. El token se guarda solo en sessionStorage (se borra al cerrar la pestaña).
const BASE = ((window.APP_CONFIG && window.APP_CONFIG.API_URL) || "").replace(/\/$/, "");
const KEY = "ehm_token";

export const getToken = () => sessionStorage.getItem(KEY);
export const setToken = (t) => sessionStorage.setItem(KEY, t);
export const clearToken = () => sessionStorage.removeItem(KEY);

export class AuthError extends Error {}

export async function api(path, { method = "GET", body, params } = {}) {
  const url = new URL(BASE + path, location.href);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
    }
  }
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = "Bearer " + token;

  let res;
  try {
    res = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new Error(BASE.includes("localhost")
      ? "No se puede conectar con el backend de tu PC (http://localhost:8000). Arráncalo y vuelve a intentarlo. Si el navegador pregunta por acceso a la red local, acéptalo."
      : "No se puede conectar con el servidor. ¿Está arrancado el backend?");
  }
  let data = null;
  try { data = await res.json(); } catch { /* respuesta sin JSON */ }
  if (res.status === 401 && path !== "/api/login") {
    clearToken();
    throw new AuthError((data && data.detail) || "Sesión caducada");
  }
  if (!res.ok) throw new Error((data && data.detail) || `Error ${res.status}`);
  return data;
}
