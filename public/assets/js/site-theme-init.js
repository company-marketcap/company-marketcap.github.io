/*
 * File: assets/js/site-theme-init.js
 * Loaded as a normal (blocking) script in <head> so the saved light/dark theme is applied before first paint.
 */

class SiteThemePreloader {
  constructor() {
    this.storageKey = "company-marketcap-theme-preference";
  }

  applySavedTheme() {
    let savedPreference = null;
    try {
      savedPreference = window.localStorage.getItem(this.storageKey);
    } catch (error) {
      savedPreference = null;
    }
    const followsSystem = !savedPreference || savedPreference === "system";
    const prefersDark = savedPreference === "dark" || (followsSystem && window.matchMedia("(prefers-color-scheme: dark)").matches);

    document.documentElement.classList.toggle("dark", prefersDark);
    document.documentElement.style.colorScheme = prefersDark ? "dark" : "light";
  }
}

new SiteThemePreloader().applySavedTheme();
