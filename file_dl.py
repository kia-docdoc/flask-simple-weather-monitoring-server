import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
import datetime
import re

def get_latest_file_by_date(url):
    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    
    # Find the <pre> tag containing the file list
    pre_tag = soup.find("pre")
    if not pre_tag:
        return "No <pre> tag found. Cannot parse the file list."

    file_entries = pre_tag.text.strip().split("\n")  # Split lines in the <pre> content
    files = []

    for entry in file_entries:
        # Use regex to parse the file name, date, and time
        match = re.search(r"(?P<file_name>\S+)\s+(?P<date>\d{2}-\w{3}-\d{4})\s+(?P<time>\d{2}:\d{2})", entry)
        if match:
            file_name = match.group("file_name")
            date_str = f"{match.group('date')} {match.group('time')}"

            try:
                # Parse the date
                last_modified = datetime.datetime.strptime(date_str, "%d-%b-%Y %H:%M")
                files.append((file_name, last_modified))
            except ValueError as e:
                print(f"Error parsing date '{date_str}': {e}")
                continue

    if not files:
        return "No files found with valid dates."

    # Find the file with the latest date
    latest_file = max(files, key=lambda x: x[1])
    return latest_file  # Return tuple: (file_name, last_modified)

def download_file(url, save_path):
    response = requests.get(url)
    response.raise_for_status()  # Ensure the request was successful

    # Write the content to the file
    with open(save_path, "wb") as file:
        file.write(response.content)
    print(f"File downloaded and saved as {save_path}")

# Example usage
directory_url = "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/weather_advisory/"
latest_file = get_latest_file_by_date(directory_url)

def run_dl():
    if isinstance(latest_file, str):
        print(latest_file)  # If no files found, latest_file will contain an error message
    else:
        file_name, last_modified = latest_file
        # Encode the file name to handle special characters like '#'
        encoded_file_name = quote(file_name)
        # Construct the full URL
        download_url = urljoin(directory_url, encoded_file_name)

        print(f"Download URL: {download_url}")
        print(f"Latest file: {file_name}")
        print(f"Last modified: {last_modified}\n")

        # Create the folder if it doesn't exist
        folder_path = "pagasa_alert"
        os.makedirs(folder_path, exist_ok=True)

        # Set the full path for the downloaded file
        save_path = os.path.join(folder_path, "advisory.pdf")

        # Download and save the file
        download_file(download_url, save_path)
