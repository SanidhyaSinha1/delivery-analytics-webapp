from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
import os
import pandas as pd
import numpy as np
from datetime import datetime
from werkzeug.utils import secure_filename
import zipfile
import io
from analysis import analyze_comprehensive_delivery_performance_corrected

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-fallback-secret-key')  # Change this in production

# Configuration
UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'
ALLOWED_EXTENSIONS = {'csv'}

app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'uploads')
app.config['DOWNLOAD_FOLDER'] = os.environ.get('DOWNLOAD_FOLDER', 'downloads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size 

# MongoDB configuration
app.config['MONGODB_URI'] = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/delivery_analytics')

# DigitalOcean Spaces configuration
app.config['DO_SPACES_KEY'] = os.environ.get('DO_SPACES_KEY')
app.config['DO_SPACES_SECRET'] = os.environ.get('DO_SPACES_SECRET')
app.config['DO_SPACES_BUCKET'] = os.environ.get('DO_SPACES_BUCKET')
app.config['DO_SPACES_REGION'] = os.environ.get('DO_SPACES_REGION', 'nyc3') 

# Azure Blob Storage configuration
app.config['AZURE_STORAGE_CONNECTION_STRING'] = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
app.config['AZURE_CONTAINER_NAME'] = os.environ.get('AZURE_CONTAINER_NAME', 'delivery-analytics-files')

# Security settings
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = os.environ.get('CSRF_SECRET_KEY', 'csrf-secret-key') 

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            flash('No file selected')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Process the file
            return redirect(url_for('analyze', filename=filename))
        else:
            flash('Please upload a CSV file only')
            return redirect(request.url)
    
    except Exception as e:
        flash(f'Error uploading file: {str(e)}')
        return redirect(url_for('index'))

@app.route('/analyze/<filename>')
def analyze(filename):
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(filepath):
            flash('File not found')
            return redirect(url_for('index'))
        
        # Run the analysis
        flash('Analysis in progress... This may take a few minutes.')
        results = analyze_comprehensive_delivery_performance_corrected(filepath)
        
        if results is None:
            flash('Analysis failed. Please check your data format.')
            return redirect(url_for('index'))
        
        daywise_results, payment_results, zone_results, route_results, courier_results = results
        
        # Generate download files
        download_files = generate_download_files(filename, results)
        
        # Prepare data for display
        analysis_data = prepare_display_data(results)
        
        return render_template('results.html', 
                             analysis_data=analysis_data,
                             download_files=download_files,
                             filename=filename)
    
    except Exception as e:
        flash(f'Analysis error: {str(e)}')
        return redirect(url_for('index'))

def generate_download_files(filename, results):
    """Generate CSV files for download"""
    try:
        daywise_results, payment_results, zone_results, route_results, courier_results = results
        
        base_name = filename.replace('.csv', '')
        download_files = []
        
        # Save each analysis result
        analyses = {
            'daywise_analysis': daywise_results,
            'payment_method_analysis': payment_results,
            'zone_performance_analysis': zone_results,
            'route_performance_analysis': route_results,
            'courier_performance_analysis': courier_results
        }
        
        for analysis_name, data in analyses.items():
            if data is not None and not data.empty:
                download_filename = f"{base_name}_{analysis_name}.csv"
                download_path = os.path.join(app.config['DOWNLOAD_FOLDER'], download_filename)
                data.to_csv(download_path, index=False)
                download_files.append(download_filename)
        
        return download_files
    
    except Exception as e:
        print(f"Error generating download files: {e}")
        return []

def prepare_display_data(results):
    """Prepare data for web display"""
    try:
        daywise_results, payment_results, zone_results, route_results, courier_results = results
        
        # Convert DataFrames to HTML tables
        analysis_data = {}
        
        if daywise_results is not None and not daywise_results.empty:
            # Format daywise data for display
            daywise_display = daywise_results.head(15).copy()
            daywise_display['delivery_percentage'] = daywise_display['delivery_percentage'].apply(lambda x: f"{x:.2f}%")
            daywise_display['drop_in_delivery_percentage'] = daywise_display['drop_in_delivery_percentage'].apply(
                lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A"
            )
            analysis_data['daywise'] = daywise_display.to_html(classes='table table-striped', index=False)
        
        if payment_results is not None and not payment_results.empty:
            # Payment method summary
            payment_summary = payment_results.groupby('payment_method').agg({
                'total_shipments': 'sum',
                'delivered_count': 'sum',
                'rto_count': 'sum',
                'delivery_percentage': 'mean'
            }).reset_index()
            payment_summary['delivery_percentage'] = payment_summary['delivery_percentage'].apply(lambda x: f"{x:.2f}%")
            analysis_data['payment'] = payment_summary.to_html(classes='table table-striped', index=False)
        
        if zone_results is not None and not zone_results.empty:
            # Zone performance summary
            zone_summary = zone_results.groupby('applied_zone').agg({
                'total_shipments': 'sum',
                'delivered_count': 'sum',
                'rto_count': 'sum',
                'delivery_percentage': 'mean'
            }).reset_index()
            zone_summary['delivery_percentage'] = zone_summary['delivery_percentage'].apply(lambda x: f"{x:.2f}%")
            analysis_data['zone'] = zone_summary.to_html(classes='table table-striped', index=False)
        
        if courier_results is not None and not courier_results.empty:
            # Courier performance summary
            courier_summary = courier_results.groupby('parent_courier_name').agg({
                'total_shipments': 'sum',
                'delivered_count': 'sum',
                'rto_count': 'sum',
                'delivery_percentage': 'mean'
            }).reset_index()
            courier_summary['delivery_percentage'] = courier_summary['delivery_percentage'].apply(lambda x: f"{x:.2f}%")
            analysis_data['courier'] = courier_summary.to_html(classes='table table-striped', index=False)
        
        return analysis_data
    
    except Exception as e:
        print(f"Error preparing display data: {e}")
        return {}

@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            flash('File not found')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'Download error: {str(e)}')
        return redirect(url_for('index'))

@app.route('/download_all/<base_filename>')
def download_all_files(base_filename):
    try:
        # Create a zip file with all analysis results
        memory_file = io.BytesIO()
        
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            download_folder = app.config['DOWNLOAD_FOLDER']
            for filename in os.listdir(download_folder):
                if filename.startswith(base_filename.replace('.csv', '')):
                    file_path = os.path.join(download_folder, filename)
                    zf.write(file_path, filename)
        
        memory_file.seek(0)
        
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{base_filename.replace('.csv', '')}_analysis_results.zip"
        )
    
    except Exception as e:
        flash(f'Download error: {str(e)}')
        return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False) 
