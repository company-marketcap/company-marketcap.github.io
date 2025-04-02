// Market Cap Insights - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize components
    initCalculator();

    // Set up smooth scrolling for anchors
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
});

// Growth chart instance
let growthChart;

// Calculator functionality
function initCalculator() {
    const calculateBtn = document.getElementById('calculateBtn');

    if (calculateBtn) {
        calculateBtn.addEventListener('click', performCalculation);
    }
}

function performCalculation() {
    // Get all input values
    const initialMarketCap = parseFloat(document.getElementById('initialMarketCap').value) || 1000000000;
    const annualGrowthRate = parseFloat(document.getElementById('annualGrowthRate').value) || 15;
    const revenueMultiple = parseFloat(document.getElementById('revenueMultiple').value) || 5;
    const industryPeRatio = parseFloat(document.getElementById('industryPeRatio').value) || 22;
    const initialInvestment = parseFloat(document.getElementById('initialInvestment').value) || 10000;
    const monthlyContribution = parseFloat(document.getElementById('monthlyContribution').value) || 500;
    const investmentYears = parseInt(document.getElementById('investmentYears').value) || 10;
    const reinvestDividends = document.getElementById('reinvestDividends').value === 'yes';

    // Validate inputs
    if (initialMarketCap <= 0 || annualGrowthRate < 0 || revenueMultiple <= 0 ||
        industryPeRatio <= 0 || initialInvestment < 0 || monthlyContribution < 0 ||
        investmentYears <= 0) {
        alert('Please enter valid positive values for all inputs.');
        return;
    }

    // Calculate market cap projections
    const projectedMarketCap = calculateProjectedMarketCap(initialMarketCap, annualGrowthRate, investmentYears);
    const cagr = annualGrowthRate; // In this simple model, we use the input growth rate as CAGR

    // Calculate revenue and earnings projections
    const initialRevenue = initialMarketCap / revenueMultiple;
    const projectedRevenue = projectedMarketCap / revenueMultiple;

    // Assuming a net margin of 15% for earnings calculation - this is a unique approach
    // We use a dynamic net margin that scales with growth rate to simulate maturing businesses
    const netMargin = 0.1 + (annualGrowthRate * 0.005); // Higher growth = higher margin
    const projectedEarnings = projectedRevenue * netMargin;

    // Calculate investment projections using our unique compound growth model
    const investmentResults = calculateInvestmentGrowth(
        initialInvestment,
        monthlyContribution,
        annualGrowthRate,
        investmentYears,
        reinvestDividends
    );

    // Update the UI with results
    updateResultsUI(
        projectedMarketCap,
        cagr,
        projectedRevenue,
        projectedEarnings,
        investmentResults,
        investmentYears,
        initialMarketCap,
        initialRevenue
    );

    // Show the results section
    document.getElementById('resultsCard').style.display = 'block';
    document.getElementById('resultsCard').classList.add('fade-in');

    // Scroll to results
    setTimeout(() => {
        document.getElementById('resultsCard').scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    }, 300);
}

// Calculate projected market cap based on initial value and growth rate
function calculateProjectedMarketCap(initialMarketCap, growthRate, years) {
    return initialMarketCap * Math.pow(1 + (growthRate / 100), years);
}

// Calculate investment growth with market cap correlation
function calculateInvestmentGrowth(initialInvestment, monthlyContribution, growthRate, years, reinvestDividends) {
    // Convert annual growth rate to monthly
    const monthlyRate = Math.pow(1 + (growthRate / 100), 1/12) - 1;

    let totalValue = initialInvestment;
    let totalContributions = initialInvestment;
    const yearlyValues = [initialInvestment];

    // Unique factor: We'll add a volatility factor that simulates market ups and downs
    // This creates a more realistic projection than simple compound interest
    const volatilityFactor = growthRate > 20 ? 0.2 : (growthRate > 10 ? 0.15 : 0.1);

    // Calculate monthly compounding
    for (let month = 1; month <= years * 12; month++) {
        // Add monthly contribution
        totalValue += monthlyContribution;
        totalContributions += monthlyContribution;

        // Apply monthly growth rate with random volatility
        const monthVolatility = 1 + ((Math.random() * 2 - 1) * volatilityFactor * monthlyRate);
        const adjustedMonthlyRate = monthlyRate * monthVolatility;

        totalValue *= (1 + adjustedMonthlyRate);

        // Add dividend effect quarterly (assuming 0.5% quarterly dividend)
        if (month % 3 === 0) {
            const dividendAmount = totalValue * 0.005;
            if (reinvestDividends) {
                totalValue += dividendAmount;
            }
        }

        // Record year-end values for the chart
        if (month % 12 === 0) {
            yearlyValues.push(totalValue);
        }
    }

    // Calculate ROI
    const investmentGrowth = totalValue - totalContributions;
    const roi = (investmentGrowth / totalContributions) * 100;

    return {
        totalValue,
        totalContributions,
        investmentGrowth,
        roi,
        yearlyValues
    };
}

// Format currency values
function formatCurrency(value) {
    if (value >= 1_000_000_000) {
        return (value / 1_000_000_000).toFixed(2) + ' billion';
    } else if (value >= 1_000_000) {
        return (value / 1_000_000).toFixed(2) + ' million';
    } else {
        return value.toLocaleString('en-US', { maximumFractionDigits: 2 });
    }
}


// Update the UI with calculation results
function updateResultsUI(projectedMarketCap, cagr, projectedRevenue, projectedEarnings, investmentResults, years, initialMarketCap, initialRevenue) {
    // Update market cap projections
    document.getElementById('projectedMarketCap').textContent = formatCurrency(projectedMarketCap);
    document.getElementById('cagr').textContent = cagr.toFixed(2) + '%';
    document.getElementById('projectedRevenue').textContent = formatCurrency(projectedRevenue);
    document.getElementById('projectedEarnings').textContent = formatCurrency(projectedEarnings);

    // Update year spans
    const yearSpans = document.querySelectorAll('[id^="yearSpan"]');
    yearSpans.forEach(span => {
        span.textContent = years;
    });

    // Update investment projections
    document.getElementById('totalInvestmentValue').textContent = formatCurrency(investmentResults.totalValue);
    document.getElementById('totalContributions').textContent = formatCurrency(investmentResults.totalContributions);
    document.getElementById('investmentGrowth').textContent = formatCurrency(investmentResults.investmentGrowth);
    document.getElementById('roi').textContent = investmentResults.roi.toFixed(2) + '%';

    // Update or create the chart
    updateGrowthChart(investmentResults.yearlyValues, initialMarketCap, projectedMarketCap, initialRevenue, projectedRevenue, years);
}

// Update or create the growth chart
function updateGrowthChart(yearlyInvestmentValues, initialMarketCap, projectedMarketCap, initialRevenue, projectedRevenue, years) {
    const ctx = document.getElementById('growthChart').getContext('2d');

    // Generate labels for each year
    const labels = Array.from({length: years + 1}, (_, i) => `Year ${i}`);

    // Generate market cap data (initial to projected, with exponential growth)
    const marketCapData = [];
    const revenueData = [];

    for (let i = 0; i <= years; i++) {
        const growthFactor = Math.pow(projectedMarketCap / initialMarketCap, i / years);
        marketCapData.push(initialMarketCap * growthFactor);

        const revenueFactor = Math.pow(projectedRevenue / initialRevenue, i / years);
        revenueData.push(initialRevenue * revenueFactor);
    }

    // Normalize the data for better visualization (divide by appropriate scale)
    const maxValue = Math.max(
        ...marketCapData,
        ...yearlyInvestmentValues,
        ...revenueData
    );

let divisor = 1;
let yAxisLabel = '';

if (maxValue >= 1_000_000_000) {
    divisor = 1_000_000_000;
    yAxisLabel = 'Billions';
} else if (maxValue >= 1_000_000) {
    divisor = 1_000_000;
    yAxisLabel = 'Millions';
} else if (maxValue >= 1_000) {
    divisor = 1_000;
    yAxisLabel = 'Thousands';
}


    const normalizedMarketCap = marketCapData.map(val => val / divisor);
    const normalizedInvestment = yearlyInvestmentValues.map(val => val / divisor);
    const normalizedRevenue = revenueData.map(val => val / divisor);

    // Destroy existing chart if it exists
    if (growthChart) {
        growthChart.destroy();
    }

    // Create new chart
    growthChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Market Cap',
                    data: normalizedMarketCap,
                    borderColor: 'rgba(67, 97, 238, 1)',
                    backgroundColor: 'rgba(67, 97, 238, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                },
                {
                    label: 'Investment Value',
                    data: normalizedInvestment,
                    borderColor: 'rgba(76, 201, 240, 1)',
                    backgroundColor: 'rgba(76, 201, 240, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.1
                },
                {
                    label: 'Revenue',
                    data: normalizedRevenue,
                    borderColor: 'rgba(72, 149, 239, 1)',
                    backgroundColor: 'rgba(72, 149, 239, 0.1)',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.4,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: 'Growth Projection Over Time',
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
                            const value = context.raw * divisor;
                            label += formatCurrency(value);
                            return label;
                        }
                    }
                },
                legend: {
                    position: 'top',
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: yAxisLabel
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Time (Years)'
                    }
                }
            }
        }
    });
}
