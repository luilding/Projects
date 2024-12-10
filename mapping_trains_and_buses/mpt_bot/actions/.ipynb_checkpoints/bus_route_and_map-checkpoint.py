import requests
import folium
from geopy.geocoders import Nominatim
from datetime import datetime
import pandas as pd
from scipy.spatial import KDTree
from geopy.distance import geodesic
import os
import webbrowser

def geocode_address(address):
    geolocator = Nominatim(user_agent="bus_mapping_app1.0")
    melbourne_bbox = [(-38.5267, 144.5937), (-37.5113, 145.5125)]
    location = geolocator.geocode(address, viewbox=melbourne_bbox, bounded=True)
    
    if location:
        return location.latitude, location.longitude
    else:
        print("Address not found within Melbourne.")
        return None

def find_nearest_stop(lat, lon, kdtree, df):
    # Find nearest bus stop using KDTree
    distance, index = kdtree.query([lat, lon])
    nearest_stop = df.iloc[index]
    
    # Calculate actual distance
    stop_coords = (nearest_stop["stop_lat"], nearest_stop["stop_lon"])
    point_coords = (lat, lon)
    distance_meters = geodesic(point_coords, stop_coords).meters
    
    return nearest_stop, distance_meters, distance

def visualize_route(start_location, start_stop, end_location, end_stop):
    # Create a map centered at the starting location
    m = folium.Map(location=[start_location[0], start_location[1]], zoom_start=13)
    
    # Add markers for start and end locations
    folium.Marker(
        [start_location[0], start_location[1]],
        popup="Start",
        icon=folium.Icon(color='green')
    ).add_to(m)
    
    folium.Marker(
        [end_location[0], end_location[1]],
        popup="Destination",
        icon=folium.Icon(color='red')
    ).add_to(m)
    
    # Add markers for bus stops
    folium.Marker(
        [start_stop["stop_lat"], start_stop["stop_lon"]],
        popup=f"Bus Stop: {start_stop['stop_name']}",
        icon=folium.Icon(color='blue')
    ).add_to(m)
    
    folium.Marker(
        [end_stop["stop_lat"], end_stop["stop_lon"]],
        popup=f"Bus Stop: {end_stop['stop_name']}",
        icon=folium.Icon(color='blue')
    ).add_to(m)
    
    # Draw lines for walking and bus routes
    # Walking to first bus stop
    folium.PolyLine(
        locations=[[start_location[0], start_location[1]], 
                  [start_stop["stop_lat"], start_stop["stop_lon"]]],
        weight=2,
        color='green',
        opacity=0.8
    ).add_to(m)
    
    # Bus route
    folium.PolyLine(
        locations=[[start_stop["stop_lat"], start_stop["stop_lon"]], 
                  [end_stop["stop_lat"], end_stop["stop_lon"]]],
        weight=2,
        color='blue',
        opacity=0.8
    ).add_to(m)
    
    # Walking from last bus stop
    folium.PolyLine(
        locations=[[end_stop["stop_lat"], end_stop["stop_lon"]], 
                  [end_location[0], end_location[1]]],
        weight=2,
        color='red',
        opacity=0.8
    ).add_to(m)
    
    # Generate timestamp for unique filename
    current_dir = os.path.dirname(os.path.abspath(__file__))
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    map_file = os.path.join(current_dir, 'mpt_data', f'bus_directions_{timestamp}.html')
    
    # Save the map
    m.save(map_file)
    return map_file

# Main execution
if __name__ == "__main__":
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Path to bus stops file
    stops_file_path = os.path.join(script_dir, 'mpt_data', 'bus', 'stops.txt')
    
    print("\nBus Route Planner")
    print("-----------------")
    
    try:
        # Read the bus stops file
        df = pd.read_csv(stops_file_path)
        coords = df[["stop_lat", "stop_lon"]].values
        
        # Create the k-d tree
        kdtree = KDTree(coords)
        
        # Get user input
        current_location = input("\nEnter your starting location: ")
        destination_input = input("Enter your destination: ")
        
        print("\nProcessing your request...")
        
        # Geocode the current location
        start_coords = geocode_address(current_location)
        if not start_coords:
            print("Could not find starting location.")
            exit()
            
        # Find nearest bus stop to start location
        nearest_start_stop, start_distance, _ = find_nearest_stop(start_coords[0], start_coords[1], kdtree, df)
        
        # Geocode the destination
        end_coords = geocode_address(destination_input)
        if not end_coords:
            print("Could not find destination location.")
            exit()
        
        # Find nearest bus stop to destination
        nearest_end_stop, end_distance, _ = find_nearest_stop(end_coords[0], end_coords[1], kdtree, df)
        
        # Generate the map
        map_file = visualize_route(
            start_coords, 
            nearest_start_stop, 
            end_coords, 
            nearest_end_stop
        )
        
        # Print route information
        print("\nRoute Details:")
        print(f"1. Walk {start_distance:.0f} meters to {nearest_start_stop['stop_name']} bus stop")
        print(f"2. Take bus to {nearest_end_stop['stop_name']}")
        print(f"3. Walk {end_distance:.0f} meters to your destination")
        
        print(f"\nMap saved as: {map_file}")
        
        # Automatically open the map in default browser
        webbrowser.open('file://' + os.path.abspath(map_file))
        
    except FileNotFoundError:
        print(f"Error: Could not find bus stops data file at {stops_file_path}")
    except Exception as e:
        print(f"An error occurred: {str(e)}")