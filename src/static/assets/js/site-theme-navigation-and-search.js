/*
 * File: assets/js/site-theme-navigation-and-search.js
 * Shared behaviour for every page: theme switching, mobile sidebar drawer, calculator search.
 * Every element is looked up by the page-namespaced id built from <body data-page-slug="...">.
 */

class SiteTextNormalizer {
  static normalizeText(text) {
    return String(text || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }
}

class SiteThemeController {
  constructor(pageSlug) {
    this.pageSlug = pageSlug;
    this.storageKey = "company-marketcap-theme-preference";
    this.preferenceOrder = ["system", "light", "dark"];
    this.preferenceLabels = { system: "System", light: "Light", dark: "Dark" };
    this.themeColors = { light: "#F1F4F0", dark: "#121714" };
    this.toggleButton = document.getElementById(`${pageSlug}-theme-toggle-button`);
    this.toggleLabel = document.getElementById(`${pageSlug}-theme-toggle-label`);
    this.themeColorMetaElements = document.querySelectorAll("meta[name='theme-color']");
    this.systemDarkQuery = window.matchMedia("(prefers-color-scheme: dark)");
    this.currentPreference = this.readStoredPreference();
  }

  initialize() {
    this.applyThemePreference(this.currentPreference);
    this.bindToggleButton();
    this.listenToSystemThemeChanges();
  }

  readStoredPreference() {
    try {
      const storedPreference = window.localStorage.getItem(this.storageKey);
      return this.preferenceOrder.includes(storedPreference) ? storedPreference : "system";
    } catch (error) {
      return "system";
    }
  }

  saveStoredPreference(preference) {
    try {
      if (preference === "system") {
        window.localStorage.removeItem(this.storageKey);
      } else {
        window.localStorage.setItem(this.storageKey, preference);
      }
    } catch (error) {
      /* Storage can be blocked; the theme still applies for this visit. */
    }
  }

  resolveTheme(preference) {
    if (preference === "system") {
      return this.systemDarkQuery.matches ? "dark" : "light";
    }
    return preference;
  }

  getNextPreference(preference) {
    const currentIndex = this.preferenceOrder.indexOf(preference);
    return this.preferenceOrder[(currentIndex + 1) % this.preferenceOrder.length];
  }

  applyThemePreference(preference) {
    const resolvedTheme = this.resolveTheme(preference);
    const rootElement = document.documentElement;

    rootElement.classList.toggle("dark", resolvedTheme === "dark");
    rootElement.style.colorScheme = resolvedTheme;
    rootElement.dataset.themePreference = preference;
    this.themeColorMetaElements.forEach((metaElement) => {
      metaElement.setAttribute("content", this.themeColors[resolvedTheme]);
    });
    this.updateToggleButton(preference);
  }

  updateToggleButton(preference) {
    if (!this.toggleButton) {
      return;
    }
    const nextPreference = this.getNextPreference(preference);
    this.toggleButton.dataset.themeState = preference;
    this.toggleButton.setAttribute(
      "aria-label",
      `Theme: ${this.preferenceLabels[preference]}. Switch to ${this.preferenceLabels[nextPreference].toLowerCase()} theme`
    );
    this.toggleButton.querySelectorAll("[data-theme-icon]").forEach((iconElement) => {
      iconElement.hidden = iconElement.dataset.themeIcon !== preference;
    });
    if (this.toggleLabel) {
      this.toggleLabel.textContent = this.preferenceLabels[preference];
    }
  }

  bindToggleButton() {
    if (!this.toggleButton) {
      return;
    }
    this.toggleButton.addEventListener("click", () => this.cycleThemePreference());
  }

  cycleThemePreference() {
    this.currentPreference = this.getNextPreference(this.currentPreference);
    this.saveStoredPreference(this.currentPreference);
    this.applyThemePreference(this.currentPreference);
  }

  listenToSystemThemeChanges() {
    this.systemDarkQuery.addEventListener("change", () => {
      if (this.currentPreference === "system") {
        this.applyThemePreference("system");
      }
    });
  }
}

class SiteMobileSidebarController {
  constructor(pageSlug) {
    this.pageSlug = pageSlug;
    this.sidebarElement = document.getElementById(`${pageSlug}-sidebar`);
    this.openButton = document.getElementById(`${pageSlug}-sidebar-open-button`);
    this.closeButton = document.getElementById(`${pageSlug}-sidebar-close-button`);
    this.overlayElement = document.getElementById(`${pageSlug}-sidebar-overlay`);
    this.desktopQuery = window.matchMedia("(min-width: 64rem)");
  }

  initialize() {
    if (!this.sidebarElement) {
      return;
    }
    this.bindControls();
    this.syncWithViewport();
    this.desktopQuery.addEventListener("change", () => this.syncWithViewport());
  }

  bindControls() {
    if (this.openButton) {
      this.openButton.addEventListener("click", () => this.openSidebar());
    }
    if (this.closeButton) {
      this.closeButton.addEventListener("click", () => this.closeSidebar(true));
    }
    if (this.overlayElement) {
      this.overlayElement.addEventListener("click", () => this.closeSidebar(true));
    }
    document.addEventListener("keydown", (event) => this.handleEscapeKey(event));
  }

  isSidebarOpen() {
    return this.sidebarElement.dataset.open === "true";
  }

  openSidebar() {
    this.sidebarElement.dataset.open = "true";
    this.sidebarElement.removeAttribute("inert");
    this.overlayElement.hidden = false;
    this.openButton.setAttribute("aria-expanded", "true");
    document.body.classList.add("overflow-hidden");
    if (this.closeButton) {
      this.closeButton.focus();
    }
  }

  closeSidebar(shouldReturnFocus) {
    this.sidebarElement.dataset.open = "false";
    this.overlayElement.hidden = true;
    this.openButton.setAttribute("aria-expanded", "false");
    document.body.classList.remove("overflow-hidden");
    if (!this.desktopQuery.matches) {
      this.sidebarElement.setAttribute("inert", "");
    }
    if (shouldReturnFocus) {
      this.openButton.focus();
    }
  }

  handleEscapeKey(event) {
    if (event.key === "Escape" && this.isSidebarOpen()) {
      event.preventDefault();
      this.closeSidebar(true);
    }
  }

  syncWithViewport() {
    if (this.desktopQuery.matches) {
      this.sidebarElement.removeAttribute("inert");
      this.sidebarElement.dataset.open = "false";
      this.overlayElement.hidden = true;
      document.body.classList.remove("overflow-hidden");
      return;
    }
    if (!this.isSidebarOpen()) {
      this.sidebarElement.setAttribute("inert", "");
    }
  }
}

class SiteCalculatorSearchController {
  constructor(pageSlug, searchKey, calculatorIndex) {
    this.searchKey = searchKey;
    this.idPrefix = `${pageSlug}-${searchKey}-search`;
    this.formElement = document.getElementById(`${this.idPrefix}-form`);
    this.inputElement = document.getElementById(`${this.idPrefix}-input`);
    this.resultsElement = document.getElementById(`${this.idPrefix}-results`);
    this.statusElement = document.getElementById(`${this.idPrefix}-status`);
    this.calculatorIndex = calculatorIndex;
    this.maximumResults = 8;
    this.currentResults = [];
  }

  initialize() {
    if (!this.formElement || !this.inputElement || !this.resultsElement) {
      return;
    }
    this.inputElement.addEventListener("input", () => this.handleSearchInput());
    this.inputElement.addEventListener("keydown", (event) => this.handleInputKeydown(event));
    this.resultsElement.addEventListener("keydown", (event) => this.handleResultsKeydown(event));
    this.formElement.addEventListener("submit", (event) => this.handleSearchSubmit(event));
    document.addEventListener("click", (event) => this.handleOutsideClick(event));
    this.prefillFromQueryString();
  }

  updateCalculatorIndex(calculatorIndex) {
    this.calculatorIndex = calculatorIndex;
    if (SiteTextNormalizer.normalizeText(this.inputElement.value)) {
      this.handleSearchInput();
    }
  }

  prefillFromQueryString() {
    if (this.formElement.dataset.searchPrefill !== "true") {
      return;
    }
    const queryValue = new URLSearchParams(window.location.search).get("q");
    if (queryValue) {
      this.inputElement.value = queryValue;
      this.handleSearchInput();
    }
  }

  handleSearchInput() {
    const queryText = this.inputElement.value;
    if (!SiteTextNormalizer.normalizeText(queryText)) {
      this.currentResults = [];
      this.hideResults();
      this.updateStatus("");
      return;
    }
    this.currentResults = this.findMatchingCalculators(queryText);
    this.renderResults(queryText);
  }

  findMatchingCalculators(queryText) {
    const searchTerms = SiteTextNormalizer.normalizeText(queryText).split(" ").filter(Boolean);

    return this.calculatorIndex
      .map((calculatorEntry) => ({ calculatorEntry, score: this.scoreCalculator(calculatorEntry, searchTerms) }))
      .filter((scoredEntry) => scoredEntry.score > 0)
      .sort((first, second) => second.score - first.score || first.calculatorEntry.name.localeCompare(second.calculatorEntry.name))
      .slice(0, this.maximumResults)
      .map((scoredEntry) => scoredEntry.calculatorEntry);
  }

  scoreCalculator(calculatorEntry, searchTerms) {
    let score = 0;
    for (const searchTerm of searchTerms) {
      if (calculatorEntry.normalizedName.startsWith(searchTerm)) {
        score += 3;
      } else if (calculatorEntry.nameWords.some((word) => word.startsWith(searchTerm))) {
        score += 2;
      } else if (calculatorEntry.normalizedName.includes(searchTerm)) {
        score += 1;
      } else if (calculatorEntry.normalizedCategory.includes(searchTerm)) {
        score += 0.5;
      } else {
        return 0;
      }
    }
    return score;
  }

  renderResults(queryText) {
    this.resultsElement.replaceChildren();

    if (this.currentResults.length === 0) {
      const emptyItem = document.createElement("li");
      emptyItem.className = "search-result-empty";
      emptyItem.textContent = `No calculators match "${queryText.trim()}". Try a shorter word, like "loan" or "BMI".`;
      this.resultsElement.append(emptyItem);
      this.updateStatus("No calculators found.");
      this.showResults();
      return;
    }

    this.currentResults.forEach((calculatorEntry, resultIndex) => {
      const listItem = document.createElement("li");
      const resultLink = document.createElement("a");
      const nameSpan = document.createElement("span");
      const categorySpan = document.createElement("span");

      resultLink.href = calculatorEntry.url;
      resultLink.id = `${this.idPrefix}-result-${resultIndex}`;
      resultLink.className = "search-result-link";
      resultLink.dataset.searchResultIndex = String(resultIndex);
      nameSpan.textContent = calculatorEntry.name;
      categorySpan.className = "search-result-category";
      categorySpan.textContent = calculatorEntry.category;

      resultLink.append(nameSpan, categorySpan);
      listItem.append(resultLink);
      this.resultsElement.append(listItem);
    });

    const countLabel = this.currentResults.length === 1 ? "1 calculator found" : `${this.currentResults.length} calculators found`;
    this.updateStatus(`${countLabel}. Press the down arrow to browse them.`);
    this.showResults();
  }

  showResults() {
    this.resultsElement.hidden = false;
  }

  hideResults() {
    this.resultsElement.hidden = true;
  }

  updateStatus(message) {
    if (this.statusElement) {
      this.statusElement.textContent = message;
    }
  }

  getResultLinks() {
    return Array.from(this.resultsElement.querySelectorAll("[data-search-result-index]"));
  }

  handleInputKeydown(event) {
    if (event.key === "ArrowDown") {
      const firstLink = this.getResultLinks()[0];
      if (firstLink) {
        event.preventDefault();
        firstLink.focus();
      }
    } else if (event.key === "Escape") {
      this.hideResults();
    }
  }

  handleResultsKeydown(event) {
    const resultLinks = this.getResultLinks();
    const currentIndex = resultLinks.indexOf(document.activeElement);

    if (event.key === "ArrowDown" && currentIndex < resultLinks.length - 1) {
      event.preventDefault();
      resultLinks[currentIndex + 1].focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (currentIndex <= 0) {
        this.inputElement.focus();
      } else {
        resultLinks[currentIndex - 1].focus();
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      this.hideResults();
      this.inputElement.focus();
    }
  }

  handleSearchSubmit(event) {
    event.preventDefault();
    this.handleSearchInput();
    if (this.currentResults.length > 0) {
      window.location.href = this.currentResults[0].url;
    }
  }

  handleOutsideClick(event) {
    if (!this.formElement.contains(event.target)) {
      this.hideResults();
    }
  }
}

class SiteApplication {
  constructor() {
    this.pageSlug = document.body.dataset.pageSlug;
    this.searchIndexUrl = "/assets/data/calculator-search-index.json";
    this.searchControllers = [];
  }

  initialize() {
    new SiteThemeController(this.pageSlug).initialize();
    new SiteMobileSidebarController(this.pageSlug).initialize();
    this.initializeCalculatorSearches();
    this.updateFooterYear();
  }

  createIndexEntry(entryName, entryCategory, entryUrl) {
    const normalizedName = SiteTextNormalizer.normalizeText(entryName);
    return {
      name: entryName,
      category: entryCategory,
      url: entryUrl,
      normalizedName,
      nameWords: normalizedName.split(" "),
      normalizedCategory: SiteTextNormalizer.normalizeText(entryCategory),
    };
  }

  buildCalculatorIndex(searchIndexEntries = []) {
    const calculatorsByUrl = new Map();

    document.querySelectorAll("a[data-calculator-name]").forEach((calculatorLink) => {
      const calculatorUrl = calculatorLink.getAttribute("href");
      if (!calculatorsByUrl.has(calculatorUrl)) {
        calculatorsByUrl.set(
          calculatorUrl,
          this.createIndexEntry(calculatorLink.dataset.calculatorName, calculatorLink.dataset.categoryName || "", calculatorUrl)
        );
      }
    });

    searchIndexEntries.forEach((searchIndexEntry) => {
      if (!calculatorsByUrl.has(searchIndexEntry.url)) {
        calculatorsByUrl.set(
          searchIndexEntry.url,
          this.createIndexEntry(searchIndexEntry.name, searchIndexEntry.category || "", searchIndexEntry.url)
        );
      }
    });
    return Array.from(calculatorsByUrl.values());
  }

  async loadCalculatorSearchIndex() {
    try {
      const response = await fetch(this.searchIndexUrl, { cache: "force-cache" });
      if (!response.ok) {
        return [];
      }
      const searchIndexEntries = await response.json();
      return Array.isArray(searchIndexEntries) ? searchIndexEntries : [];
    } catch (error) {
      return [];
    }
  }

  initializeCalculatorSearches() {
    const pageIndex = this.buildCalculatorIndex();
    document.querySelectorAll("form[data-search-key]").forEach((searchForm) => {
      const searchController = new SiteCalculatorSearchController(this.pageSlug, searchForm.dataset.searchKey, pageIndex);
      searchController.initialize();
      this.searchControllers.push(searchController);
    });

    this.loadCalculatorSearchIndex().then((searchIndexEntries) => {
      const fullIndex = this.buildCalculatorIndex(searchIndexEntries);
      this.searchControllers.forEach((searchController) => searchController.updateCalculatorIndex(fullIndex));
    });
  }

  updateFooterYear() {
    const footerYearElement = document.getElementById(`${this.pageSlug}-footer-year`);
    if (footerYearElement) {
      footerYearElement.textContent = String(new Date().getFullYear());
    }
  }
}

new SiteApplication().initialize();
