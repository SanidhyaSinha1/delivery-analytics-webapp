document.addEventListener('DOMContentLoaded', function() {
    // File upload validation and preview
    const fileInput = document.getElementById('file');
    const uploadForm = document.getElementById('uploadForm');
    const submitBtn = document.getElementById('submitBtn');
    const fileInfo = document.getElementById('fileInfo');
    const fileDetails = document.getElementById('fileDetails');
    
    if (fileInput && uploadForm) {
        fileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                // File size validation
                if (file.size > 50 * 1024 * 1024) {
                    showAlert('File size must be less than 50MB', 'danger');
                    e.target.value = '';
                    hideFileInfo();
                    return;
                }
                
                // File type validation
                if (!file.name.toLowerCase().endsWith('.csv')) {
                    showAlert('Please select a CSV file', 'danger');
                    e.target.value = '';
                    hideFileInfo();
                    return;
                }
                
                // Show file information
                showFileInfo(file);
            } else {
                hideFileInfo();
            }
        });
        
        uploadForm.addEventListener('submit', function(e) {
            if (!fileInput.files[0]) {
                e.preventDefault();
                showAlert('Please select a file first', 'warning');
                return;
            }
            
            // Update button state
            submitBtn.innerHTML = '<span class="loading-spinner"></span> Processing...';
            submitBtn.disabled = true;
            
            // Show processing message
            showAlert('File uploaded successfully!', 'info');
        });
    }
    
    // Auto-dismiss alerts
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            if (bootstrap.Alert) {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }
        }, 5000);
    });
    
    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
    
    // Table enhancements
    enhanceTables();
    
    function showFileInfo(file) {
        const sizeInMB = (file.size / (1024 * 1024)).toFixed(2);
        const lastModified = new Date(file.lastModified).toLocaleDateString();
        
        fileDetails.innerHTML = `
            <div class="row">
                <div class="col-sm-6"><strong>File name:</strong> ${file.name}</div>
                <div class="col-sm-6"><strong>Size:</strong> ${sizeInMB} MB</div>
                <div class="col-sm-6"><strong>Type:</strong> ${file.type || 'CSV'}</div>
                <div class="col-sm-6"><strong>Last modified:</strong> ${lastModified}</div>
            </div>
        `;
        
        fileInfo.classList.remove('d-none');
    }
    
    function hideFileInfo() {
        fileInfo.classList.add('d-none');
    }
    
    function showAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const container = document.querySelector('.container-fluid');
        container.insertBefore(alertDiv, container.firstChild);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            if (bootstrap.Alert) {
                const bsAlert = new bootstrap.Alert(alertDiv);
                bsAlert.close();
            }
        }, 5000);
    }
    
    function enhanceTables() {
    const tables = document.querySelectorAll('.table');
    tables.forEach(table => {
        table.classList.add('table-striped');
        table.classList.add('table-hover');
        
        // Format all cells
        const cells = table.querySelectorAll('td');
        cells.forEach(cell => {
            const text = cell.textContent.trim();
            
            // Check if this is a percentage cell
            if (text.includes('%')) {
                const percentage = parseFloat(text);
                
                if (!isNaN(percentage)) {
                    // Check if this cell contains "drop" data by looking at the column header
                    const cellIndex = Array.from(cell.parentNode.children).indexOf(cell);
                    const headerRow = table.querySelector('thead tr');
                    const header = headerRow ? headerRow.children[cellIndex] : null;
                    const headerText = header ? header.textContent.trim().toLowerCase() : '';
                    
                    if (headerText.includes('drop')) {
                        // Handle drop_in_delivery_percentage column
                        if (percentage > 0) {
                            cell.style.color = '#059669'; // Green for positive
                            cell.style.fontWeight = '600';
                        } else if (percentage < 0) {
                            cell.style.color = '#dc2626'; // Red for negative
                            cell.style.fontWeight = '600';
                        }
                    } else {
                        // Handle other percentage columns (delivery_percentage, rto_rate)
                        if (percentage >= 80) {
                            cell.style.color = '#059669'; // Green for good performance
                            cell.style.fontWeight = '600';
                        } else if (percentage >= 60) {
                            cell.style.color = '#d97706'; // Orange for average performance
                            cell.style.fontWeight = '600';
                        } else if (percentage < 60 && percentage > 0) {
                            cell.style.color = '#dc2626'; // Red for poor performance
                            cell.style.fontWeight = '600';
                        }
                    }
                }
            }
        });
    });
}

});
