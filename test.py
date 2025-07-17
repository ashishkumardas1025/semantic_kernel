import json
import boto3
from botocore.exceptions import ClientError
import urllib3
from typing import Dict, Any, Optional, List
import warnings
import os
import pandas as pd
import chromadb
import uuid
from pathlib import Path
from datetime import datetime

# Configure warnings and disable insecure request warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Unverified HTTPS request")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Model configuration
CLAUDE_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"
TITAN_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
SAMPLE_ESTIMATIONS_DIR = "Sample Estimations"
CHROMA_DB_PATH = "./chroma_db"

# Global clients
_bedrock_client = None
_chroma_client = None
_collection = None

def initialize_bedrock_client():
    """Initialize AWS Bedrock client"""
    global _bedrock_client
    if _bedrock_client is None:
        session = boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN")
        )
        _bedrock_client = session.client(
            service_name='bedrock-runtime', 
            region_name='us-east-1', 
            verify=False
        )
    return _bedrock_client

def initialize_chroma_client():
    """Initialize ChromaDB client and collection"""
    global _chroma_client, _collection
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        try:
            _collection = _chroma_client.get_collection(name="capability_chunks")
        except:
            _collection = _chroma_client.create_collection(name="capability_chunks")
    return _chroma_client, _collection

def generate_embedding(text: str) -> List[float]:
    """Generate embedding using Amazon Titan Embed model"""
    bedrock_client = initialize_bedrock_client()
    
    try:
        request_payload = {
            "inputText": text,
            "dimensions": 1024,
            "normalize": True
        }
        
        response = bedrock_client.invoke_model(
            modelId=TITAN_EMBED_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_payload).encode("utf-8")
        )
        
        response_body = json.loads(response["body"].read().decode("utf-8"))
        return response_body["embedding"]
        
    except Exception as e:
        print(f"Error generating embedding: {e}")
        raise

def invoke_claude(prompt: str, system: Optional[str] = None, max_tokens: int = 250) -> str:
    """Invoke Claude model through AWS Bedrock"""
    bedrock_client = initialize_bedrock_client()
    
    request_payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": [{"text": prompt}]}]
    }
    
    if system:
        request_payload["system"] = system
        
    try:
        response = bedrock_client.invoke_model(
            modelId=CLAUDE_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_payload).encode("utf-8")
        )
        response_body = json.loads(response["body"].read().decode("utf-8"))
        return response_body["content"][0]["text"]
    except Exception as e:
        print(f"Error invoking Claude: {e}")
        raise

def find_header_row(df_raw: pd.DataFrame) -> tuple:
    """Find the header row containing required columns"""
    column_variations = {
        "Capability": ["capability", "capabilities", "cap", "function", "feature", "business capability"],
        "Scope / Business Description": ["scope", "business description", "description", "scope/business description", "scope / business description"],
        "System Changes": ["system changes", "system change", "changes", "technical changes", "system modifications"]
    }
    
    for row_idx in range(min(10, len(df_raw))):
        row = df_raw.iloc[row_idx]
        row_str = row.astype(str).str.lower().str.strip()
        
        found_columns = {}
        for standard_name, variations in column_variations.items():
            for col_idx, cell_value in enumerate(row_str):
                if pd.isna(cell_value) or cell_value == 'nan':
                    continue
                if cell_value in variations or any(var in cell_value for var in variations):
                    found_columns[standard_name] = df_raw.columns[col_idx]
                    break
        
        if len(found_columns) == 3:
            column_mapping = {v: k for k, v in found_columns.items()}
            return row_idx, column_mapping
    
    return None, None

def process_excel_file(excel_file_path: Path) -> int:
    """Process Excel file and extract capability data"""
    _, collection = initialize_chroma_client()
    chunks_added = 0
    
    try:
        df_raw = pd.read_excel(excel_file_path, sheet_name="Capability List", header=None)
        header_row_idx, column_mapping = find_header_row(df_raw)
        
        if header_row_idx is None:
            print(f"Could not find required columns in {excel_file_path.name}")
            return 0
        
        df = pd.read_excel(excel_file_path, sheet_name="Capability List", header=header_row_idx)
        df.columns = df.columns.str.strip()
        
        if column_mapping:
            df = df.rename(columns=column_mapping)
        
        df = df.dropna(subset=["Capability"])
        df = df[df["Capability"].str.strip().astype(bool)]
        
        for index, row in df.iterrows():
            if create_and_store_chunk(row, excel_file_path, index + header_row_idx + 1, collection):
                chunks_added += 1
                
        return chunks_added
        
    except Exception as e:
        print(f"Error processing {excel_file_path.name}: {e}")
        return 0

def create_and_store_chunk(row, file_path: Path, row_index: int, collection) -> bool:
    """Create and store chunk in ChromaDB"""
    try:
        capability = str(row.get("Capability", "")).strip()
        scope_description = str(row.get("Scope / Business Description", "")).strip()
        system_changes = str(row.get("System Changes", "")).strip()
        
        if not capability or capability.lower() == 'nan':
            return False
        
        chunk_text = f"Capability: {capability}\n"
        if scope_description and scope_description.lower() != 'nan':
            chunk_text += f"Business Description: {scope_description}\n"
        if system_changes and system_changes.lower() != 'nan':
            chunk_text += f"System Changes: {system_changes}\n"
        
        embedding = generate_embedding(chunk_text)
        chunk_id = str(uuid.uuid4())
        
        metadata = {
            "file_name": file_path.name,
            "file_path": str(file_path),
            "capability": capability,
            "scope_description": scope_description,
            "system_changes": system_changes,
            "indexed_at": datetime.now().isoformat()
        }
        
        collection.add(
            embeddings=[embedding],
            documents=[chunk_text],
            metadatas=[metadata],
            ids=[chunk_id]
        )
        
        return True
        
    except Exception as e:
        print(f"Error creating chunk: {e}")
        return False

def index_all_excel_files():
    """Index all Excel files in directory"""
    print(f"Scanning directory: {SAMPLE_ESTIMATIONS_DIR}")
    
    if not os.path.exists(SAMPLE_ESTIMATIONS_DIR):
        print(f"Directory {SAMPLE_ESTIMATIONS_DIR} does not exist!")
        return
    
    excel_files = list(Path(SAMPLE_ESTIMATIONS_DIR).glob("*.xlsx"))
    print(f"Found {len(excel_files)} Excel files to process")
    
    total_chunks = 0
    for excel_file in excel_files:
        chunks_added = process_excel_file(excel_file)
        if chunks_added > 0:
            total_chunks += chunks_added
            print(f"✓ Processed {excel_file.name} ({chunks_added} chunks)")
        else:
            print(f"✗ No valid data in {excel_file.name}")
    
    print(f"Total chunks indexed: {total_chunks}")

def query_similar_capabilities(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Query ChromaDB for similar capabilities"""
    _, collection = initialize_chroma_client()
    
    try:
        query_embedding = generate_embedding(query)
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        formatted_results = []
        for i in range(len(results["documents"][0])):
            formatted_results.append({
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
                "similarity_score": 1 - results["distances"][0][i]
            })
        
        return formatted_results
        
    except Exception as e:
        print(f"Error querying capabilities: {e}")
        return []

def generate_response_with_links(query: str, matches: List[Dict[str, Any]]) -> str:
    """Generate response using Claude based on matched capabilities"""
    if not matches:
        return "No matching capabilities found for the given query."
    
    # Prepare match data for the prompt
    match_data = []
    for match in matches[:3]:  # Top 3 matches
        metadata = match["metadata"]
        match_info = {
            "capability": metadata.get('capability', 'N/A'),
            "business_description": metadata.get('scope_description', 'N/A'),
            "system_changes": metadata.get('system_changes', 'N/A'),
            "file_name": metadata.get('file_name', 'N/A'),
            "similarity": f"{match['similarity_score']:.2f}"
        }
        match_data.append(match_info)
    
    # Create source links
    source_links = []
    for i, match in enumerate(matches[:5], 1):
        metadata = match["metadata"]
        source_links.append(f"{i}. {metadata.get('file_name', 'Unknown File')}")
    
    system_prompt = """You are a business analyst providing capability analysis. 
    Provide a comprehensive summary (under 200 words) covering:
    - Overview of matching capabilities
    - Key systems and changes involved
    - Business impact and value
    Then mention source files with similar capabilities for further reference."""
    
    user_prompt = f"""
    Query: "{query}"
    
    Matching capabilities found:
    {chr(10).join([f"- {match['capability']}: {match['business_description']}" for match in match_data])}
    
    Provide an overview summary and mention these source files contain similar capabilities:
    {chr(10).join(source_links)}
    """
    
    try:
        response = invoke_claude(user_prompt, system=system_prompt, max_tokens=300)
        return response.strip()
    except Exception as e:
        print(f"Error generating response: {e}")
        return f"Analysis failed. Found {len(matches)} matching capabilities for '{query}'."

def search_capabilities(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Main search function"""
    try:
        print(f"Searching for: '{query}'")
        
        # Find similar capabilities
        similar_capabilities = query_similar_capabilities(query, top_k=max_results)
        
        if not similar_capabilities:
            return {
                "query": query,
                "response": "No matching capabilities found for the given query.",
                "source_files": [],
                "total_found": 0
            }
        
        # Generate response with source links
        response = generate_response_with_links(query, similar_capabilities)
        
        # Extract source file information
        source_files = []
        for match in similar_capabilities:
            metadata = match["metadata"]
            source_files.append({
                "file_name": metadata.get('file_name', 'Unknown'),
                "capability": metadata.get('capability', 'N/A'),
                "similarity": f"{match['similarity_score']:.2f}"
            })
        
        return {
            "query": query,
            "response": response,
            "source_files": source_files,
            "total_found": len(similar_capabilities),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Error in search: {e}")
        return {
            "query": query,
            "response": f"Search failed: {str(e)}",
            "source_files": [],
            "error": str(e)
        }

def search_command(query: str):
    """Command-line interface for searching capabilities"""
    results = search_capabilities(query)
    
    print(f"\n{'='*60}")
    print(f"CAPABILITY SEARCH RESULTS")
    print(f"{'='*60}")
    print(f"Query: '{query}'")
    print(f"Found: {results.get('total_found', 0)} matches")
    
    if results.get("error"):
        print(f"\nError: {results['error']}")
        return
    
    print(f"\n{'='*60}")
    print("RESPONSE")
    print(f"{'='*60}")
    print(results.get('response', 'No response generated'))
    
    if results.get("source_files"):
        print(f"\n{'='*60}")
        print("SOURCE FILES")
        print(f"{'='*60}")
        for i, source in enumerate(results["source_files"], 1):
            print(f"{i}. {source['file_name']} (Similarity: {source['similarity']})")
            print(f"   Capability: {source['capability']}")

def main():
    """Main function"""
    print("Capability Lookup System")
    
    # Check if data is indexed
    _, collection = initialize_chroma_client()
    count = collection.count()
    
    if count == 0:
        print("No data found. Run indexing first: python script.py index")
        return
    
    print(f"Database contains {count} capability chunks")
    
    # Test queries
    test_queries = [
        "customer onboarding intake process",
        "mutual funds capability",
        "consent management business process"
    ]
    
    for query in test_queries:
        print(f"\nTesting: '{query}'")
        result = search_capabilities(query)
        print(f"Found: {result.get('total_found')}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "index":
            index_all_excel_files()
        elif command == "search":
            if len(sys.argv) > 2:
                query = " ".join(sys.argv[2:])
                search_command(query)
            else:
                print("Usage: python script.py search 'your query'")
        else:
            # Treat as search query
            query = " ".join(sys.argv[1:])
            search_command(query)
    else:
        main()
