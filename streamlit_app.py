import streamlit as st
from app import Neo4jApp # Import the main application class
import base64
from pathlib import Path
import time

# --- 1. Page Configuration ---
# Sets the title, icon, and layout for the web app. This should be the first Streamlit command.
st.set_page_config(
    page_title="DreamKG",
    page_icon="logo.png",
    layout="centered",
)

# --- 2. Application Initialization ---
# This function initializes the main Neo4jApp.
# @st.cache_resource ensures that this complex, expensive object is created only once
# and is shared across all user sessions and reruns.
@st.cache_resource
def init_app():
    """Initializes the Neo4jApp and returns the instance."""
    try:
        # Create an instance of the main application class from app.py
        app_instance = Neo4jApp() #
        return app_instance
    except Exception as e:
        # If initialization fails (e.g., bad secrets), show an error and stop.
        st.error(f"Application failed to initialize. Please check your configurations. Error: {e}", icon="🚨")
        return None

# Initialize the app. If it fails, the rest of the script won't run.
app = init_app()

# --- 3. User Interface ---
# --- Function to load and encode the image ---
@st.cache_data
def get_img_as_base64(file):
    if not Path(file).is_file():
        return None
    with open(file, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

# --- Load the image ---
img = get_img_as_base64("logo.png")

# --- Custom Title using a single HTML block ---
if img:
    # We now use 'gap' on the container to create space, and remove all margins from the h1.
    # The 'align-items: center;' property will now perfectly center both items vertically.
    st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 15px;">
            <img src="data:image/png;base64,{img}" width="60">
            <h1 style="margin: 0;">DreamKG</h1>
        </div>
        """,
        unsafe_allow_html=True
    )

# Add a horizontal line to separate the title from the rest of the content
st.markdown("---")

# The rest of your app's code follows...
# st.markdown("Welcome! Ask a question...")
st.markdown("""
Welcome! Ask a question about services.

**For example:**
* Where can I find free Wi-Fi in zipcode 19121?
* Where can I find free Wi-Fi around Cecil B Moore?
* Are there any public computers near Wadsworth Library?
""")

# Initialize a session state variable to store the chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display all the messages stored in the session state
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 4. Main Interaction Logic ---
# Only proceed if the application was initialized successfully.
if app:
    # Use st.chat_input to get user input at the bottom of the screen.
    if prompt := st.chat_input("What are you looking for?"):
        
        # Add the user's message to the chat history and display it.
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Display the assistant's response.
        with st.chat_message("assistant"):
            # Show a "thinking" spinner while processing the request.
            with st.spinner("Thinking..."):
                # Call the specific orchestration method designed for Streamlit.
                # This method handles query generation, execution, and result polishing.
                response = app.process_user_request_for_streamlit(prompt) #
                st.markdown(response)

        # Add the assistant's response to the chat history.
        st.session_state.messages.append({"role": "assistant", "content": response})
else:
    st.warning("Application is not available due to an initialization error.")