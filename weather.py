import requests
import os
import time
import file_dl
import importlib
import atexit
from flask import Flask, render_template, Response, request, redirect, url_for, jsonify, send_file
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from pytz import timezone as ptz
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

#Run once checker
initialized = False

# Directory to store downloaded images
SATELLITE_IMAGES_DIR = "static/satellite_images"
os.makedirs(SATELLITE_IMAGES_DIR, exist_ok=True)  # Ensure directory exists

# Weather API and PAGASA settings
WEATHER_API_KEY = "d3fa937c2fb167613c83a82b7324c32d"
WEATHER_API_URL = "https://api.openweathermap.org/data/2.5/onecall"
PAGASA_ALERTS_URL = "https://www.pagasa.dost.gov.ph/"

def dl_advisory():
    try:
        importlib.reload(file_dl)
        file_dl.run_dl()
        print("Advisory updated!\n")
    except:
        print("Error downloading advisory file.\n")

def is_url_accessible(url):
    try:
        response = requests.head(url, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Error checking URL {url}: {e}")
        return False

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %I:%M %p'):
    # Convert the UTC timestamp to Philippine time
    philippine_time = ptz('Asia/Manila')
    utc_time = datetime.fromtimestamp(value, tz=timezone.utc)
    local_time = utc_time.astimezone(philippine_time)
    return local_time.strftime(format)
    
def update_satellite_images():
    """API endpoint to get and save the last six satellite images."""
    print("Updating satellite images...")
    now = datetime.now(timezone.utc)
    valid_images = []

    for i in range(6):
        # Calculate time for each image (20-minute delay, 10-minute intervals)
        delayed_time = now - timedelta(minutes=20 + i * 10)
        adjusted_minute = (delayed_time.minute // 10) * 10
        satellite_time = delayed_time.replace(minute=adjusted_minute, second=0, microsecond=0).strftime('%H%M')
        satellite_url = f"https://www.data.jma.go.jp/mscweb/data/himawari/img/se2/se2_hrp_{satellite_time}.jpg"
        local_filename = f"{SATELLITE_IMAGES_DIR}/satellite_{satellite_time}.jpg"
        print(f"Downloading image: {satellite_url}")

        if is_url_accessible(satellite_url):
            # Download and save the image locally
            try:
                response = requests.get(satellite_url, stream=True)
                if response.status_code == 200:
                    with open(local_filename, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
                    valid_images.append(local_filename)
                    time.sleep(1)
                else:
                    print('Image is already in directory. Download skipped!')
            except Exception as e:
                print(f"Error downloading image {satellite_url}: {e}\n")

    # Fallback: Add the last working image if fewer than 6 valid images are found
    if len(valid_images) < 6:
        fallback_image = f"{valid_images[0]}"
        while len(valid_images) < 6:
            valid_images.append(fallback_image)

    # Keep only the latest six images in the directory
    all_images = sorted((os.path.join(SATELLITE_IMAGES_DIR, f) for f in os.listdir(SATELLITE_IMAGES_DIR) if os.path.isfile(os.path.join(SATELLITE_IMAGES_DIR, f))), key=os.path.getmtime,reverse=True)
    
    print(f"\nImages before cleanup: {all_images}\n")
    try:
        for image in all_images[6:]:
            img_path = os.path.normpath(image)
            print('Removing: ', img_path)
            os.remove(img_path)
            print(f"Successfuly removed {img_path}\n")
    except:
        print('Cleanup failed.\n')
        pass
        
    print("Satellite image updated!\n")

# Initialize APScheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=update_satellite_images, trigger="interval", minutes=10, misfire_grace_time=3600, max_instances=1)  # Update every 10 minutes
scheduler.add_job(func=dl_advisory, trigger="interval", minutes=30, misfire_grace_time=3600, max_instances=1)  # Update every 30 minutes
scheduler.start()

print("\nScheduled Jobs:")
for job in scheduler.get_jobs():
    print(job)
print('')

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

@app.route('/api/satellite-images')
def get_satellite_images():
    """API endpoint to return the list of pre-fetched satellite images."""
    print("\nGetting satellite images.")
    images = sorted(os.listdir(SATELLITE_IMAGES_DIR), reverse=True)[:6]
    return jsonify({"images": [f"/{SATELLITE_IMAGES_DIR}/{image}" for image in images]})

 
@app.route('/')
def index():
    city = request.args.get('city', 'Ozamiz')
    weather_data = get_weather_data(city)
    
    # Check for Cloudflare's CF-Connecting-IP header first
    client_ip = request.headers.get('CF-Connecting-IP')

    # If not behind Cloudflare, fall back to X-Forwarded-For or remote_addr
    if not client_ip:
        forwarded_for = request.headers.get('X-Forwarded-For')
        if forwarded_for:
            client_ip = forwarded_for.split(',')[0].strip()
        else:
            client_ip = request.remote_addr

    print(f"\nYour IP address is {client_ip}\n")

    return render_template(
        'index.html', 
        city=city, 
        weather_data=weather_data
    )

@app.route('/pin', methods=['POST'])
def pin_city():
    city = request.form.get('city')
    return redirect(url_for('index', city=city))
    
@app.route('/api/weather')
def get_weather_data_api():
    city = request.args.get('city', 'Ozamiz')  # Default to Manila if no city is provided
    weather_data = get_weather_data(city)
    if weather_data:
        return jsonify(weather_data)
    return jsonify({"error": "Weather data unavailable"}), 500

def get_weather_data(city):
    try:
        # Fetch current weather data
        current_url = "https://api.openweathermap.org/data/2.5/weather"
        forecast_url = "https://api.openweathermap.org/data/2.5/forecast"

        params = {
            "q": city,
            "appid": WEATHER_API_KEY,
            "units": "metric",
        }

        current_response = requests.get(current_url, params=params)
        current_response.raise_for_status()
        current_weather = current_response.json()

        forecast_response = requests.get(forecast_url, params=params)
        forecast_response.raise_for_status()
        forecast_weather = forecast_response.json()

        return {
            "current": current_weather,
            "forecast": forecast_weather,
        }
    except Exception as e:
        print(f"Error fetching weather data: {e}\n")
        return None
        
@app.route('/pagasa_alert/advisory')
def serve_advisory_pdf():
    file_path = './pagasa_alert/advisory.pdf'  # Adjust the path based on your file location
    
    def generate():
        with open(file_path, 'rb') as file:
            while chunk := file.read(8192):  # Read in 8KB chunks
                yield chunk

    file_size = os.path.getsize(file_path)
    headers = {
        'Content-Disposition': 'inline; filename="advisory.pdf"',
        'Content-Length': str(file_size),
        'Content-Type': 'application/pdf',
    }

    return Response(generate(), headers=headers)

        
@app.before_request
def initialize_satellite_images():
    global initialized
    if not initialized:
        print("\nInitializing...\n")
        dl_advisory()
        update_satellite_images()
        print("Initialization complete!\n")
        initialized = True

if __name__ == '__main__':
    app.run(debug=True, port=2025, host='::')
