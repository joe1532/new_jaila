/**
 * Til- og frakobling af faner, der er lagt på hylden.
 *
 * Koden bag en frakoblet fane bliver liggende urørt - modul, tilstand, API-klient og
 * backend-endepunkter. Kun indgangen fjernes, så fanen kan tændes igen ved at sætte
 * flaget til true, uden at noget skal skrives forfra.
 *
 * Sættes et flag til true, skal det kontrolleres, at fanens tilstand stadig passer til
 * resten af programmet. Sagsbehandling blev lagt på hylden i august 2026 og har ikke
 * fulgt med de ændringer, chat og test har fået siden.
 */

export const ENABLE_ANALYSE_TAB = false;
export const ENABLE_SAGSBEHANDLING_TAB = false;
