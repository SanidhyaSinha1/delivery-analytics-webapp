from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify
import os
import pandas as pd
import numpy as np
from datetime import datetime
from werkzeug.utils import secure_filename
import zipfile
import io
import gc
from analysis import analyze_comprehensive_delivery_performance_corrected

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-fallback-secret-key')

# Configuration for large files
UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'
ALLOWED_EXTENSIONS = {'csv'}

app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'uploads')
app.config['DOWNLOAD_FOLDER'] = os.environ.get('DOWNLOAD_FOLDER', 'downloads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Memory optimization settings
import socket
socket.setdefaulttimeout(1200)  # 20 minutes timeout

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# MongoDB configuration
app.config['MONGODB_URI'] = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017/delivery_analytics')

# Azure Blob Storage configuration
app.config['AZURE_STORAGE_CONNECTION_STRING'] = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
app.config['AZURE_CONTAINER_NAME'] = os.environ.get('AZURE_CONTAINER_NAME', 'delivery-analytics-files')

# Security settings
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = os.environ.get('CSRF_SECRET_KEY', 'csrf-secret-key') 

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
            return redirect(url_for('index'))
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected')
            return redirect(url_for('index'))
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Check file size before processing
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)  # Reset file pointer
            
            if file_size > 100 * 1024 * 1024:  # 100MB+
                flash('Large file detected. Processing may take 10-15 minutes. Please be patient...')
            else:
                flash('File uploaded successfully! Starting analysis...')
            
            # Save file efficiently
            file.save(filepath)
            
            return redirect(url_for('analyze', filename=filename))
        else:
            flash('Please upload a CSV file only')
            return redirect(url_for('index'))
    
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
        
        # Force garbage collection before analysis
        gc.collect()
        
        
        # Run memory-optimized analysis
        results = analyze_comprehensive_delivery_performance_corrected(filepath)
        
        # Force garbage collection after analysis
        gc.collect()
        
        if results is None or results[0] is None:
            flash('Analysis failed. Please check your data format and ensure all required columns are present.')
            return redirect(url_for('index'))
        
        daywise_results, payment_results, zone_results, route_results, courier_results, initial_total_records = results
        
        # Generate download files
        download_files = generate_download_files(filename, (daywise_results, payment_results, zone_results, route_results, courier_results))
        
        # Prepare data for display
        analysis_data = prepare_display_data((daywise_results, payment_results, zone_results, route_results, courier_results), initial_total_records)
        
        # Clean up memory
        del results
        gc.collect()
        
        return render_template('results.html', 
                             analysis_data=analysis_data,
                             download_files=download_files,
                             filename=filename)
    
    except Exception as e:
        flash(f'Analysis error: {str(e)}')
        return redirect(url_for('index'))

def generate_download_files(filename, results):
    """Generate CSV files for download with memory optimization"""
    try:
        daywise_results, payment_results, zone_results, route_results, courier_results = results
        
        base_name = filename.replace('.csv', '')
        download_files = []
        
        # Save each analysis result efficiently
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
                
                # Write in chunks to save memory
                data.to_csv(download_path, index=False, chunksize=1000)
                download_files.append(download_filename)
                
                # Clean up memory
                del data
                gc.collect()
        
        return download_files
    
    except Exception as e:
        print(f"Error generating download files: {e}")
        return []

def prepare_display_data(results, initial_total_records):
    """Prepare data for web display with summary statistics"""
    try:
        daywise_results, payment_results, zone_results, route_results, courier_results = results
        
        analysis_data = {}
        
        # Calculate summary statistics
        if daywise_results is not None and not daywise_results.empty:
            total_breach_cases = daywise_results['total_shipments'].sum()
            total_delivered = daywise_results['successful_deliveries'].sum()
            total_rto = daywise_results['rto_count'].sum()
            
            # Calculate rates
            delivery_rate = (total_delivered / total_breach_cases * 100) if total_breach_cases > 0 else 0
            rto_rate = (total_rto / total_breach_cases * 100) if total_breach_cases > 0 else 0
            
            # Add summary stats to analysis_data
            analysis_data['total_records'] = f"{initial_total_records:,}"
            analysis_data['breach_cases'] = f"{total_breach_cases:,}"
            analysis_data['delivery_rate'] = f"{delivery_rate:.1f}%"
            analysis_data['rto_rate'] = f"{rto_rate:.1f}%"
            
            # Process daywise data for display
            daywise_display = daywise_results.head(15).copy()
            daywise_display['delivery_percentage'] = daywise_display['delivery_percentage'].apply(lambda x: f"{x:.2f}%")
            daywise_display['drop_in_delivery_percentage'] = daywise_display['drop_in_delivery_percentage'].apply(
                lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A"
            )
            analysis_data['daywise'] = daywise_display.to_html(classes='table table-striped', index=False)
            del daywise_display
        else:
            # Set default values when no data
            analysis_data['total_records'] = f"{initial_total_records:,}" if initial_total_records else "0"
            analysis_data['breach_cases'] = "0"
            analysis_data['delivery_rate'] = "0%"
            analysis_data['rto_rate'] = "0%"
        
        # Process payment method data
        if payment_results is not None and not payment_results.empty:
            payment_summary = payment_results.groupby('payment_method').agg({
                'total_shipments': 'sum',
                'delivered_count': 'sum',
                'rto_count': 'sum',
                'delivery_percentage': 'mean'
            }).reset_index()
            payment_summary['delivery_percentage'] = (payment_summary['delivered_count'] / payment_summary['total_shipments'] * 100)
            payment_summary['delivery_percentage'] = payment_summary['delivery_percentage'].apply(lambda x: f"{x:.2f}%")
            analysis_data['payment'] = payment_summary.to_html(classes='table table-striped', index=False)
            del payment_summary
        
        # Process zone data
        if zone_results is not None and not zone_results.empty:
            zone_summary = zone_results.groupby('applied_zone').agg({
                'total_shipments': 'sum',
                'delivered_count': 'sum',
                'rto_count': 'sum',
                'delivery_percentage': 'mean'
            }).reset_index()
            zone_summary['delivery_percentage'] = (zone_summary['delivered_count'] / zone_summary['total_shipments'] * 100)
            zone_summary['delivery_percentage'] = zone_summary['delivery_percentage'].apply(lambda x: f"{x:.2f}%")
            analysis_data['zone'] = zone_summary.to_html(classes='table table-striped', index=False)
            del zone_summary
        
        # Process courier data
        if courier_results is not None and not courier_results.empty:
            courier_summary = courier_results.groupby('parent_courier_name').agg({
                'total_shipments': 'sum',
                'delivered_count': 'sum',
                'rto_count': 'sum',
                'delivery_percentage': 'mean'
            }).reset_index()
            courier_summary['delivery_percentage'] = (courier_summary['delivered_count'] / courier_summary['total_shipments'] * 100)
            courier_summary['delivery_percentage'] = courier_summary['delivery_percentage'].apply(lambda x: f"{x:.2f}%")
            analysis_data['courier'] = courier_summary.to_html(classes='table table-striped', index=False)
            del courier_summary
        
        # Force garbage collection
        gc.collect()
        
        return analysis_data
    
    except Exception as e:
        print(f"Error preparing display data: {e}")
        # Return default values on error
        return {
            'total_records': f"{initial_total_records:,}" if 'initial_total_records' in locals() else "0",
            'breach_cases': "0", 
            'delivery_rate': "0%",
            'rto_rate': "0%"
        }


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

@app.errorhandler(413)
def too_large(error):
    flash('File too large! Please upload a file smaller than 50MB.')
    return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    flash('Internal server error. Please try again.')
    return redirect(url_for('index'))

@app.route('/health')
def health():
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "max_file_size_mb": app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024),
        "max_file_size_bytes": app.config['MAX_CONTENT_LENGTH']
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"Starting Flask app with 50MB limit and memory optimization")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
