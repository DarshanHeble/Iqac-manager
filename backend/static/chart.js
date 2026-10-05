/* Chart.js placeholder - use local version */
// Minimal chart setup example
window.addEventListener('DOMContentLoaded', () => {
  const ctx = document.getElementById('categoryChart');
  if (ctx) {
    new Chart(ctx, {
      type: 'pie',
      data: {
        labels: ['Teaching', 'Research', 'Administrative', 'Extension', 'Others'],
        datasets: [{
          label: 'Category Distribution',
          data: [10, 20, 15, 5, 8],
          backgroundColor: ['#0d6efd','#17a2b8','#6c757d','#ffc107','#28a745']
        }]
      }
    });
  }
});
