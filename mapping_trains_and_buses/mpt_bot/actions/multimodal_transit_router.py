# actions/multimodal_transit_router.py
import pandas as pd
import os
from collections import deque
import time
import folium
from datetime import datetime
import webbrowser
from geopy.geocoders import Nominatim
from scipy.spatial import KDTree
from geopy.distance import geodesic
import openrouteservice

class MultimodalTransitRouter:
    def __init__(self):
        self.api_key = '5b3ce3597851110001cf6248a6b7c97bb850491794bb504b30e2f2f7'
        start_time = time.time()
        print("Starting router initialization")
        
        self.load_transit_data()
        self._build_network()
        self._build_shape_cache()
        print(f"\nTotal initialization took {time.time() - start_time:.2f} seconds")

    def load_transit_data(self):
        """Load both bus and train GTFS data"""
        bus_dir = os.path.join('..', 'mpt_data', 'bus')
        train_dir = os.path.join('..', 'mpt_data', 'train')
        
        print("\nLoading GTFS files")
        file_load_start = time.time()
        
        # Load and combine bus and train data
        self.stops = pd.concat([
            pd.read_csv(os.path.join(bus_dir, 'stops.txt')).assign(mode='bus'),
            pd.read_csv(os.path.join(train_dir, 'stops.txt')).assign(mode='train')
        ], ignore_index=True)
        
        self.routes = pd.concat([
            pd.read_csv(os.path.join(bus_dir, 'routes.txt')).assign(mode='bus'),
            pd.read_csv(os.path.join(train_dir, 'routes.txt')).assign(mode='train')
        ], ignore_index=True)
        
        self.trips = pd.concat([
            pd.read_csv(os.path.join(bus_dir, 'trips.txt')),
            pd.read_csv(os.path.join(train_dir, 'trips.txt'))
        ], ignore_index=True)
        
        self.stop_times = pd.concat([
            pd.read_csv(os.path.join(bus_dir, 'stop_times.txt')),
            pd.read_csv(os.path.join(train_dir, 'stop_times.txt'))
        ], ignore_index=True)
        
        self.shapes = pd.concat([
            pd.read_csv(os.path.join(bus_dir, 'shapes.txt')),
            pd.read_csv(os.path.join(train_dir, 'shapes.txt'))
        ], ignore_index=True)
        
        print(f"File loading took {time.time() - file_load_start:.2f} seconds")
        
        # Normalize stop names and create search index
        self.stops['normalized_stop_name'] = self.stops['stop_name'].str.lower()

    def _build_network(self):
        """Build transit network and KDTree for spatial queries"""
        merge_start = time.time()
        
        # Build transit connections
        stop_route_data = self.stop_times.merge(
            self.trips[['trip_id', 'route_id']], 
            on='trip_id'
        )[['stop_id', 'route_id']]
        
        print(f"Merging dataframes took {time.time() - merge_start:.2f} seconds")
        
        mapping_start = time.time()
        self.stop_routes = {
            stop_id: set(group['route_id']) 
            for stop_id, group in stop_route_data.groupby('stop_id')
        }
        
        self.route_stops = {
            route_id: set(group['stop_id']) 
            for route_id, group in stop_route_data.groupby('route_id')
        }
        
        # Build KDTree for spatial queries
        self.kdtree = KDTree(self.stops[["stop_lat", "stop_lon"]].values)
        
        print(f"Building mappings took {time.time() - mapping_start:.2f} seconds")

    def _build_shape_cache(self):
        """Build cache of shape points for all routes"""
        print("Building shape cache")
        shape_start = time.time()
        
        # Get shape_id for each route using trips table
        route_shapes = {}
        for _, trip in self.trips.iterrows():
            route_shapes[trip['route_id']] = trip['shape_id']
        
        # Create cache of shape points
        self.route_shapes = {}
        for route_id, shape_id in route_shapes.items():
            shape_points = (
                self.shapes[self.shapes['shape_id'] == shape_id]
                .sort_values('shape_pt_sequence')[['shape_pt_lat', 'shape_pt_lon']]
                .values.tolist()
            )
            self.route_shapes[route_id] = shape_points
        
        print(f"Shape cache built in {time.time() - shape_start:.2f} seconds")

    def _get_route_segment(self, route_id, start_stop_id, end_stop_id):
        """Get shape points for a segment of a route between two stops"""
        if route_id not in self.route_shapes:
            print(f"Warning: No shape data found for route {route_id}")
            return None
            
        # Get stop coordinates
        start_stop = self.stops[self.stops['stop_id'] == start_stop_id].iloc[0]
        end_stop = self.stops[self.stops['stop_id'] == end_stop_id].iloc[0]
        start_coord = [start_stop['stop_lat'], start_stop['stop_lon']]
        end_coord = [end_stop['stop_lat'], end_stop['stop_lon']]
        
        # Get full shape for the route
        shape_points = self.route_shapes[route_id]
        
        # Find closest points on shape to our stops
        start_idx = min(range(len(shape_points)), 
                       key=lambda i: ((shape_points[i][0] - start_coord[0])**2 + 
                                    (shape_points[i][1] - start_coord[1])**2))
        end_idx = min(range(len(shape_points)), 
                     key=lambda i: ((shape_points[i][0] - end_coord[0])**2 + 
                                  (shape_points[i][1] - end_coord[1])**2))
        
        # Return points in correct order
        if start_idx <= end_idx:
            return shape_points[start_idx:end_idx + 1]
        else:
            return shape_points[end_idx:start_idx + 1][::-1]

    def find_nearest_stops(self, lat, lon, radius=500, limit=3):
        """Find stops within radius meters of the given coordinates"""
        # Query KDTree for nearest neighbors
        distances, indices = self.kdtree.query([lat, lon], k=10)  # Get more than we need
        
        nearby_stops = []
        for idx in indices:
            stop = self.stops.iloc[idx]
            dist = geodesic((lat, lon), (stop["stop_lat"], stop["stop_lon"])).meters
            if dist <= radius:
                nearby_stops.append((stop, dist))
                
        # Sort by distance and return top 'limit' stops
        return sorted(nearby_stops, key=lambda x: x[1])[:limit]

    def get_walking_route(self, from_lat, from_lon, to_lat, to_lon):
        """Get walking route using OpenRouteService"""
        client = openrouteservice.Client(key=self.api_key)
        coords = [[from_lon, from_lat], [to_lon, to_lat]]
        try:
            return client.directions(coordinates=coords, profile='foot-walking', format='geojson')
        except Exception as e:
            print(f"Error getting walking route: {e}")
            return None

    def _find_multimodal_route(self, start_stops, end_stops):
        """Find route including walking between transit modes"""
        queue = deque([])
        visited = set()
        
        # Initialize queue with start stops
        for start_stop, start_dist in start_stops:
            queue.append((start_stop['stop_id'], [start_stop['stop_id']], [], start_dist))
            visited.add(start_stop['stop_id'])
        
        while queue:
            current_stop_id, path, transfers, total_dist = queue.popleft()
            
            # Check if we've reached a destination stop
            if any(current_stop_id == end_stop['stop_id'] for end_stop, _ in end_stops):
                return path, transfers
            
            # Get all routes from current stop
            routes = self.stop_routes.get(current_stop_id, set())
            
            # Try each route
            for route_id in routes:
                route_info = self.routes[self.routes['route_id'] == route_id].iloc[0]
                for next_stop_id in self.route_stops[route_id]:
                    if next_stop_id not in visited:
                        visited.add(next_stop_id)
                        
                        # Add transit segment
                        next_stop = self.stops[self.stops['stop_id'] == next_stop_id].iloc[0]
                        current_stop = self.stops[self.stops['stop_id'] == current_stop_id].iloc[0]
                        
                        new_transfers = transfers + [{
                            'type': 'transit',
                            'mode': route_info['mode'],
                            'route': route_info['route_short_name'],
                            'route_id': route_id,
                            'from_stop': current_stop_id,
                            'to_stop': next_stop_id,
                            'from_lat': current_stop['stop_lat'],
                            'from_lon': current_stop['stop_lon'],
                            'to_lat': next_stop['stop_lat'],
                            'to_lon': next_stop['stop_lon']
                        }]
                        
                        queue.append((next_stop_id, path + [next_stop_id], new_transfers, total_dist))
            
            # Try walking to nearby stops of different modes
            current_stop = self.stops[self.stops['stop_id'] == current_stop_id].iloc[0]
            nearby = self.find_nearest_stops(current_stop['stop_lat'], current_stop['stop_lon'])
            
            for next_stop, walk_dist in nearby:
                if next_stop['stop_id'] not in visited and next_stop['mode'] != current_stop['mode']:
                    visited.add(next_stop['stop_id'])
                    
                    # Add walking segment
                    new_transfers = transfers + [{
                        'type': 'walking',
                        'from_lat': current_stop['stop_lat'],
                        'from_lon': current_stop['stop_lon'],
                        'to_lat': next_stop['stop_lat'],
                        'to_lon': next_stop['stop_lon'],
                        'distance': walk_dist
                    }]
                    
                    queue.append((next_stop['stop_id'], path + [next_stop['stop_id']], new_transfers, total_dist + walk_dist))
        
        return None, None

    def visualize_route(self, start_coords, end_coords, path, transfers):
        """Visualize the complete route including walking segments"""
        m = folium.Map(location=[start_coords[0], start_coords[1]], zoom_start=13)
        
        # Colors for different modes
        colors = {
            'bus': {
                'blue': '#0066CC',
                'red': '#CC0000',
                'green': '#009933',
                'purple': '#660099',
                'orange': '#FF6600',
            },
            'train': {
                'blue': '#000066',
                'red': '#660000',
                'green': '#006600',
                'purple': '#330066',
                'orange': '#CC3300',
            }
        }
        
        # Add markers for start and end
        folium.Marker(
            [start_coords[0], start_coords[1]],
            popup='Start',
            icon=folium.Icon(color='green')
        ).add_to(m)
        
        folium.Marker(
            [end_coords[0], end_coords[1]],
            popup='End',
            icon=folium.Icon(color='red')
        ).add_to(m)
        
        # Track used colors for each mode
        used_colors = {'bus': 0, 'train': 0}
        
        # Draw each segment
        for transfer in transfers:
            if transfer['type'] == 'walking':
                walking_route = self.get_walking_route(
                    transfer['from_lat'], transfer['from_lon'],
                    transfer['to_lat'], transfer['to_lon']
                )
                
                if walking_route:
                    folium.GeoJson(
                        walking_route,
                        style_function=lambda x: {'color': '#00FF00', 'weight': 3, 'opacity': 0.7},
                        popup=f'Walking ({transfer["distance"]:.0f}m)'
                    ).add_to(m)
                else:
                    print(f"Warning: Could not get walking route for segment")
                    continue
                
            elif transfer['type'] == 'transit':
                segment_points = self._get_route_segment(
                    transfer['route_id'],
                    transfer['from_stop'],
                    transfer['to_stop']
                )
                
                if not segment_points:
                    print(f"Warning: Could not get route segment for {transfer['mode']} {transfer['route']}")
                    continue
                
                # Choose color based on mode
                mode = transfer['mode']
                color_idx = used_colors[mode]
                color = list(colors[mode].values())[color_idx % len(colors[mode])]
                used_colors[mode] += 1
                
                # Draw the route line using shape points
                folium.PolyLine(
                    locations=segment_points,
                    weight=4,
                    color=color,
                    popup=f"{mode.title()} {transfer['route']}",
                    opacity=0.8
                ).add_to(m)
                
                # Add route label at midpoint
                if len(segment_points) >= 2:
                    mid_idx = len(segment_points) // 2
                    mid_point = segment_points[mid_idx]
                    folium.DivIcon(
                        html=f'<div style="background-color: {color}; color: white; padding: 3px 6px; border-radius: 3px; font-weight: bold;">{mode.title()} {transfer["route"]}</div>',
                        icon_size=(70, 20),
                        icon_anchor=(35, 10)
                    ).add_to(folium.Marker(mid_point).add_to(m))
        
        # Add markers for transit stops
        for i, stop_id in enumerate(path):
            stop = self.stops[self.stops['stop_id'] == stop_id].iloc[0]
            
            if i == 0:
                icon_color = 'green'
                prefix = 'Start'
  

            elif i == len(path) - 1:
                icon_color = 'red'
                prefix = 'End'
            else:
                icon_color = 'blue'
                prefix = 'Transfer'
            
            folium.Marker(
                [stop['stop_lat'], stop['stop_lon']],
                popup=f"{prefix}: {stop['stop_name']}",
                icon=folium.Icon(color=icon_color, icon='info-sign')
            ).add_to(m)
        
        # Save map
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        output_dir = os.path.join('..', 'mpt_data', 'maps')
        os.makedirs(output_dir, exist_ok=True)
        map_file = os.path.join(output_dir, f'multimodal_route_{timestamp}.html')
        m.save(map_file)
        return map_file

    def find_route(self, start_location, end_location):
        """Find and visualize a route between two locations"""
        # Geocode locations
        geolocator = Nominatim(user_agent="multimodal_router", timeout=10)
        start_loc = geolocator.geocode(start_location + ", Melbourne", exactly_one=True)
        end_loc = geolocator.geocode(end_location + ", Melbourne", exactly_one=True)
        
        if not start_loc or not end_loc:
            return "Could not geocode one or both locations"
        
        # Find nearest stops to start and end
        start_stops = self.find_nearest_stops(start_loc.latitude, start_loc.longitude)
        end_stops = self.find_nearest_stops(end_loc.latitude, end_loc.longitude)
        
        if not start_stops or not end_stops:
            return "No transit stops found near one or both locations"
        
        # Find route
        path, transfers = self._find_multimodal_route(start_stops, end_stops)
        
        if not path:
            return "No route found"
        
        # Add initial and final walking segments
        try:
            first_stop = self.stops[self.stops['stop_id'] == path[0]].iloc[0]
            last_stop = self.stops[self.stops['stop_id'] == path[-1]].iloc[0]
            
            # Initial walking segment
            initial_walk_dist = geodesic(
                (start_loc.latitude, start_loc.longitude),
                (first_stop['stop_lat'], first_stop['stop_lon'])
            ).meters
            
            # Final walking segment
            final_walk_dist = geodesic(
                (last_stop['stop_lat'], last_stop['stop_lon']),
                (end_loc.latitude, end_loc.longitude)
            ).meters
            
            transfers = [{
                'type': 'walking',
                'from_lat': start_loc.latitude,
                'from_lon': start_loc.longitude,
                'to_lat': first_stop['stop_lat'],
                'to_lon': first_stop['stop_lon'],
                'distance': initial_walk_dist,
                'description': f'Walk to {first_stop["stop_name"]}'
            }] + transfers + [{
                'type': 'walking',
                'from_lat': last_stop['stop_lat'],
                'from_lon': last_stop['stop_lon'],
                'to_lat': end_loc.latitude,
                'to_lon': end_loc.longitude,
                'distance': final_walk_dist,
                'description': f'Walk from {last_stop["stop_name"]} to destination'
            }]
            
        except Exception as e:
            print(f"Warning: Could not generate walking segments: {e}")
            return "Error generating route segments"
        
        try:
            # Generate text directions
            directions = ["Route found:"]
            total_walking = 0
            total_transfers = 0
            
            for transfer in transfers:
                if transfer['type'] == 'walking':
                    if 'description' in transfer:
                        directions.append(f"{transfer['description']} ({transfer['distance']:.0f}m)")
                    else:
                        directions.append(f"Walk {transfer['distance']:.0f}m")
                    total_walking += transfer['distance']
                else:
                    directions.append(f"Take {transfer['mode']} {transfer['route']} to {self.stops[self.stops['stop_id'] == transfer['to_stop']].iloc[0]['stop_name']}")
                    total_transfers += 1
            
            directions.append(f"\nTotal transfers: {total_transfers}")
            directions.append(f"Total walking distance: {total_walking:.0f}m")
            
            # Visualize route
            map_file = self.visualize_route(
                (start_loc.latitude, start_loc.longitude),
                (end_loc.latitude, end_loc.longitude),
                path,
                transfers
            )
            
            return "\n".join(directions), map_file
            
        except Exception as e:
            print(f"Error generating directions: {e}")
            return "Error generating directions"


