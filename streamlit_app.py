import streamlit as st
from app import Neo4jApp # Import the main application class
import base64
from pathlib import Path
import pandas as pd
import pydeck as pdk
from geopy.geocoders import Nominatim
import time

# --- 1. Page Configuration ---
st.set_page_config(
    page_title="DreamKG",
    page_icon="logo.png",
    layout="centered",
)

# --- 2. Application Initialization ---
@st.cache_resource
def init_app():
    """Initializes the Neo4jApp and returns the instance."""
    try:
        app_instance = Neo4jApp()
        return app_instance
    except Exception as e:
        st.error(f"Application failed to initialize. Please check your configurations. Error: {e}", icon="🚨")
        return None

app = init_app()

# --- Geocoding Function with Caching ---
@st.cache_data
def geocode_address(address, org_name=None):
    """Converts an address string into latitude and longitude."""
    try:
        geolocator = Nominatim(user_agent="dream_kg_map_app_v2", timeout=10)
        time.sleep(1.5)  # Increased delay to avoid rate limiting
        
        # Try the full address first
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
        
        # If full address fails, try with just street and city
        if "Philadelphia" in address:
            simplified_address = address.split(",")[0] + ", Philadelphia, PA"
            location = geolocator.geocode(simplified_address)
            if location:
                return location.latitude, location.longitude
        
        # If that fails, try even more simplified
        if "Philadelphia" in address:
            very_simple = address.split(",")[0] + ", Philadelphia"
            location = geolocator.geocode(very_simple)
            if location:
                return location.latitude, location.longitude
        
        # If address fails completely, try the organization name + Philadelphia
        if org_name:
            org_location = geolocator.geocode(f"{org_name}, Philadelphia, PA")
            if org_location:
                return org_location.latitude, org_location.longitude
                
    except Exception as e:
        # Only show warning in debug, not to user
        pass
    return None, None

# --- 3. User Interface ---
@st.cache_data
def get_img_as_base64(file):
    if not Path(file).is_file():
        return None
    with open(file, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

img = get_img_as_base64("logo.png")

if img:
    st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 15px;">
            <img src="data:image/png;base64,{img}" width="60">
            <h1 style="margin: 0;">DreamKG</h1>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("---")

st.markdown("""
Welcome! Ask a question about services.

**For example:**
* Where can I find free Wi-Fi in zipcode 19121?
* Where can I find free Wi-Fi around Cecil B Moore?
""")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous messages and maps from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "map_deck" in message and message["map_deck"]:
            st.pydeck_chart(message["map_deck"])

# --- 4. Main Interaction Logic ---
if app:
    if prompt := st.chat_input("What are you looking for?"):
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            map_deck = None
            with st.spinner("Thinking..."):
                response, raw_data = app.process_user_request_for_streamlit(prompt)
                
                # --- FIXED MAP GENERATION LOGIC ---
                
                # Define the modern, smaller icon for the map pins
                ICON_URL = "https://img.icons8.com/fluency/48/marker.png"
                ICON_DATA = {
                    "url": ICON_URL,
                    "width": 128,
                    "height": 128,
                    "anchorY": 128,
                }
                
                if raw_data and response:
                    locations_to_map = []

                    for record in raw_data:
                        # Handle different possible data structures
                        org_info = record.get('org') or record.get('o') or {}
                        org_name = None
                        
                        # Try different ways to get organization name
                        if isinstance(org_info, dict):
                            org_name = org_info.get('name')
                        elif isinstance(org_info, str):
                            org_name = org_info
                        
                        # Also check if org name is directly in the record
                        if not org_name:
                            org_name = record.get('name') or record.get('organizationName')
                        
                        # Only proceed if we have an organization name and it's mentioned in the response
                        if org_name and org_name in response:
                            # Try to get location information from different possible structures
                            locations_list = record.get('locations', []) or record.get('l', [])
                            
                            # If locations_list is empty, try to get address info directly from record
                            if not locations_list:
                                address = record.get('streetAddress') or record.get('address')
                                if address:
                                    location_info = {
                                        'streetAddress': address,
                                        'city': record.get('city', ''),
                                        'state': record.get('state', ''),
                                        'zipCode': record.get('zipCode', '')
                                    }
                                    locations_list = [location_info]
                            
                            if locations_list:
                                location_info = locations_list[0]
                                
                                # Handle different ways address might be stored
                                address = None
                                if isinstance(location_info, dict):
                                    address = location_info.get('streetAddress') or location_info.get('address')
                                elif isinstance(location_info, str):
                                    address = location_info
                                
                                if address:
                                    city = location_info.get('city', '') if isinstance(location_info, dict) else ''
                                    state = location_info.get('state', '') if isinstance(location_info, dict) else ''
                                    zip_code = location_info.get('zipCode', '') if isinstance(location_info, dict) else ''
                                    
                                    # Clean up the address components
                                    full_address = f"{address}"
                                    if city:
                                        full_address += f", {city}"
                                    if state:
                                        full_address += f", {state}"
                                    if zip_code:
                                        full_address += f" {zip_code}"
                                    
                                    full_address = full_address.strip()
                                    locations_to_map.append({
                                        'name': org_name, 
                                        'address': full_address, 
                                        'icon_data': ICON_DATA
                                    })

                    if locations_to_map:
                        try:
                            df = pd.DataFrame(locations_to_map).drop_duplicates(subset=['address'])
                            
                            # Geocode addresses with better error handling
                            coords = []
                            successful_geocodes = 0
                            for idx, row in df.iterrows():
                                address = row['address']
                                org_name = row['name']
                                lat, lon = geocode_address(address, org_name)
                                coords.append({'lat': lat, 'lon': lon})
                                if lat is not None and lon is not None:
                                    successful_geocodes += 1
                            
                            coords_df = pd.DataFrame(coords)
                            df = pd.concat([df, coords_df], axis=1)
                            df.dropna(subset=['lat', 'lon'], inplace=True)
                            
                            # Only show map if we successfully geocoded at least one address
                            if not df.empty and successful_geocodes > 0:
                                # Use IconLayer with smaller, modern pins
                                layer = pdk.Layer(
                                    "IconLayer",
                                    data=df,
                                    get_icon="icon_data",
                                    get_size=3,
                                    size_scale=10,
                                    get_position='[lon, lat]',
                                    pickable=True
                                )
                                
                                # Calculate bounds to fit all pins
                                lat_min, lat_max = df['lat'].min(), df['lat'].max()
                                lon_min, lon_max = df['lon'].min(), df['lon'].max()
                                
                                # Calculate center
                                center_lat = (lat_min + lat_max) / 2
                                center_lon = (lon_min + lon_max) / 2
                                
                                # Calculate zoom level based on the span of coordinates
                                lat_span = lat_max - lat_min
                                lon_span = lon_max - lon_min
                                max_span = max(lat_span, lon_span)
                                
                                # Dynamic zoom calculation with bounds
                                if max_span == 0:  # Single point
                                    zoom_level = 15
                                elif max_span < 0.01:  # Very close points
                                    zoom_level = 14
                                elif max_span < 0.05:  # Close points
                                    zoom_level = 12
                                elif max_span < 0.1:   # Medium spread
                                    zoom_level = 11
                                elif max_span < 0.2:   # Wide spread
                                    zoom_level = 10
                                else:                   # Very wide spread
                                    zoom_level = 9
                                
                                # Add some padding by reducing zoom slightly for multiple points
                                if len(df) > 1:
                                    zoom_level = max(zoom_level - 0.5, 8)  # Minimum zoom of 8
                                
                                view_state = pdk.ViewState(
                                    latitude=center_lat,
                                    longitude=center_lon,
                                    zoom=zoom_level,
                                    pitch=0  # Top-down view
                                )
                                tooltip = {"html": "<b>{name}</b><br/>{address}", "style": {"color": "white"}}
                                
                                # Free map style options (choose one):
                                # Option 1: Default road style (similar to Google Maps)
                                # map_style = 'road'
                                
                                # Option 2: Light theme (clean, minimal)
                                # map_style = 'light' 
                                
                                # Option 3: Dark theme (good for data visualization)
                                # map_style = 'dark'
                                
                                # Option 4: No background map (just pins)
                                map_style = None
                                
                                map_deck = pdk.Deck(
                                    layers=[layer], 
                                    initial_view_state=view_state, 
                                    map_style=map_style,
                                    tooltip=tooltip
                                )
                            elif successful_geocodes == 0:
                                # Show info message if no addresses could be geocoded
                                st.info("Map not available - addresses could not be located for mapping.")
                        except Exception as e:
                            st.info("Map display temporarily unavailable.")

                # --- END OF FIXED MAP LOGIC ---

                st.markdown(response)
                if map_deck:
                    st.pydeck_chart(map_deck)

        st.session_state.messages.append({
            "role": "assistant", 
            "content": response, 
            "map_deck": map_deck 
        })
else:
    st.warning("Application is not available due to an initialization error.")