// Standard: Same-Origin. Der Browser ruft /api/... am Frontend-Port auf;
// nginx im Frontend-Container proxyt intern zum Backend-Container.
window.__BPSTRACKER_CONFIG__ = { API_BASE_URL: "same-origin", DEFAULT_LANGUAGE: "de" };
