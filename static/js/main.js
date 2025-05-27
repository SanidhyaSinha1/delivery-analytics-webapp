document.addEventListener('DOMContentLoaded', function() {
    // File upload validation
    const fileInput = document.getElementById('file');
    const uploadForm = document.querySelector('form[enctype="multipart/form-data"]');
    
    if (fileInput && uploadForm) {
        fileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                // Check file size (50MB limit)
                if (file.size > 50 * 1024 * 1024) {
                    alert('File size must be less than 50MB');
                    e.target.value = '';
                    return;
                }
                
                // Check file type
                if (!file.name.toLowerCase().endsWith('.csv')) {
                    alert('Please select a CSV file');
                    e.target.value = '';
                    return;
                }
            }
        });
        
        uploadForm.addEventListener('submit', function(e) {
            const submitBtn = this.querySelector('button[type="submit"]');
            submitBtn.innerHTML = '⏳ Processing...';
            submitBtn.disabled = true;
        });
    }
    
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
});
