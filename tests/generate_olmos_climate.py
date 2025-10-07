import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pathlib

def generate_olmos_climate_data(start_year=2002, years=6):
    """
    Generate Cretaceous climate data in the EXACT format expected by Environment.py
    """
    
    dates = pd.date_range(start=f'{start_year}-01-01', 
                         periods=365*years, freq='D')
    
    hourly_data = []
    
    for date in dates:
        day_of_year = date.timetuple().tm_yday
        
        # Daily climate parameters (same as before)
        base_temp = 21.5
        seasonal_amplitude = 2.0
        seasonal_variation = seasonal_amplitude * np.sin(2 * np.pi * (day_of_year - 80) / 365)
        base_radiation = 2600
        radiation_amplitude = 400
        radiation_variation = radiation_amplitude * np.sin(2 * np.pi * (day_of_year - 172) / 365)
        base_humidity = 78
        
        for hour in range(24):
            # Generate hourly values
            daily_temp = base_temp + seasonal_variation + np.random.normal(0, 1.5)
            daily_radiation = base_radiation + radiation_variation + np.random.normal(0, 150)
            daily_humidity = base_humidity + np.random.normal(0, 4)
            
            # Diurnal patterns
            hour_angle = 2 * np.pi * (hour - 14) / 24
            
            # Temperature
            temp_amplitude = 4.0
            temp_variation = temp_amplitude * np.sin(hour_angle)
            hourly_temp = daily_temp + temp_variation + np.random.normal(0, 0.5)
            hourly_temp = max(15.0, min(28.0, hourly_temp))
            
            # Radiation
            if 6 <= hour <= 18:
                radiation_factor = np.sin(np.pi * (hour - 6) / 12)
                hourly_radiation = daily_radiation * radiation_factor
            else:
                hourly_radiation = 0
            hourly_radiation += np.random.normal(0, 50)
            hourly_radiation = max(0, hourly_radiation)
            
            # Humidity (inverse of temperature)
            humidity_variation = -8 * np.sin(hour_angle)
            hourly_humidity = daily_humidity + humidity_variation + np.random.normal(0, 2)
            hourly_humidity = max(60, min(95, hourly_humidity))
            
            # Format date exactly like the example
            formatted_date = date.replace(hour=hour).strftime('%d-%m-%Y %H:%M:%S')
            
            hourly_data.append({
                'Numero de la station': 'OLMOS001',
                'Nom de la station': 'Olmos Cretaceous',
                'Jour': formatted_date,
                'Heure': hour + 1,  # 1-24 instead of 0-23
                'tm': round(hourly_temp, 1),
                'glot': round(hourly_radiation, 0),
                'um': round(hourly_humidity, 1)
            })
    
    return pd.DataFrame(hourly_data)

def validate_format_compatibility(generated_df):
    """
    Validate that our generated data matches the expected format
    """
    print("=== Format Compatibility Check ===")
    print(f"Columns: {list(generated_df.columns)}")
    print(f"Date format sample: {generated_df['Jour'].iloc[0]}")
    print(f"Hour range: {generated_df['Heure'].min()} to {generated_df['Heure'].max()}")
    print(f"Temperature range: {generated_df['tm'].min():.1f} to {generated_df['tm'].max():.1f} °C")
    print(f"Radiation range: {generated_df['glot'].min()} to {generated_df['glot'].max()} J/cm²/h")
    print(f"Humidity range: {generated_df['um'].min():.1f} to {generated_df['um'].max():.1f} %")

def save_climate_data(df, output_path):
    """
    Save in the exact format expected by Environment.py
    """
    # Create directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save with the exact same format
    df.to_csv(output_path, index=False, sep=';')
    print(f"Saved Cretaceous climate data to: {output_path}")

# Main execution
if __name__ == "__main__":
    print("Generating Olmos Formation Cretaceous climate data...")
    
    # Generate data in the correct format
    climate_data = generate_olmos_climate_data(start_year=2002, years=6)
    
    # Validate format
    validate_format_compatibility(climate_data)
    
    # Determine output path
    project_root = pathlib.Path(__file__).resolve().parent.parent
    output_path = project_root / 'vmlab' / 'data' / 'environment' / 'olmos_cretaceous_weather.csv'
    
    # Save the data
    save_climate_data(climate_data, output_path)
    
    # Additional validation
    print(f"\nGenerated {len(climate_data)} hourly records")
    print(f"Date range: {climate_data['Jour'].min()} to {climate_data['Jour'].max()}")
    
    # Climate validation
    mat = climate_data['tm'].mean()
    print(f"\nClimate Validation:")
    print(f"Mean Annual Temperature: {mat:.1f}°C")
    print(f"✓ Within Olmos Formation range (20-23°C)" if 20 <= mat <= 23 else f"✗ Outside expected range")