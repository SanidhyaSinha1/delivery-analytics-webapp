import pandas as pd
import numpy as np
from datetime import datetime
import gc
import os

def read_large_csv_optimized(file_path):
    """
    Memory-optimized CSV reading for large files
    """
    print(f"📊 Loading large dataset: {file_path}")
    
    # Define optimized data types to reduce memory usage
    dtype_dict = {
        'parent_courier_name': 'category',
        'courier_name': 'category',
        'payment_method': 'category',
        'tracking_status_group': 'category',
        'applied_zone': 'category',
        'pickup_state': 'category',
        'delivery_state': 'category',
        'delivery_city': 'category',
        'company_name': 'category',
        'shipment_mode': 'category'
    }
    
    try:
        # Check file size
        file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
        print(f"File size: {file_size:.2f} MB")
        
        if file_size > 50:  # Large file - use chunked reading
            print("Large file detected. Using chunked processing...")
            chunks = []
            chunk_size = 10000  # Process 10k rows at a time
            
            for i, chunk in enumerate(pd.read_csv(file_path, chunksize=chunk_size, dtype=dtype_dict, low_memory=False)):
                chunks.append(chunk)
                if i % 10 == 0:  # Progress update every 100k rows
                    print(f"Processed {(i+1) * chunk_size:,} rows...")
                
                # Memory management
                if len(chunks) >= 50:  # Combine every 50 chunks
                    combined_chunk = pd.concat(chunks, ignore_index=True)
                    chunks = [combined_chunk]
                    gc.collect()
            
            df = pd.concat(chunks, ignore_index=True)
            del chunks
            gc.collect()
            
        else:  # Small file - read normally
            df = pd.read_csv(file_path, dtype=dtype_dict, low_memory=False)
        
        print(f"✅ Dataset loaded with {len(df):,} records")
        return df
        
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None

def calculate_comprehensive_delivery_analysis_corrected(file_path):
    """
    Memory-optimized comprehensive delivery performance analysis
    """
    
    # Load dataset with memory optimization
    df = read_large_csv_optimized(file_path)
    if df is None or df.empty:
        return None, None, None
    
    initial_total_records = len(df)
    
    # Convert date columns efficiently
    date_columns = ['first_attempt_date', 'final_courier_edd', 'delivered_date', 'rapidshyp_edd']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Create enhanced EDD column 
    df['effective_edd'] = df['final_courier_edd'].combine_first(df['rapidshyp_edd'])
    
    # Flag missing EDD values instead of dropping
    df['edd_missing'] = df['effective_edd'].isna()
    print(f"\uD83D\uDD0D Found {df['edd_missing'].sum():,} records with missing EDD")
    
    # Get current date as date object
    current_date = datetime.now().date()
    
    # Convert datetime columns to date objects safely
    df['effective_edd_date'] = df['effective_edd'].apply(
        lambda x: x.date() if pd.notna(x) else None
    )
    df['first_attempt_date'] = df['first_attempt_date'].apply(
        lambda x: x.date() if pd.notna(x) else None
    )
    
    # Vectorized TAT breach calculation
    cond_missing_edd = df['edd_missing'] & df['first_attempt_date'].notna()
    cond_attempt_after_edd = (
        df['first_attempt_date'].notna() & 
        df['effective_edd_date'].notna() & 
        (df['first_attempt_date'] > df['effective_edd_date'])
    )
    cond_no_attempt = (
        df['first_attempt_date'].isna() & 
        df['effective_edd_date'].notna() & 
        (current_date > df['effective_edd_date'])
    )
    
    df['tat_breach'] = cond_missing_edd | cond_attempt_after_edd | cond_no_attempt
    
    # Calculate delivery success
    df['delivery_success'] = (df['tracking_status_group'] == 'Delivered').astype(int)
    
    # Filter only TAT breach cases for analysis
    breach_df = df[df['tat_breach']].copy()
    
    # Categorize shipment status with error handling
    def categorize_shipment_status(row):
        try:
            status = row['tracking_status_group']
            if status == 'Delivered':
                return 'Delivered'
            elif status == 'RTO':
                return 'RTO'
            elif status == 'Damage/Lost':
                return 'Damage/Lost'
            elif status == 'Manifested':
                return 'Undelivered'
            else:
                if pd.isna(row['delivered_date']):
                    return 'Undelivered'
                return 'Other'
        except KeyError:
            return 'Unknown'
    
    breach_df['shipment_category'] = breach_df.apply(categorize_shipment_status, axis=1)
    
    # Calculate days after TAT breach with NaT handling
    def calculate_days_after_tat_breach(row):
        try:
            effective_edd = row['effective_edd_date']
            first_attempt = row['first_attempt_date']
            
            if effective_edd is None:
                return None  # Skip invalid entries
                
            if first_attempt is not None:
                days = (first_attempt - effective_edd).days
            else:
                days = (current_date - effective_edd).days
                
            return max(1, days) if days is not None else None
            
        except TypeError:
            return None

    breach_df['days_after_tat_breach'] = breach_df.apply(
        calculate_days_after_tat_breach, axis=1
    )
    
    # Clean invalid entries
    breach_df = breach_df[breach_df['days_after_tat_breach'].notna()]
    
    # Calculate daywise statistics (starting from Day 1)
    daywise_stats = breach_df.groupby('days_after_tat_breach').agg(
        total_shipments=('delivery_success', 'count'),
        successful_deliveries=('delivery_success', 'sum'),
        delivered_count=('shipment_category', lambda x: sum(x == 'Delivered')),
        rto_count=('shipment_category', lambda x: sum(x == 'RTO')),
        damage_lost_count=('shipment_category', lambda x: sum(x == 'Damage/Lost')),
        undelivered_count=('shipment_category', lambda x: sum(x == 'Undelivered'))
    ).reset_index()
    
    # Calculate performance metrics with zero-division handling
    daywise_stats['delivery_percentage'] = daywise_stats.apply(
        lambda x: (x['successful_deliveries'] / x['total_shipments'] * 100) if x['total_shipments'] > 0 else 0,
        axis=1
    )
    
    daywise_stats['rto_rate'] = daywise_stats.apply(
        lambda x: (x['rto_count'] / x['total_shipments'] * 100) if x['total_shipments'] > 0 else 0,
        axis=1
    )
    
    daywise_stats['drop_in_delivery_percentage'] = daywise_stats['delivery_percentage'].diff()
    
    # Memory cleanup
    gc.collect()
    
    return daywise_stats, breach_df, initial_total_records


def calculate_payment_method_analysis(breach_df):
    """
    Calculate payment method performance analysis with memory optimization
    """
    print("\n💳 Calculating Payment Method Analysis...")
    
    payment_performance = breach_df.groupby(['payment_method', 'days_after_tat_breach']).agg(
        total_shipments=('delivery_success', 'count'),
        successful_deliveries=('delivery_success', 'sum'),
        delivered_count=('shipment_category', lambda x: sum(x == 'Delivered')),
        rto_count=('shipment_category', lambda x: sum(x == 'RTO')),
        undelivered_count=('shipment_category', lambda x: sum(x == 'Undelivered'))
    ).reset_index()
    
    payment_performance['delivery_percentage'] = (payment_performance['successful_deliveries'] / payment_performance['total_shipments']) * 100
    payment_performance['rto_rate'] = (payment_performance['rto_count'] / payment_performance['total_shipments']) * 100
    payment_performance['drop_in_delivery_percentage'] = payment_performance.groupby('payment_method')['delivery_percentage'].diff()
    
    return payment_performance

def calculate_zone_performance_analysis(breach_df):
    """
    Calculate zone-wise performance analysis with memory optimization
    """
    print("\n🗺️  Calculating Zone Performance Analysis...")
    
    zone_performance = breach_df.groupby(['applied_zone', 'days_after_tat_breach']).agg(
        total_shipments=('delivery_success', 'count'),
        successful_deliveries=('delivery_success', 'sum'),
        delivered_count=('shipment_category', lambda x: sum(x == 'Delivered')),
        rto_count=('shipment_category', lambda x: sum(x == 'RTO')),
        undelivered_count=('shipment_category', lambda x: sum(x == 'Undelivered'))
    ).reset_index()
    
    zone_performance['delivery_percentage'] = (zone_performance['successful_deliveries'] / zone_performance['total_shipments']) * 100
    zone_performance['rto_rate'] = (zone_performance['rto_count'] / zone_performance['total_shipments']) * 100
    zone_performance['drop_in_delivery_percentage'] = zone_performance.groupby('applied_zone')['delivery_percentage'].diff()
    
    return zone_performance

def calculate_route_performance_analysis(breach_df):
    """
    Calculate route performance analysis with meaningful aggregations
    """
    print("\n🛣️  Calculating Route Performance Analysis...")
    
    # Create route combinations (pickup_state -> delivery_state)
    breach_df['route'] = breach_df['pickup_state'].astype(str) + ' → ' + breach_df['delivery_state'].astype(str)
    
    # Get overall route performance (not day-wise to avoid too much granularity)
    route_summary = breach_df.groupby('route').agg(
        total_shipments=('delivery_success', 'count'),
        successful_deliveries=('delivery_success', 'sum'),
        delivered_count=('shipment_category', lambda x: sum(x == 'Delivered')),
        rto_count=('shipment_category', lambda x: sum(x == 'RTO')),
        undelivered_count=('shipment_category', lambda x: sum(x == 'Undelivered')),
        avg_days_to_delivery=('days_after_tat_breach', lambda x: x[breach_df.loc[x.index, 'shipment_category'] == 'Delivered'].mean())
    ).reset_index()
    
    # Calculate performance metrics
    route_summary['delivery_percentage'] = (route_summary['delivered_count'] / route_summary['total_shipments']) * 100
    route_summary['rto_rate'] = (route_summary['rto_count'] / route_summary['total_shipments']) * 100
    route_summary['undelivered_rate'] = (route_summary['undelivered_count'] / route_summary['total_shipments']) * 100
    
    # Sort by total shipments to show most important routes first
    route_summary = route_summary.sort_values('total_shipments', ascending=False)
    
    # Only keep routes with significant volume (top 20 or minimum 10 shipments)
    route_summary = route_summary[
        (route_summary['total_shipments'] >= 10) | 
        (route_summary.index < 20)
    ].reset_index(drop=True)
    
    # Add route performance categories
    def categorize_route_performance(row):
        delivery_rate = row['delivery_percentage']
        if delivery_rate >= 80:
            return 'Excellent'
        elif delivery_rate >= 60:
            return 'Good'
        elif delivery_rate >= 40:
            return 'Average'
        else:
            return 'Poor'
    
    route_summary['performance_category'] = route_summary.apply(categorize_route_performance, axis=1)
    
    # Separate pickup and delivery states for better analysis
    route_summary[['pickup_state', 'delivery_state']] = route_summary['route'].str.split(' → ', expand=True)
    
    # Reorder columns for better readability
    column_order = [
        'route', 'pickup_state', 'delivery_state', 'total_shipments', 
        'delivered_count', 'delivery_percentage', 'rto_count', 'rto_rate',
        'undelivered_count', 'undelivered_rate', 'avg_days_to_delivery', 
        'performance_category'
    ]
    
    route_summary = route_summary[column_order]
    
    print(f"✅ Route analysis completed for {len(route_summary)} major routes")
    
    return route_summary


def calculate_parent_courier_performance(breach_df):
    """
    Calculate parent courier performance with memory optimization
    """
    print("\n📦 Calculating Parent Courier Performance...")
    
    courier_stats = breach_df.groupby(['parent_courier_name', 'days_after_tat_breach']).agg(
        total_shipments=('delivery_success', 'count'),
        successful_deliveries=('delivery_success', 'sum'),
        delivered_count=('shipment_category', lambda x: sum(x == 'Delivered')),
        rto_count=('shipment_category', lambda x: sum(x == 'RTO')),
        undelivered_count=('shipment_category', lambda x: sum(x == 'Undelivered'))
    ).reset_index()
    
    courier_stats['delivery_percentage'] = (courier_stats['successful_deliveries'] / courier_stats['total_shipments']) * 100
    courier_stats['rto_rate'] = (courier_stats['rto_count'] / courier_stats['total_shipments']) * 100
    courier_stats['drop_in_delivery_percentage'] = courier_stats.groupby('parent_courier_name')['delivery_percentage'].diff()
    
    return courier_stats

def analyze_comprehensive_delivery_performance_corrected(file_path):
    """
    Main function with memory-optimized comprehensive analysis
    """
    try:
        print("🚀 Starting Memory-Optimized Comprehensive Delivery Performance Analysis...")
        print("(TAT Breach Analysis starts from Day 1 - True Breach Cases Only)")
        print("=" * 100)
        
        # Calculate main statistics with memory optimization
        daywise_stats, breach_df, initial_total_records = calculate_comprehensive_delivery_analysis_corrected(file_path)
        
        if daywise_stats is not None and not daywise_stats.empty:
            # Calculate all performance analyses
            payment_perf = calculate_payment_method_analysis(breach_df)
            zone_perf = calculate_zone_performance_analysis(breach_df)
            route_perf = calculate_route_performance_analysis(breach_df)
            courier_stats = calculate_parent_courier_performance(breach_df)
            
            print("✅ Memory-Optimized Comprehensive analysis completed successfully!")
            
            return daywise_stats, payment_perf, zone_perf, route_perf, courier_stats, initial_total_records
        else:
            print("❌ No analysis could be performed due to insufficient data.")
            return None, None, None, None, None
            
    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        return None, None, None, None, None
