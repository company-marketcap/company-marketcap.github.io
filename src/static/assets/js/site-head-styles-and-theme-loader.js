/*
 * File: assets/js/site-head-styles-and-theme-loader.js
 * Loaded as a normal (blocking) script in <head>, before the Tailwind CDN script.
 * 1. Applies the saved light/dark theme before the first paint.
 * 2. Fetches the shared Tailwind source file and injects it as <style type="text/tailwindcss">,
 *    which the Tailwind browser CDN detects and compiles.
 * 3. Hides the page until the compiled styles are applied, so visitors never see unstyled content.
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

class SiteTailwindStylesheetLoader {
  constructor(stylesheetUrl, revealTimeoutMilliseconds) {
    this.stylesheetUrl = stylesheetUrl;
    this.revealTimeoutMilliseconds = revealTimeoutMilliseconds;
    this.pendingClassName = "site-styles-pending";
    this.loadStartTime = Date.now();
    this.isRevealed = false;
  }

  initialize() {
    this.hidePageUntilStylesApply();
    this.loadStylesheet();
    window.setTimeout(() => this.revealPage(), this.revealTimeoutMilliseconds);
  }

  hidePageUntilStylesApply() {
    const hidingStyle = document.createElement("style");
    hidingStyle.id = "site-styles-pending-rule";
    hidingStyle.textContent = `html.${this.pendingClassName} body { visibility: hidden; }`;
    document.head.append(hidingStyle);
    document.documentElement.classList.add(this.pendingClassName);
  }

  async loadStylesheet() {
    try {
      const response = await fetch(this.stylesheetUrl, { cache: "force-cache" });
      if (!response.ok) {
        throw new Error(`Stylesheet request failed with status ${response.status}`);
      }
      this.injectTailwindStyle(await response.text());
      this.waitForCompiledStyles();
    } catch (error) {
      console.error("Site styles could not be loaded:", error);
      this.revealPage();
    }
  }

  injectTailwindStyle(cssText) {
    const tailwindStyle = document.createElement("style");
    tailwindStyle.type = "text/tailwindcss";
    tailwindStyle.id = "site-tailwind-source-styles";
    tailwindStyle.textContent = cssText;
    document.head.append(tailwindStyle);
  }

  stylesAreApplied() {
    if (!document.body) {
      return false;
    }
    const bodyBackground = window.getComputedStyle(document.body).backgroundColor;
    return bodyBackground !== "rgba(0, 0, 0, 0)" && bodyBackground !== "transparent";
  }

  waitForCompiledStyles() {
    if (this.isRevealed) {
      return;
    }
    if (this.stylesAreApplied()) {
      this.revealPage();
      return;
    }
    if (Date.now() - this.loadStartTime > this.revealTimeoutMilliseconds) {
      this.revealPage();
      return;
    }
    window.requestAnimationFrame(() => this.waitForCompiledStyles());
  }

  revealPage() {
    if (this.isRevealed) {
      return;
    }
    this.isRevealed = true;
    document.documentElement.classList.remove(this.pendingClassName);
  }
}

new SiteThemePreloader().applySavedTheme();
new SiteTailwindStylesheetLoader("/assets/css/site-theme-and-components.css", 3000).initialize();
