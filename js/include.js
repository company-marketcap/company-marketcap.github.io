// include.js
function loadHTML(selector, file) {
  fetch(file)
    .then(response => response.text())
    .then(data => document.querySelector(selector).innerHTML = data);
}

document.addEventListener("DOMContentLoaded", () => {
  // Load header and footer
loadHTML("#header", "/header.html");
loadHTML("#footer", "/footer.html");
loadHTML("#calcNav", "/calculator-nav.html");


  // Add calculator nav container if it doesn't exist
  if (!document.getElementById('calcNav')) {
    const calcNavDiv = document.createElement('div');
    calcNavDiv.id = 'calcNav';
    calcNavDiv.style.display = 'none';
    document.body.insertBefore(calcNavDiv, document.getElementById('header').nextSibling);
  }

  // Load calculator navigation
  loadHTML("#calcNav", "calculator-nav.html");

  // Add toggle button
  const toggleBtn = document.createElement('button');
  toggleBtn.className = 'btn btn-sm btn-primary position-fixed';
  toggleBtn.id = 'showCalcNav';
  toggleBtn.innerHTML = '<i class="bi bi-calculator me-1"></i> More Calculators';
  toggleBtn.style.bottom = '20px';
  toggleBtn.style.right = '20px';
  toggleBtn.style.zIndex = '1000';
  toggleBtn.style.borderRadius = '30px';
  toggleBtn.style.padding = '8px 16px';
  document.body.appendChild(toggleBtn);

  // Add toggle functionality
  document.addEventListener('click', function(e) {
    if (e.target.id === 'showCalcNav' || e.target.closest('#showCalcNav')) {
      document.getElementById('calcNav').style.display = 'block';
      document.getElementById('showCalcNav').style.display = 'none';
    }

    if (e.target.id === 'hideCalcNav') {
      document.getElementById('calcNav').style.display = 'none';
      document.getElementById('showCalcNav').style.display = 'block';
    }
  });
});
