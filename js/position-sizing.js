// Position Sizing Calculator - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize the calculator
    initPositionSizingCalculator();

    // Setup smooth scrolling for anchors
    setupSmoothScrolling();

    // Setup share popup functionality
    setupSharePopup();
});

// Chart instance
let positionChart;

// Initialize position sizing calculator
function initPositionSizingCalculator() {
    const calculateBtn = document.getElementById('calculateBtn');

    if (calculateBtn) {
        calculateBtn.addEventListener('click', calculatePositionSize);
    }
}

// Set up smooth scrolling
function setupSmoothScrolling() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            const targetElement = document.querySelector(targetId);

            if (targetElement) {
                window.scrollTo({
                    top: targetElement.offsetTop - 70,
                    behavior: 'smooth'
                });
            }
        });
    });
}

// Setup share popup functionality
function setupSharePopup() {
    const shareBtn = document.getElementById('shareResultsBtn');

    if (shareBtn) {
        shareBtn.addEventListener('click', function() {
            // Create popup dynamically
            const popupHtml = `
                <div class="share-popup shadow-sm p-2 rounded" id="sharePopup">
                    <a class="text-decoration-none me-2"
                       href="https://twitter.com/intent/tweet?text=Check+out+this+Position+Sizing+Calculator!&url=${encodeURIComponent(window.location.href)}" target="_blank">
                        <i class="bi bi-twitter fs-4 text-info"></i>
                    </a>
                    <a class="text-decoration-none me-2"
                       href="https://www.linkedin.com/shareArticle?mini=true&url=${encodeURIComponent(window.location.href)}&title=Position+Sizing+Calculator" target="_blank">
                        <i class="bi bi-linkedin fs-4 text-primary"></i>
                    </a>
                    <a class="text-decoration-none"
                       href="https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(window.location.href)}" target="_blank">
                        <i class="bi bi-facebook fs-4 text-secondary"></i>
                    </a>
                </div>
            `;

            // Remove existing popup if it exists
            const existingPopup = document.getElementById('sharePopup');
            if (existingPopup) {
                existingPopup.remove();
            }

            // Add popup to DOM
            shareBtn.insertAdjacentHTML('beforebegin', popupHtml);

            // Position the popup
            const popup = document.getElementById('sharePopup');
            popup.style.left = `${shareBtn.offsetLeft}px`;

            // Hide popup when clicking outside
            document.addEventListener('click', function hidePopup(e) {
                if (!e.target.closest('#sharePopup') && e.target !== shareBtn) {
                    popup.remove();
                    document.removeEventListener('click', hidePopup);
                }
            });
        });
    }
}

// Calculate the position size based on risk parameters
function calculatePositionSize() {
    // Get input values
    const accountValue = parseFloat(document.getElementById('accountValue').value) || 100000;
    const riskPercentage = parseFloat(document.getElementById('riskPercentage').value) || 1;
    const maxPositionPercentage = parseFloat(document.getElementById('maxPositionPercentage').value) || 15;
    const entryPrice = parseFloat(document.getElementById('entryPrice').value) || 50;
    const stopLossPrice = parseFloat(document.getElementById('stopLossPrice').value) || 45;
    const commissionFee = parseFloat(document.getElementById('commissionFee').value) || 5;

    // Validate inputs
    if (accountValue <= 0 || riskPercentage <= 0 || maxPositionPercentage <= 0 ||
        entryPrice <= 0 || stopLossPrice <= 0 || stopLossPrice >= entryPrice) {
        alert('Please check your inputs. Make sure your stop-loss is below your entry price for a long position.');
        return;
    }

    // Calculate position metrics
    const riskAmount = (accountValue * (riskPercentage / 100));
    const lossPerShare = Math.abs(entryPrice - stopLossPrice);
    const stopLossPercentage = (lossPerShare / entryPrice) * 100;

    // Calculate optimal number of shares
    let optimalShares = Math.floor((riskAmount - commissionFee) / lossPerShare);

    // Check against maximum position constraint
    const maxPositionValue = accountValue * (maxPositionPercentage / 100);
    const positionValue = optimalShares * entryPrice;

    if (positionValue > maxPositionValue) {
        optimalShares = Math.floor(maxPositionValue / entryPrice);
    }

    // Recalculate final position metrics
    const finalPositionValue = optimalShares * entryPrice;
    const adjustedPositionValue = finalPositionValue + commissionFee;
    const accountPercentage = (finalPositionValue / accountValue) * 100;
    const rMultiple = riskAmount;

    // Update UI with results
    updateResultsUI({
        optimalShares,
        positionValue: finalPositionValue,
        accountPercentage,
        adjustedPositionValue,
        riskAmount,
        lossPerShare,
        stopLossPercentage,
        rMultiple
    });

    // Show results card
    document.getElementById('resultsCard').style.display = 'block';

    // Scroll to results after a short delay
    setTimeout(() => {
        document.getElementById('resultsCard').scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    }, 300);
}

// Format currency with appropriate suffix
function formatCurrency(value) {
    if (value >= 1_000_000) {
        return '$' + (value / 1_000_000).toFixed(2) + ' million';
    } else if (value >= 1_000) {
        return '$' + (value / 1_000).toFixed(2) + 'k';
    } else {
        return '$' + value.toFixed(2);
    }
}

// Format number with commas
function formatNumber(value) {
    return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Update the results UI
function updateResultsUI(results) {
    // Update position information
    document.getElementById('optimalShares').textContent = formatNumber(results.optimalShares);
    document.getElementById('positionValue').textContent = formatCurrency(results.positionValue);
    document.getElementById('accountPercentage').textContent = results.accountPercentage.toFixed(2) + '%';
    document.getElementById('adjustedPosition').textContent = formatCurrency(results.adjustedPositionValue);

    // Update risk information
    document.getElementById('riskAmount').textContent = formatCurrency(results.riskAmount);
    document.getElementById('lossPerShare').textContent = formatCurrency(results.lossPerShare);
    document.getElementById('stopLossPercentage').textContent = results.stopLossPercentage.toFixed(2) + '%';
    document.getElementById('rMultiple').textContent = formatCurrency(results.rMultiple);

    // Update chart
    updatePositionChart(results);
}

// Update or create position chart
function updatePositionChart(results) {
    const ctx = document.getElementById('positionChart').getContext('2d');

    // Destroy existing chart if it exists
    if (positionChart) {
        positionChart.destroy();
    }

    // Create data for chart
    const accountValue = parseFloat(document.getElementById('accountValue').value);
    const maxPositionValue = accountValue * (parseFloat(document.getElementById('maxPositionPercentage').value) / 100);

    // Create an array of potential position sizes
    const positionSizes = [];
    const maxShares = results.optimalShares * 2; // Go up to 2x the optimal for visualization

    for (let i = 0; i <= maxShares; i += Math.max(1, Math.floor(maxShares / 20))) {
        positionSizes.push(i);
    }

    // If optimal shares isn't in the array, add it
    if (!positionSizes.includes(results.optimalShares)) {
        positionSizes.push(results.optimalShares);
        // Sort the array
        positionSizes.sort((a, b) => a - b);
    }

    // Calculate risk for each position size
    const entryPrice = parseFloat(document.getElementById('entryPrice').value);
    const stopLossPrice = parseFloat(document.getElementById('stopLossPrice').value);
    const lossPerShare = Math.abs(entryPrice - stopLossPrice);

    const riskAmounts = positionSizes.map(shares =>
        (shares * lossPerShare / accountValue) * 100 // Risk as percentage of account
    );

    // Calculate position value percentages
    const positionPercentages = positionSizes.map(shares =>
        (shares * entryPrice / accountValue) * 100 // Position value as percentage of account
    );

    // Create the chart
    positionChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: positionSizes.map(shares => shares.toString()),
            datasets: [
                {
                    label: 'Risk (% of Account)',
                    data: riskAmounts,
                    borderColor: 'rgba(220, 53, 69, 1)',
                    backgroundColor: 'rgba(220, 53, 69, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                },
                {
                    label: 'Position Size (% of Account)',
                    data: positionPercentages,
                    borderColor: 'rgba(13, 110, 253, 1)',
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Risk vs. Position Size',
                    font: {
                        size: 16
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            label += context.parsed.y.toFixed(2) + '%';
                            return label;
                        }
                    }
                },
                annotation: {
                    annotations: {
                        optimalLine: {
                            type: 'line',
                            xMin: results.optimalShares,
                            xMax: results.optimalShares,
                            borderColor: 'rgba(40, 167, 69, 1)',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            label: {
                                content: 'Optimal Position',
                                enabled: true,
                                position: 'top'
                            }
                        },
                        riskLine: {
                            type: 'line',
                            yMin: parseFloat(document.getElementById('riskPercentage').value),
                            yMax: parseFloat(document.getElementById('riskPercentage').value),
                            borderColor: 'rgba(220, 53, 69, 1)',
                            borderWidth: 2,
                            borderDash: [5, 5],
                            label: {
                                content: 'Risk Limit',
                                enabled: true,
                                position: 'left'
                            }
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Percentage of Account'
                    },
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Number of Shares'
                    }
                }
            }
        }
    });

    // Manually add a vertical line to highlight optimal shares
    // Since the annotation plugin might not be available
    const optimalIndex = positionSizes.indexOf(results.optimalShares);
    if (optimalIndex !== -1) {
        const meta = positionChart.getDatasetMeta(0);
        const rect = positionChart.canvas.getBoundingClientRect();
        const point = meta.data[optimalIndex].getCenterPoint();

        ctx.save();
        ctx.beginPath();
        ctx.setLineDash([5, 5]);
        ctx.moveTo(point.x, 0);
        ctx.lineTo(point.x, rect.height);
        ctx.strokeStyle = 'rgba(40, 167, 69, 1)';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();
    }
}
