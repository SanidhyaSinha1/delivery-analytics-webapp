import pandas as pd
import numpy as np
from datetime import datetime

def calculate_comprehensive_delivery_analysis_corrected(file_path):
    """
    Calculate comprehensive delivery performance analysis starting from Day 1 (after TAT breach)
    Includes geographic, payment method, and route performance analysis
    """
    
    # Load the dataset
    print("📊 Loading dataset...")
    df = pd.read_csv(file_path)
    print(f"✅ Dataset loaded with {len(df):,} records")
    
    # Convert date columns to datetime
    date_columns = ['first_attempt_date', 'final_courier_edd', 'delivered_date', 'rapidshyp_edd']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Create enhanced EDD column using final_courier_edd with rapidshyp_edd as fallback
    df['effective_edd'] = df['final_courier_edd'].fillna(df['rapidshyp_edd'])
    
    # Filter out rows where both EDDs are missing
    initial_count = len(df)
    df = df.dropna(subset=['effective_edd'])
    print(f"🔍 Filtered dataset: {len(df):,} records (removed {initial_count - len(df):,} records with missing EDD)")
    
    # Get current date for undelivered shipments analysis
    current_date = datetime.now()
    
    # CORRECTED TAT breach calculation - only after EDD date, not on same date
    def calculate_tat_breach(row):
        effective_edd = row['effective_edd']
        first_attempt = row['first_attempt_date']
        delivered = row['delivered_date']
        status = row['tracking_status_group']
        
        # For delivered shipments, check if delivered AFTER EDD date (not on same date)
        if status == 'Delivered' and pd.notna(delivered):
            return delivered.date() > effective_edd.date()
        
        # For RTO/failed deliveries, check if first attempt was AFTER EDD date
        if status in ['RTO', 'Damage/Lost'] and pd.notna(first_attempt):
            return first_attempt.date() > effective_edd.date()
        
        # For undelivered shipments with attempt, check if attempt was AFTER EDD date
        if pd.isna(delivered) and pd.notna(first_attempt):
            return first_attempt.date() > effective_edd.date()
        
        # For shipments with no attempt made and we're past EDD date
        if pd.isna(first_attempt):
            return current_date.date() > effective_edd.date()
        
        return False
    
    df['tat_breach'] = df.apply(calculate_tat_breach, axis=1)
    df['delivery_success'] = (df['tracking_status_group'] == 'Delivered').astype(int)
    
    # CORRECTED days calculation - starts from Day 1
    def calculate_days_after_tat_breach(row):
        effective_edd = row['effective_edd']
        delivered = row['delivered_date']
        first_attempt = row['first_attempt_date']
        status = row['tracking_status_group']
        
        # For delivered shipments, use delivered_date
        if status == 'Delivered' and pd.notna(delivered):
            days = (delivered.date() - effective_edd.date()).days
            return max(1, days)  # Minimum Day 1
        
        # For RTO cases, use first_attempt_date
        elif status == 'RTO' and pd.notna(first_attempt):
            days = (first_attempt.date() - effective_edd.date()).days
            return max(1, days)  # Minimum Day 1
        
        # For other failed deliveries with attempt, use first_attempt_date
        elif status in ['Damage/Lost'] and pd.notna(first_attempt):
            days = (first_attempt.date() - effective_edd.date()).days
            return max(1, days)  # Minimum Day 1
        
        # For undelivered shipments with attempt, use first_attempt_date
        elif pd.isna(delivered) and pd.notna(first_attempt):
            days = (first_attempt.date() - effective_edd.date()).days
            return max(1, days)  # Minimum Day 1
        
        # For undelivered shipments with no attempt, use current date
        elif pd.isna(delivered) and pd.isna(first_attempt):
            days = (current_date.date() - effective_edd.date()).days
            return max(1, days)  # Minimum Day 1
        
        # Default fallback
        else:
            days = (current_date.date() - effective_edd.date()).days
            return max(1, days)  # Minimum Day 1
    
    # Apply days calculation only for TAT breach cases
    df.loc[df['tat_breach'], 'days_after_tat_breach'] = df.loc[df['tat_breach']].apply(
        calculate_days_after_tat_breach, axis=1
    )
    
    # Categorize shipment status
    def categorize_shipment_status(row):
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
            else:
                return 'Other'
    
    df['shipment_category'] = df.apply(categorize_shipment_status, axis=1)
    
    # Filter only TAT breach cases
    breach_df = df[df['tat_breach'] == True].copy()
    print(f"⚠️  TAT breach cases: {len(breach_df):,} records")
    
    if len(breach_df) == 0:
        print("❌ No TAT breach cases found in the dataset")
        return None, None
    
    # Show RTO statistics
    breach_rto_count = (breach_df['shipment_category'] == 'RTO').sum()
    print(f"📊 RTO cases in TAT breach data: {breach_rto_count:,}")
    print(f"📊 RTO percentage in TAT breach data: {(breach_rto_count/len(breach_df))*100:.2f}%")
    
    # Calculate daywise statistics (starting from Day 1)
    daywise_stats = breach_df.groupby('days_after_tat_breach').agg(
        total_shipments=('delivery_success', 'count'),
        successful_deliveries=('delivery_success', 'sum'),
        failed_deliveries=('delivery_success', lambda x: len(x) - sum(x)),
        delivered_count=('shipment_category', lambda x: sum(x == 'Delivered')),
        rto_count=('shipment_category', lambda x: sum(x == 'RTO')),
        damage_lost_count=('shipment_category', lambda x: sum(x == 'Damage/Lost')),
        undelivered_count=('shipment_category', lambda x: sum(x == 'Undelivered'))
    ).reset_index()
    
    daywise_stats['delivery_percentage'] = (daywise_stats['successful_deliveries'] / daywise_stats['total_shipments']) * 100
    daywise_stats['rto_rate'] = (daywise_stats['rto_count'] / daywise_stats['total_shipments']) * 100
    daywise_stats['drop_in_delivery_percentage'] = daywise_stats['delivery_percentage'].diff()
    
    return daywise_stats, breach_df

def calculate_payment_method_analysis(breach_df):
    """
    Calculate payment method performance analysis with RTO insights
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
    Calculate zone-wise performance analysis with RTO insights
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
    Calculate route performance analysis (pickup to delivery state)
    """
    print("\n🛣️  Calculating Route Performance Analysis...")
    
    route_performance = breach_df.groupby(['pickup_state', 'delivery_state', 'days_after_tat_breach']).agg(
        total_shipments=('delivery_success', 'count'),
        successful_deliveries=('delivery_success', 'sum'),
        delivered_count=('shipment_category', lambda x: sum(x == 'Delivered')),
        rto_count=('shipment_category', lambda x: sum(x == 'RTO')),
        undelivered_count=('shipment_category', lambda x: sum(x == 'Undelivered'))
    ).reset_index()
    
    route_performance['delivery_percentage'] = (route_performance['successful_deliveries'] / route_performance['total_shipments']) * 100
    route_performance['rto_rate'] = (route_performance['rto_count'] / route_performance['total_shipments']) * 100
    
    return route_performance

def calculate_parent_courier_performance(breach_df):
    """
    Calculate parent courier performance with RTO analysis
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

def create_summary_tables(df, analysis_type):
    """
    Create formatted summary tables for different analysis types
    """
    if analysis_type == "payment":
        summary = df[df['days_after_tat_breach'] <= 5].groupby('payment_method').agg(
            total_shipments=('total_shipments', 'sum'),
            total_delivered=('delivered_count', 'sum'),
            total_rto=('rto_count', 'sum'),
            avg_delivery_rate=('delivery_percentage', 'mean'),
            avg_rto_rate=('rto_rate', 'mean')
        ).reset_index()
        
    elif analysis_type == "zone":
        summary = df[df['days_after_tat_breach'] <= 5].groupby('applied_zone').agg(
            total_shipments=('total_shipments', 'sum'),
            total_delivered=('delivered_count', 'sum'),
            total_rto=('rto_count', 'sum'),
            avg_delivery_rate=('delivery_percentage', 'mean'),
            avg_rto_rate=('rto_rate', 'mean')
        ).reset_index()
        
    elif analysis_type == "route":
        summary = df[df['days_after_tat_breach'] <= 5].groupby(['pickup_state', 'delivery_state']).agg(
            total_shipments=('total_shipments', 'sum'),
            total_delivered=('delivered_count', 'sum'),
            total_rto=('rto_count', 'sum'),
            avg_delivery_rate=('delivery_percentage', 'mean'),
            avg_rto_rate=('rto_rate', 'mean')
        ).reset_index()
        summary = summary.nlargest(15, 'total_shipments')
        
    elif analysis_type == "courier":
        summary = df[df['days_after_tat_breach'] <= 5].groupby('parent_courier_name').agg(
            total_shipments=('total_shipments', 'sum'),
            total_delivered=('delivered_count', 'sum'),
            total_rto=('rto_count', 'sum'),
            avg_delivery_rate=('delivery_percentage', 'mean'),
            avg_rto_rate=('rto_rate', 'mean')
        ).reset_index()
    
    return summary

def format_summary_table(df):
    """
    Format summary tables for better readability
    """
    df_formatted = df.copy()
    
    # Format numeric columns
    numeric_cols = ['total_shipments', 'total_delivered', 'total_rto']
    for col in numeric_cols:
        if col in df_formatted.columns:
            df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:,}")
    
    # Format percentage columns
    percentage_cols = ['avg_delivery_rate', 'avg_rto_rate']
    for col in percentage_cols:
        if col in df_formatted.columns:
            df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:.2f}%")
    
    return df_formatted

def print_comprehensive_executive_summary(daywise_stats, payment_summary, zone_summary, courier_summary):
    """
    Print comprehensive executive summary with all analyses
    """
    print("\n" + "="*120)
    print("🎯 COMPREHENSIVE DELIVERY PERFORMANCE ANALYSIS AFTER TAT BREACH")
    print("(CORRECTED: Analysis starts from Day 1 - True TAT Breach Cases)")
    print("="*120)
    
    # Overall summary
    total_breach_cases = daywise_stats['total_shipments'].sum()
    overall_delivery_rate = (daywise_stats['successful_deliveries'].sum() / total_breach_cases) * 100
    total_rto = daywise_stats['rto_count'].sum()
    overall_rto_rate = (total_rto / total_breach_cases) * 100
    
    print(f"📈 Total TAT Breach Cases (Day 1+): {total_breach_cases:,}")
    print(f"📊 Overall Delivery Rate: {overall_delivery_rate:.2f}%")
    print(f"🔄 Total RTO Cases: {total_rto:,} ({overall_rto_rate:.1f}%)")
    print(f"📅 Analysis Period: Day 1 to Day {daywise_stats['days_after_tat_breach'].max()}")
    
    # Payment method insights
    print(f"\n💳 PAYMENT METHOD INSIGHTS:")
    print("-" * 50)
    cod_perf = payment_summary[payment_summary['payment_method'] == 'COD']
    prepaid_perf = payment_summary[payment_summary['payment_method'] == 'PREPAID']
    
    if not cod_perf.empty and not prepaid_perf.empty:
        cod_delivery = float(cod_perf['avg_delivery_rate'].iloc[0].replace('%', ''))
        prepaid_delivery = float(prepaid_perf['avg_delivery_rate'].iloc[0].replace('%', ''))
        cod_rto = float(cod_perf['avg_rto_rate'].iloc[0].replace('%', ''))
        prepaid_rto = float(prepaid_perf['avg_rto_rate'].iloc[0].replace('%', ''))
        
        print(f"• COD Performance: {cod_delivery:.2f}% delivery, {cod_rto:.2f}% RTO")
        print(f"• PREPAID Performance: {prepaid_delivery:.2f}% delivery, {prepaid_rto:.2f}% RTO")
        print(f"• Performance Gap: {abs(prepaid_delivery - cod_delivery):.2f}% delivery difference")
    
    # Zone insights
    print(f"\n🗺️  ZONE PERFORMANCE INSIGHTS:")
    print("-" * 50)
    best_zone = zone_summary.loc[zone_summary['avg_delivery_rate'].str.replace('%', '').astype(float).idxmax()]
    worst_zone = zone_summary.loc[zone_summary['avg_delivery_rate'].str.replace('%', '').astype(float).idxmin()]
    
    print(f"• Best Zone: {best_zone['applied_zone']} ({best_zone['avg_delivery_rate']} delivery)")
    print(f"• Worst Zone: {worst_zone['applied_zone']} ({worst_zone['avg_delivery_rate']} delivery)")
    
    # Courier insights
    print(f"\n📦 COURIER PERFORMANCE INSIGHTS:")
    print("-" * 50)
    best_courier = courier_summary.loc[courier_summary['avg_delivery_rate'].str.replace('%', '').astype(float).idxmax()]
    worst_courier = courier_summary.loc[courier_summary['avg_delivery_rate'].str.replace('%', '').astype(float).idxmin()]
    
    print(f"• Best Courier: {best_courier['parent_courier_name']} ({best_courier['avg_delivery_rate']} delivery)")
    print(f"• Worst Courier: {worst_courier['parent_courier_name']} ({worst_courier['avg_delivery_rate']} delivery)")

def analyze_comprehensive_delivery_performance_corrected(file_path):
    """
    Main function with corrected TAT breach logic starting from Day 1
    """
    try:
        print("🚀 Starting CORRECTED Comprehensive Delivery Performance Analysis...")
        print("(TAT Breach Analysis starts from Day 1 - True Breach Cases Only)")
        print("=" * 100)
        
        # Calculate main statistics
        daywise_stats, breach_df = calculate_comprehensive_delivery_analysis_corrected(file_path)
        
        if daywise_stats is not None and not daywise_stats.empty:
            # Calculate all performance analyses
            payment_perf = calculate_payment_method_analysis(breach_df)
            zone_perf = calculate_zone_performance_analysis(breach_df)
            route_perf = calculate_route_performance_analysis(breach_df)
            courier_stats = calculate_parent_courier_performance(breach_df)
            
            # Create summary tables
            payment_summary = format_summary_table(create_summary_tables(payment_perf, "payment"))
            zone_summary = format_summary_table(create_summary_tables(zone_perf, "zone"))
            route_summary = format_summary_table(create_summary_tables(route_perf, "route"))
            courier_summary = format_summary_table(create_summary_tables(courier_stats, "courier"))
            
            # Print comprehensive executive summary
            print_comprehensive_executive_summary(daywise_stats, payment_summary, zone_summary, courier_summary)
            
            # Display Day-wise Analysis (starting from Day 1)
            print(f"\n📋 DAY-WISE ANALYSIS (Days 1-15):")
            print("=" * 80)
            daywise_display = daywise_stats.head(15).copy()
            daywise_display['total_shipments'] = daywise_display['total_shipments'].apply(lambda x: f"{x:,}")
            daywise_display['delivered_count'] = daywise_display['delivered_count'].apply(lambda x: f"{x:,}")
            daywise_display['rto_count'] = daywise_display['rto_count'].apply(lambda x: f"{x:,}")
            daywise_display['delivery_percentage'] = daywise_display['delivery_percentage'].apply(lambda x: f"{x:.2f}%")
            daywise_display['rto_rate'] = daywise_display['rto_rate'].apply(lambda x: f"{x:.2f}%")
            daywise_display['drop_in_delivery_percentage'] = daywise_display['drop_in_delivery_percentage'].apply(
                lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A"
            )
            
            daywise_display.columns = ['Days After TAT', 'Total Shipments', 'Successful Deliveries', 'Failed Deliveries',
                                     'Delivered', 'RTO', 'Damage/Lost', 'Undelivered', 'Delivery Rate', 'RTO Rate', 'Daily Change']
            
            print(daywise_display[['Days After TAT', 'Total Shipments', 'Delivered', 'RTO', 'Delivery Rate', 'RTO Rate', 'Daily Change']].to_string(index=False))
            
            # Display Payment Method Analysis
            print(f"\n💳 PAYMENT METHOD ANALYSIS (Days 1-5 Summary):")
            print("=" * 80)
            payment_summary.columns = ['Payment Method', 'Total Shipments', 'Delivered', 'RTO', 'Avg Delivery Rate', 'Avg RTO Rate']
            print(payment_summary.to_string(index=False))
            
            # Display Zone Analysis
            print(f"\n🗺️  ZONE PERFORMANCE ANALYSIS (Days 1-5 Summary):")
            print("=" * 80)
            zone_summary.columns = ['Zone', 'Total Shipments', 'Delivered', 'RTO', 'Avg Delivery Rate', 'Avg RTO Rate']
            print(zone_summary.to_string(index=False))
            
            # Display Route Analysis
            print(f"\n🛣️  TOP ROUTE PERFORMANCE ANALYSIS (Days 1-5 Summary):")
            print("=" * 100)
            route_summary.columns = ['Pickup State', 'Delivery State', 'Total Shipments', 'Delivered', 'RTO', 'Avg Delivery Rate', 'Avg RTO Rate']
            print(route_summary.to_string(index=False))
            
            # Display Courier Analysis
            print(f"\n📦 PARENT COURIER ANALYSIS (Days 1-5 Summary):")
            print("=" * 80)
            courier_summary.columns = ['Parent Courier', 'Total Shipments', 'Delivered', 'RTO', 'Avg Delivery Rate', 'Avg RTO Rate']
            print(courier_summary.to_string(index=False))
            
            # Save all results
            base_output_file = file_path.replace('.csv', '_corrected_comprehensive_analysis')
            
            # Save all analyses
            daywise_stats.to_csv(f"{base_output_file}_daywise.csv", index=False)
            payment_perf.to_csv(f"{base_output_file}_payment_method.csv", index=False)
            zone_perf.to_csv(f"{base_output_file}_zone_performance.csv", index=False)
            route_perf.to_csv(f"{base_output_file}_route_performance.csv", index=False)
            courier_stats.to_csv(f"{base_output_file}_parent_courier.csv", index=False)
            
            # Save summary tables
            payment_summary.to_csv(f"{base_output_file}_payment_summary.csv", index=False)
            zone_summary.to_csv(f"{base_output_file}_zone_summary.csv", index=False)
            route_summary.to_csv(f"{base_output_file}_route_summary.csv", index=False)
            courier_summary.to_csv(f"{base_output_file}_courier_summary.csv", index=False)
            
            print(f"\n💾 Results saved to multiple CSV files:")
            print(f"• Day-wise Analysis: {base_output_file}_daywise.csv")
            print(f"• Payment Method Analysis: {base_output_file}_payment_method.csv")
            print(f"• Zone Performance: {base_output_file}_zone_performance.csv")
            print(f"• Route Performance: {base_output_file}_route_performance.csv")
            print(f"• Parent Courier Analysis: {base_output_file}_parent_courier.csv")
            print(f"• Summary Tables: {base_output_file}_*_summary.csv")
            
            print("✅ CORRECTED Comprehensive analysis completed successfully!")
            print("\n📝 Key Corrections Applied:")
            print("🔧 TAT Breach Logic: Now starts from Day 1 (true breach cases only)")
            print("💳 Payment Method Analysis: COD vs PREPAID performance with RTO insights")
            print("🗺️  Zone Performance: Geographic analysis with delivery and RTO rates")
            print("🛣️  Route Performance: Pickup to delivery state analysis")
            print("📊 Enhanced RTO Analysis: Comprehensive RTO tracking across all dimensions")
            
            return daywise_stats, payment_perf, zone_perf, route_perf, courier_stats
        else:
            print("❌ No analysis could be performed due to insufficient data.")
            return None, None, None, None, None
            
    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        return None, None, None, None, None

# Usage
if __name__ == "__main__":
    file_path = r"C:\Users\sanidhya.sinha\Desktop\3 Month Data.csv"  # Update with your file path
    daywise_results, payment_results, zone_results, route_results, courier_results = analyze_comprehensive_delivery_performance_corrected(file_path)
