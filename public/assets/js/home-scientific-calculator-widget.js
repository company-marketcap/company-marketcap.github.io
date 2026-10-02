/*
 * File: assets/js/home-scientific-calculator-widget.js
 * Scientific calculator used on the home page.
 * Every element is looked up by its namespaced id: `${pageSlug}-${calculatorKey}-<part>`.
 */

class ScientificCalculatorExpressionParser {
  constructor() {
    this.functionTokens = ["sin⁻¹(", "cos⁻¹(", "tan⁻¹(", "sin(", "cos(", "tan(", "ln(", "log(", "√(", "∛("];
    this.constantTokens = ["Ans", "π", "e"];
    this.postfixTokens = ["⁻¹", "²", "³", "!", "%"];
    this.operatorTokens = ["ʸ√", "+", "−", "-", "×", "*", "÷", "/", "^"];
    this.operatorAliases = { "-": "−", "*": "×", "/": "÷" };
    this.resetParserState();
  }

  resetParserState() {
    this.tokens = [];
    this.position = 0;
    this.angleMode = "degrees";
    this.lastAnswer = 0;
  }

  evaluateExpression(expressionText, options = {}) {
    this.tokens = this.tokenizeExpression(expressionText);
    this.position = 0;
    this.angleMode = options.angleMode === "radians" ? "radians" : "degrees";
    this.lastAnswer = Number.isFinite(options.lastAnswer) ? options.lastAnswer : 0;

    if (this.tokens.length === 0) {
      throw new Error("Enter a calculation first.");
    }

    const value = this.parseAdditiveExpression();

    if (this.position < this.tokens.length) {
      throw new Error("Check your expression: a symbol is out of place.");
    }
    if (Number.isNaN(value)) {
      throw new Error("This calculation has no real answer.");
    }
    if (!Number.isFinite(value)) {
      throw new Error("The answer is too large to show.");
    }
    return value;
  }

  tokenizeExpression(expressionText) {
    const tokens = [];
    const normalizedText = String(expressionText).replace(/\s+/g, "");
    let index = 0;

    while (index < normalizedText.length) {
      const remainingText = normalizedText.slice(index);
      const numberMatch = remainingText.match(/^(\d+\.?\d*|\.\d+)(E[+\-−]?\d+)?/);

      if (numberMatch) {
        tokens.push({ type: "number", value: Number(numberMatch[0].replace("−", "-")) });
        index += numberMatch[0].length;
        continue;
      }

      const leadingToken = this.findLeadingToken(remainingText);
      if (!leadingToken) {
        throw new Error(`"${remainingText[0]}" is not a symbol this calculator understands.`);
      }
      tokens.push(leadingToken.token);
      index += leadingToken.length;
    }
    return tokens;
  }

  findLeadingToken(remainingText) {
    const functionToken = this.functionTokens.find((token) => remainingText.startsWith(token));
    if (functionToken) {
      return { token: { type: "function", value: functionToken.slice(0, -1) }, length: functionToken.length };
    }

    const constantToken = this.constantTokens.find((token) => remainingText.startsWith(token));
    if (constantToken) {
      return { token: { type: "constant", value: constantToken }, length: constantToken.length };
    }

    const postfixToken = this.postfixTokens.find((token) => remainingText.startsWith(token));
    if (postfixToken) {
      return { token: { type: "postfix", value: postfixToken }, length: postfixToken.length };
    }

    const operatorToken = this.operatorTokens.find((token) => remainingText.startsWith(token));
    if (operatorToken) {
      const normalizedOperator = this.operatorAliases[operatorToken] || operatorToken;
      return { token: { type: "operator", value: normalizedOperator }, length: operatorToken.length };
    }

    if (remainingText[0] === "(" || remainingText[0] === ")") {
      return { token: { type: "parenthesis", value: remainingText[0] }, length: 1 };
    }
    return null;
  }

  peekToken() {
    return this.tokens[this.position];
  }

  consumeToken() {
    const token = this.tokens[this.position];
    this.position += 1;
    return token;
  }

  isOperatorToken(token, symbol) {
    return Boolean(token) && token.type === "operator" && token.value === symbol;
  }

  startsOperand(token) {
    if (!token) {
      return false;
    }
    return ["number", "constant", "function"].includes(token.type) || (token.type === "parenthesis" && token.value === "(");
  }

  parseAdditiveExpression() {
    let value = this.parseMultiplicativeExpression();

    while (this.isOperatorToken(this.peekToken(), "+") || this.isOperatorToken(this.peekToken(), "−")) {
      const operator = this.consumeToken().value;
      const rightValue = this.parseMultiplicativeExpression();
      value = operator === "+" ? value + rightValue : value - rightValue;
    }
    return value;
  }

  parseMultiplicativeExpression() {
    let value = this.parseUnaryExpression();

    while (true) {
      const nextToken = this.peekToken();

      if (this.isOperatorToken(nextToken, "×")) {
        this.consumeToken();
        value *= this.parseUnaryExpression();
      } else if (this.isOperatorToken(nextToken, "÷")) {
        this.consumeToken();
        const divisor = this.parseUnaryExpression();
        if (divisor === 0) {
          throw new Error("You can't divide by zero.");
        }
        value /= divisor;
      } else if (this.startsOperand(nextToken)) {
        value *= this.parsePowerExpression();
      } else {
        break;
      }
    }
    return value;
  }

  parseUnaryExpression() {
    if (this.isOperatorToken(this.peekToken(), "+")) {
      this.consumeToken();
      return this.parseUnaryExpression();
    }
    if (this.isOperatorToken(this.peekToken(), "−")) {
      this.consumeToken();
      return -this.parseUnaryExpression();
    }
    return this.parsePowerExpression();
  }

  parsePowerExpression() {
    const baseValue = this.parsePostfixExpression();

    if (this.isOperatorToken(this.peekToken(), "^")) {
      this.consumeToken();
      return this.computePower(baseValue, this.parseUnaryExpression());
    }
    if (this.isOperatorToken(this.peekToken(), "ʸ√")) {
      this.consumeToken();
      return this.computeNthRoot(this.parseUnaryExpression(), baseValue);
    }
    return baseValue;
  }

  parsePostfixExpression() {
    let value = this.parsePrimaryExpression();

    while (this.peekToken() && this.peekToken().type === "postfix") {
      value = this.applyPostfixOperator(this.consumeToken().value, value);
    }
    return value;
  }

  parsePrimaryExpression() {
    const token = this.consumeToken();

    if (!token) {
      throw new Error("Your expression is unfinished. Add a number to complete it.");
    }
    if (token.type === "number") {
      return token.value;
    }
    if (token.type === "constant") {
      return this.resolveConstant(token.value);
    }
    if (token.type === "parenthesis" && token.value === "(") {
      const innerValue = this.parseAdditiveExpression();
      this.consumeClosingParenthesis();
      return innerValue;
    }
    if (token.type === "function") {
      const argumentValue = this.parseAdditiveExpression();
      this.consumeClosingParenthesis();
      return this.applyFunction(token.value, argumentValue);
    }
    throw new Error("Check your expression: an operator is missing a number.");
  }

  consumeClosingParenthesis() {
    const nextToken = this.peekToken();
    if (!nextToken) {
      return;
    }
    if (nextToken.type === "parenthesis" && nextToken.value === ")") {
      this.consumeToken();
      return;
    }
    throw new Error("A closing bracket is missing.");
  }

  resolveConstant(constantName) {
    if (constantName === "π") {
      return Math.PI;
    }
    if (constantName === "e") {
      return Math.E;
    }
    return this.lastAnswer;
  }

  applyPostfixOperator(operator, value) {
    switch (operator) {
      case "!":
        return this.computeFactorial(value);
      case "%":
        return value / 100;
      case "²":
        return value * value;
      case "³":
        return value * value * value;
      case "⁻¹":
        if (value === 0) {
          throw new Error("You can't divide by zero.");
        }
        return 1 / value;
      default:
        throw new Error(`"${operator}" is not supported.`);
    }
  }

  applyFunction(functionName, argumentValue) {
    switch (functionName) {
      case "sin":
        return this.cleanTrigonometricResult(Math.sin(this.convertAngleToRadians(argumentValue)));
      case "cos":
        return this.cleanTrigonometricResult(Math.cos(this.convertAngleToRadians(argumentValue)));
      case "tan":
        this.assertTangentIsDefined(argumentValue);
        return this.cleanTrigonometricResult(Math.tan(this.convertAngleToRadians(argumentValue)));
      case "sin⁻¹":
        this.assertInverseTrigDomain(argumentValue, "sin⁻¹");
        return this.convertRadiansToAngle(Math.asin(argumentValue));
      case "cos⁻¹":
        this.assertInverseTrigDomain(argumentValue, "cos⁻¹");
        return this.convertRadiansToAngle(Math.acos(argumentValue));
      case "tan⁻¹":
        return this.convertRadiansToAngle(Math.atan(argumentValue));
      case "ln":
        this.assertPositiveLogarithmInput(argumentValue, "ln");
        return Math.log(argumentValue);
      case "log":
        this.assertPositiveLogarithmInput(argumentValue, "log");
        return Math.log10(argumentValue);
      case "√":
        if (argumentValue < 0) {
          throw new Error("Square root needs a number of 0 or more.");
        }
        return Math.sqrt(argumentValue);
      case "∛":
        return Math.cbrt(argumentValue);
      default:
        throw new Error(`"${functionName}" is not supported.`);
    }
  }

  convertAngleToRadians(angleValue) {
    return this.angleMode === "degrees" ? (angleValue * Math.PI) / 180 : angleValue;
  }

  convertRadiansToAngle(radianValue) {
    return this.angleMode === "degrees" ? (radianValue * 180) / Math.PI : radianValue;
  }

  cleanTrigonometricResult(value) {
    return Math.abs(value) < 1e-12 ? 0 : value;
  }

  assertTangentIsDefined(angleValue) {
    if (this.angleMode !== "degrees") {
      return;
    }
    const normalizedAngle = ((angleValue % 180) + 180) % 180;
    if (Math.abs(normalizedAngle - 90) < 1e-10) {
      throw new Error("tan is undefined at 90° and every 180° after it.");
    }
  }

  assertInverseTrigDomain(value, functionLabel) {
    if (value < -1 || value > 1) {
      throw new Error(`${functionLabel} needs a number between −1 and 1.`);
    }
  }

  assertPositiveLogarithmInput(value, functionLabel) {
    if (value <= 0) {
      throw new Error(`${functionLabel} needs a number greater than 0.`);
    }
  }

  computePower(baseValue, exponentValue) {
    const result = Math.pow(baseValue, exponentValue);
    if (Number.isNaN(result)) {
      throw new Error("This power has no real answer.");
    }
    return result;
  }

  computeNthRoot(radicandValue, degreeValue) {
    if (degreeValue === 0) {
      throw new Error("The root degree can't be 0.");
    }
    if (radicandValue < 0) {
      if (Number.isInteger(degreeValue) && Math.abs(degreeValue) % 2 === 1) {
        return -Math.pow(-radicandValue, 1 / degreeValue);
      }
      throw new Error("Even roots of negative numbers have no real answer.");
    }
    return Math.pow(radicandValue, 1 / degreeValue);
  }

  computeFactorial(value) {
    if (!Number.isInteger(value) || value < 0) {
      throw new Error("Factorial needs a whole number of 0 or more.");
    }
    if (value > 170) {
      throw new Error("That factorial is too large to show.");
    }
    let result = 1;
    for (let multiplier = 2; multiplier <= value; multiplier += 1) {
      result *= multiplier;
    }
    return result;
  }

  formatNumberForDisplay(value) {
    if (value === 0 || Object.is(value, -0)) {
      return "0";
    }
    const absoluteValue = Math.abs(value);

    if (absoluteValue >= 1e15 || absoluteValue < 1e-6) {
      const [mantissa, exponent] = value.toExponential(9).split("e");
      const trimmedMantissa = mantissa.includes(".") ? mantissa.replace(/\.?0+$/, "") : mantissa;
      return `${trimmedMantissa}E${Number(exponent)}`.replace(/-/g, "−");
    }
    return String(Number(value.toPrecision(12))).replace(/-/g, "−");
  }
}

class ScientificCalculatorWidget {
  constructor(rootElement) {
    this.rootElement = rootElement;
    this.pageSlug = rootElement.dataset.pageSlug;
    this.calculatorKey = rootElement.dataset.calculatorKey;
    this.idPrefix = `${this.pageSlug}-${this.calculatorKey}`;

    this.expressionElement = this.getNamespacedElement("expression");
    this.resultElement = this.getNamespacedElement("result");
    this.announcerElement = this.getNamespacedElement("announcer");
    this.historyListElement = this.getNamespacedElement("history-list");
    this.historyEmptyElement = this.getNamespacedElement("history-empty");
    this.historyClearButton = this.getNamespacedElement("history-clear-button");

    this.parser = new ScientificCalculatorExpressionParser();
    this.expressionText = "";
    this.lastAnswer = 0;
    this.hasJustEvaluated = false;
    this.historyEntries = [];
    this.maximumHistoryEntries = 8;
    this.keyboardButtonMap = new Map();

    this.multiCharacterTokens = ["sin⁻¹(", "cos⁻¹(", "tan⁻¹(", "sin(", "cos(", "tan(", "ln(", "log(", "√(", "∛(", "Ans", "ʸ√", "⁻¹"];
    this.continuationTokens = ["+", "−", "×", "÷", "^", "ʸ√", "²", "³", "⁻¹", "!", "%"];
    this.operandEndingPattern = /([\d.)πe²³!%]|Ans|⁻¹)$/;
  }

  getNamespacedElement(partName) {
    return document.getElementById(`${this.idPrefix}-${partName}`);
  }

  initialize() {
    this.bindKeypadButtons();
    this.bindAngleModeInputs();
    this.buildKeyboardButtonMap();
    this.bindKeyboardShortcuts();
    this.bindHistoryControls();
    this.renderDisplay();
    this.renderHistory();
  }

  bindKeypadButtons() {
    this.rootElement.addEventListener("click", (event) => {
      const keyButton = event.target.closest("[data-calculator-action]");
      if (!keyButton || !this.rootElement.contains(keyButton)) {
        return;
      }
      this.handleCalculatorAction(keyButton.dataset.calculatorAction, keyButton.dataset.calculatorValue || "");
    });
  }

  bindAngleModeInputs() {
    this.getAngleModeInputs().forEach((inputElement) => {
      inputElement.addEventListener("change", () => this.renderDisplay());
    });
  }

  getAngleModeInputs() {
    return this.rootElement.querySelectorAll(`input[name="${this.idPrefix}-angle-mode"]`);
  }

  getAngleMode() {
    const checkedInput = this.rootElement.querySelector(`input[name="${this.idPrefix}-angle-mode"]:checked`);
    return checkedInput ? checkedInput.value : "degrees";
  }

  handleCalculatorAction(action, value) {
    switch (action) {
      case "insert":
        this.insertToken(value);
        break;
      case "clear":
        this.clearCalculator();
        break;
      case "backspace":
        this.deleteLastToken();
        break;
      case "evaluate":
        this.evaluateCurrentExpression();
        break;
      case "toggle-sign":
        this.toggleSignOfLastNumber();
        break;
      case "random":
        this.insertRandomNumber();
        break;
      default:
        break;
    }
  }

  insertToken(tokenText) {
    if (this.hasJustEvaluated) {
      this.expressionText = this.continuationTokens.includes(tokenText) ? "Ans" : "";
      this.hasJustEvaluated = false;
    }
    this.expressionText += tokenText;
    this.renderDisplay();
  }

  insertOperandWithImplicitMultiplication(operandText) {
    if (this.hasJustEvaluated) {
      this.expressionText = "";
      this.hasJustEvaluated = false;
    }
    if (this.operandEndingPattern.test(this.expressionText)) {
      this.expressionText += "×";
    }
    this.expressionText += operandText;
    this.renderDisplay();
  }

  insertRandomNumber() {
    this.insertOperandWithImplicitMultiplication(Math.random().toFixed(6));
  }

  clearCalculator() {
    this.expressionText = "";
    this.hasJustEvaluated = false;
    this.renderDisplay();
    this.announceMessage("Cleared.");
  }

  deleteLastToken() {
    if (this.hasJustEvaluated) {
      this.clearCalculator();
      return;
    }
    const trailingToken = this.multiCharacterTokens.find((token) => this.expressionText.endsWith(token));
    const removeLength = trailingToken ? trailingToken.length : 1;
    this.expressionText = this.expressionText.slice(0, Math.max(0, this.expressionText.length - removeLength));
    this.renderDisplay();
  }

  toggleSignOfLastNumber() {
    if (this.hasJustEvaluated) {
      this.expressionText = "Ans";
      this.hasJustEvaluated = false;
    }
    const trailingOperandMatch = this.expressionText.match(/(\d*\.?\d+(?:E[−-]?\d+)?|\d+\.|Ans|π|e)$/);

    if (!trailingOperandMatch) {
      this.expressionText += "−";
      this.renderDisplay();
      return;
    }

    const textBeforeOperand = this.expressionText.slice(0, trailingOperandMatch.index);
    const operandText = trailingOperandMatch[0];
    const textBeforeMinus = textBeforeOperand.slice(0, -1);
    const minusIsUnary = textBeforeOperand.endsWith("−") && this.isUnaryMinusPosition(textBeforeMinus);

    this.expressionText = minusIsUnary
      ? `${textBeforeMinus}${operandText}`
      : `${textBeforeOperand}−${operandText}`;
    this.renderDisplay();
  }

  isUnaryMinusPosition(textBeforeMinus) {
    return textBeforeMinus === "" || /[+−×÷^(√]$/.test(textBeforeMinus);
  }

  evaluateCurrentExpression() {
    if (!this.expressionText.trim() || this.hasJustEvaluated) {
      return;
    }
    try {
      const value = this.parser.evaluateExpression(this.expressionText, {
        angleMode: this.getAngleMode(),
        lastAnswer: this.lastAnswer,
      });
      const formattedValue = this.parser.formatNumberForDisplay(value);

      this.addHistoryEntry(this.expressionText, formattedValue);
      this.lastAnswer = value;
      this.hasJustEvaluated = true;
      this.expressionElement.textContent = `${this.expressionText} =`;
      this.showResult(formattedValue, "final");
      this.announceMessage(`Answer: ${formattedValue}`);
    } catch (error) {
      this.showResult(error.message, "error");
      this.announceMessage(error.message);
    }
  }

  renderDisplay() {
    this.expressionElement.textContent = this.expressionText || "\u00A0";

    if (!this.expressionText) {
      this.showResult("0", "final");
      return;
    }
    try {
      const previewValue = this.parser.evaluateExpression(this.expressionText, {
        angleMode: this.getAngleMode(),
        lastAnswer: this.lastAnswer,
      });
      this.showResult(this.parser.formatNumberForDisplay(previewValue), "preview");
    } catch (error) {
      this.showResult("", "preview");
    }
  }

  showResult(resultText, resultState) {
    this.resultElement.textContent = resultText || "\u00A0";
    this.resultElement.dataset.state = resultState;
  }

  announceMessage(message) {
    if (this.announcerElement) {
      this.announcerElement.textContent = message;
    }
  }

  buildKeyboardButtonMap() {
    this.rootElement.querySelectorAll("[data-keyboard-key]").forEach((keyButton) => {
      keyButton.dataset.keyboardKey.split(" ").forEach((keyName) => {
        this.keyboardButtonMap.set(keyName, keyButton);
      });
    });
  }

  bindKeyboardShortcuts() {
    document.addEventListener("keydown", (event) => this.handleKeyboardInput(event));
  }

  handleKeyboardInput(event) {
    if (event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) {
      return;
    }
    const targetElement = event.target instanceof HTMLElement ? event.target : null;

    if (targetElement) {
      if (targetElement.closest("[data-keyboard-shortcuts='off']")) {
        return;
      }
      if (targetElement.matches("input:not([type='radio']), textarea, select, [contenteditable='true']")) {
        return;
      }
      if ((event.key === "Enter" || event.key === " ") && targetElement.matches("button, a, summary, input")) {
        return;
      }
    }

    const matchedButton = this.keyboardButtonMap.get(event.key);
    if (!matchedButton) {
      return;
    }
    event.preventDefault();
    matchedButton.click();
    this.flashPressedKey(matchedButton);
  }

  flashPressedKey(keyButton) {
    keyButton.classList.add("calc-key-pressed");
    window.setTimeout(() => keyButton.classList.remove("calc-key-pressed"), 120);
  }

  bindHistoryControls() {
    if (this.historyListElement) {
      this.historyListElement.addEventListener("click", (event) => {
        const historyButton = event.target.closest("[data-history-result]");
        if (historyButton) {
          this.insertHistoryResult(historyButton.dataset.historyResult);
        }
      });
    }
    if (this.historyClearButton) {
      this.historyClearButton.addEventListener("click", () => this.clearHistory());
    }
  }

  addHistoryEntry(expressionText, resultText) {
    this.historyEntries.unshift({ expressionText, resultText });
    this.historyEntries = this.historyEntries.slice(0, this.maximumHistoryEntries);
    this.renderHistory();
  }

  insertHistoryResult(resultText) {
    const operandText = resultText.startsWith("−") ? `(${resultText})` : resultText;
    this.insertOperandWithImplicitMultiplication(operandText);
  }

  clearHistory() {
    this.historyEntries = [];
    this.renderHistory();
    this.announceMessage("History cleared.");
  }

  renderHistory() {
    if (!this.historyListElement) {
      return;
    }
    this.historyListElement.replaceChildren();

    this.historyEntries.forEach((entry, entryIndex) => {
      const listItem = document.createElement("li");
      const historyButton = document.createElement("button");
      const expressionSpan = document.createElement("span");
      const resultSpan = document.createElement("span");

      historyButton.type = "button";
      historyButton.id = `${this.idPrefix}-history-entry-${entryIndex}`;
      historyButton.className = "history-entry-button";
      historyButton.dataset.historyResult = entry.resultText;
      historyButton.setAttribute("aria-label", `Use ${entry.resultText}, the answer to ${entry.expressionText}`);

      expressionSpan.className = "history-entry-expression";
      expressionSpan.textContent = `${entry.expressionText} =`;
      resultSpan.className = "history-entry-result";
      resultSpan.textContent = entry.resultText;

      historyButton.append(expressionSpan, resultSpan);
      listItem.append(historyButton);
      this.historyListElement.append(listItem);
    });

    const hasEntries = this.historyEntries.length > 0;
    if (this.historyEmptyElement) {
      this.historyEmptyElement.hidden = hasEntries;
    }
    if (this.historyClearButton) {
      this.historyClearButton.hidden = !hasEntries;
    }
  }
}

class ScientificCalculatorBootstrap {
  static initializeAllCalculators() {
    document.querySelectorAll("[data-component='scientific-calculator']").forEach((rootElement) => {
      new ScientificCalculatorWidget(rootElement).initialize();
    });
  }
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  ScientificCalculatorBootstrap.initializeAllCalculators();
}
