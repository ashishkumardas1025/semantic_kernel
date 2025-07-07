import streamlit as st
import json
import pandas as pd
from datetime import datetime
import os
from pathlib import Path

# Import the main capability lookup system
# Assuming the previous code is saved as capability_lookup_system.py
try:
    from capability_lookup_system import CapabilityLookupSystem
except ImportError:
    st.error("Please ensure capability_lookup_system.py is in the same directory")
    st.stop()

# Configure Streamlit page
st.set_page_config(
    page_title="Capability Lookup System",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'lookup_system' not in st.session_state:
    st.session_state.lookup_system = None
if 'search_results' not in st.session_state:
    st.session_state.search_results = None

def initialize_system():
    """Initialize the capability lookup system"""
    try:
        with st.spinner("Initializing system..."):
            st.session_state.lookup_system = CapabilityLookupSystem()
        st.success("System initialized successfully!")
        return True
    except Exception as e:
        st.error(f"Error initializing system: {e}")
        return False

def main():
    """Main Streamlit application"""
    
    # Header
    st.title("🔍 Capability Lookup System")
    st.markdown("Search for similar business capabilities and system changes from historical data")
    
    # Sidebar
    st.sidebar.title("System Controls")
    
    # Initialize system button
    if st.sidebar.button("Initialize System", type="primary"):
        initialize_system()
    
    # Check if system is initialized
    if st.session_state.lookup_system is None:
        st.warning("Please initialize the system first using the sidebar button.")
        st.info("Make sure your AWS credentials are configured and Excel files are in the 'Sample Estimations' directory.")
        return
    
    lookup_system = st.session_state.lookup_system
    
    # System Statistics
    st.sidebar.subheader("System Statistics")
    with st.sidebar:
        if st.button("Refresh Stats"):
            stats = lookup_system.get_collection_stats()
            st.json(stats)
    
    # Indexing Section
    st.sidebar.subheader("Data Management")
    
    if st.sidebar.button("Index Excel Files"):
        with st.spinner("Indexing files..."):
            try:
                lookup_system.scan_and_index_excel_files()
                st.sidebar.success("Indexing completed!")
            except Exception as e:
                st.sidebar.error(f"Indexing failed: {e}")
    
    # Main Search Interface
    st.header("Search Capabilities")
    
    # Search form
    with st.form("search_form"):
        col1, col2 = st.columns([3, 1])
        
        with col1:
            query = st.text_input(
                "Enter your search query:",
                placeholder="e.g., 'review current consent', 'mutual funds selection', 'onboarding process'"
            )
        
        with col2:
            max_results = st.number_input("Max Results", min_value=1, max_value=10, value=3)
        
        search_button = st.form_submit_button("Search", type="primary")
    
    # Process search
    if search_button and query:
        with st.spinner("Searching for similar capabilities..."):
            try:
                results = lookup_system.search_capabilities(query, max_results=max_results)
                st.session_state.search_results = results
            except Exception as e:
                st.error(f"Search failed: {e}")
                st.session_state.search_results = None
    
    # Display Results
    if st.session_state.search_results:
        results = st.session_state.search_results
        
        st.header("Search Results")
        
        # Display query info
        st.info(f"Query: **{results['query']}** | Found: **{results['total_found']}** results")
        
        if results.get('error'):
            st.error(f"Error: {results['error']}")
        elif not results['results']:
            st.warning("No similar capabilities found.")
        else:
            # Display results
            for i, result in enumerate(results['results'], 1):
                with st.expander(f"Result {i}: {result['capability']}", expanded=True):
                    
                    # Create columns for better layout
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.subheader("Summary")
                        st.write(result['summary'])
                        
                        st.subheader("Capability")
                        st.write(result['capability'])
                    
                    with col2:
                        st.subheader("Details")
                        st.write(f"**File:** {result['fileName']}")
                        st.write(f"**Similarity:** {1 - result['distance']:.3f}")
                        
                        # Source link (simplified display)
                        if st.button(f"View Source {i}", key=f"source_{i}"):
                            st.code(result['sourceLink'])
            
            # Export results
            st.header("Export Results")
            
            # Convert to DataFrame for export
            export_data = []
            for result in results['results']:
                export_data.append({
                    'Capability': result['capability'],
                    'Summary': result['summary'],
                    'File Name': result['fileName'],
                    'Similarity Score': f"{1 - result['distance']:.3f}",
                    'Source Link': result['sourceLink']
                })
            
            df = pd.DataFrame(export_data)
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Download as CSV
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download as CSV",
                    data=csv,
                    file_name=f"capability_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            with col2:
                # Download as JSON
                json_data = json.dumps(results, indent=2)
                st.download_button(
                    label="Download as JSON",
                    data=json_data,
                    file_name=f"capability_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
    
    # Sample Queries Section
    st.header("Sample Queries")
    st.markdown("Try these example queries to get started:")
    
    sample_queries = [
        "review current consent",
        "mutual funds product selection",
        "onboarding process enhancement",
        "customer entitlement management",
        "data sharing compliance",
        "account setup automation"
    ]
    
    cols = st.columns(3)
    for i, sample_query in enumerate(sample_queries):
        with cols[i % 3]:
            if st.button(sample_query, key=f"sample_{i}"):
                st.session_state.sample_query = sample_query
                st.experimental_rerun()
    
    # If a sample query was clicked, populate the search box
    if hasattr(st.session_state, 'sample_query'):
        st.info(f"Selected query: {st.session_state.sample_query}")
        delattr(st.session_state, 'sample_query')
    
    # Configuration Section
    st.header("Configuration")
    
    with st.expander("System Configuration"):
        st.subheader("Directory Structure")
        
        # Check directories
        directories = ["Sample Estimations", "chroma_db"]
        for directory in directories:
            if os.path.exists(directory):
                st.success(f"✓ {directory} exists")
                if directory == "Sample Estimations":
                    excel_files = list(Path(directory).glob("*.xlsx"))
                    st.write(f"  - Found {len(excel_files)} Excel files")
                    for file in excel_files:
                        st.write(f"    - {file.name}")
            else:
                st.error(f"✗ {directory} missing")
        
        st.subheader("Environment Variables")
        env_vars = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]
        for var in env_vars:
            if os.getenv(var):
                st.success(f"✓ {var} is set")
            else:
                st.error(f"✗ {var} is missing")
    
    # Advanced Functions Section
    st.header("Advanced Functions")
    
    with st.expander("Advanced Operations"):
        
        # Direct embedding generation
        st.subheader("Generate Embedding")
        embed_text = st.text_area("Text to embed:", placeholder="Enter text to generate embedding...")
        
        if st.button("Generate Embedding") and embed_text:
            try:
                with st.spinner("Generating embedding..."):
                    embedding = lookup_system.generate_embedding(embed_text)
                st.success(f"Generated embedding with {len(embedding)} dimensions")
                st.json({"embedding_length": len(embedding), "first_5_values": embedding[:5]})
            except Exception as e:
                st.error(f"Error generating embedding: {e}")
        
        # Direct Claude invocation
        st.subheader("Direct Claude Query")
        claude_prompt = st.text_area("Prompt for Claude:", placeholder="Enter prompt for Claude...")
        
        if st.button("Query Claude") and claude_prompt:
            try:
                with st.spinner("Querying Claude..."):
                    response = lookup_system.invoke_claude(claude_prompt)
                st.success("Claude Response:")
                st.write(response)
            except Exception as e:
                st.error(f"Error querying Claude: {e}")
    
    # Footer
    st.markdown("---")
    st.markdown("Built with Streamlit | Powered by AWS Bedrock and ChromaDB")

if __name__ == "__main__":
    main()
