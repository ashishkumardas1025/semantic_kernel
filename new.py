import json
import boto3
from botocore.exceptions import ClientError
import urllib3
from typing import Dict, Any, Optional, List
import warnings
import os
import pandas as pd
import chromadb
from chromadb.config import Settings
import uuid
from pathlib import Path
import numpy as np
from datetime import datetime

# Configure warnings and disable insecure request warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Unverified HTTPS request")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Model configuration
CLAUDE_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"
TITAN_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
SAMPLE_ESTIMATIONS_DIR = "Sample Estimations"
CHROMA_DB_PATH = "./chroma_db"

# Global clients - initialized once
_bedrock_client = None
_chroma_client = None
_collection = None

def initialize_bedrock_client():
    """Initialize and return AWS Bedrock client with credentials from environment variables"""
    global _bedrock_client
    if _bedrock_client is None:
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_session_token = os.getenv("AWS_SESSION_TOKEN")

        session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token
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
        
    except ClientError as e:
        print(f"AWS Error generating embedding: {e}")
        raise
    except Exception as e:
        print(f"General Error generating embedding: {e}")
        raise

def invoke_claude(prompt: str, system: Optional[str] = None, max_tokens: int = 512, temperature: float = 0.1) -> str:
    """Invoke Claude model through AWS Bedrock"""
    bedrock_client = initialize_bedrock_client()
    
    request_payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {
                "role": "user",
                "content": [{"text": prompt}]
            }
        ]
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
    except ClientError as e:
        print(f"AWS Error invoking Claude: {e}")
        raise
    except Exception as e:
        print(f"General Error invoking Claude: {e}")
        raise

def find_header_row(df_raw: pd.DataFrame) -> tuple:
    """Find the header row containing required columns and return row index and column mapping"""
    column_variations = {
        "Capability": [
            "capability", "capabilities", "cap", "function", "feature",
            "business capability", "system capability", "functional area"
        ],
        "Scope / Business Description": [
            "scope", "business description", "description", "scope/business description",
            "scope / business description", "business scope", "scope description",
            "business desc", "scope/desc", "scope desc", "business detail",
            "scope/business desc", "scope & business description"
        ],
        "System Changes": [
            "system changes", "system change", "changes", "technical changes",
            "system modifications", "system updates", "technical details",
            "implementation", "tech changes", "system impacts", "modifications",
            "technical implementation", "system requirements"
        ]
    }
    
    # Search through first 10 rows to find header
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

def validate_excel_file(file_path: Path) -> dict:
    """Validate an Excel file and return detailed information"""
    validation_result = {
        "file_name": file_path.name,
        "file_path": str(file_path),
        "is_valid": False,
        "sheets": [],
        "errors": [],
        "warnings": [],
        "header_row": None,
        "column_mapping": None,
        "data_rows": 0
    }
    
    try:
        if not file_path.exists():
            validation_result["errors"].append("File does not exist")
            return validation_result
        
        xl_file = pd.ExcelFile(file_path)
        validation_result["sheets"] = xl_file.sheet_names
        
        if "Capability List" not in xl_file.sheet_names:
            validation_result["errors"].append("'Capability List' sheet not found")
            return validation_result
        
        df_raw = pd.read_excel(file_path, sheet_name="Capability List", header=None)
        header_row_idx, column_mapping = find_header_row(df_raw)
        
        if header_row_idx is None:
            validation_result["errors"].append("Could not find required columns")
            return validation_result
        
        validation_result["header_row"] = header_row_idx
        validation_result["column_mapping"] = column_mapping
        
        df = pd.read_excel(file_path, sheet_name="Capability List", header=header_row_idx)
        
        if column_mapping:
            df = df.rename(columns=column_mapping)
        
        df_clean = df.dropna(subset=["Capability"])
        df_clean = df_clean[df_clean["Capability"].astype(str).str.strip().astype(bool)]
        validation_result["data_rows"] = len(df_clean)
        
        if validation_result["data_rows"] == 0:
            validation_result["warnings"].append("No valid data rows found")
        
        validation_result["is_valid"] = True
        
    except Exception as e:
        validation_result["errors"].append(f"Error reading file: {str(e)}")
    
    return validation_result

def process_excel_file(excel_file_path: Path) -> int:
    """Process a single Excel file and extract capability data"""
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
        
        required_columns = ["Capability", "Scope / Business Description", "System Changes"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            print(f"Missing columns in {excel_file_path.name}: {missing_columns}")
            return 0
        
        df = df.dropna(subset=["Capability"])
        df = df[df["Capability"].str.strip().astype(bool)]
        
        print(f"Found {len(df)} valid capability rows in {excel_file_path.name}")
        
        for index, row in df.iterrows():
            if create_and_store_chunk(row, excel_file_path, index + header_row_idx + 1, collection):
                chunks_added += 1
                
        return chunks_added
        
    except Exception as e:
        print(f"Error reading Excel file {excel_file_path.name}: {e}")
        return 0

def create_and_store_chunk(row, file_path: Path, row_index: int, collection) -> bool:
    """Create a text chunk from a row and store it in ChromaDB"""
    try:
        capability = str(row.get("Capability", "")).strip()
        scope_description = str(row.get("Scope / Business Description", "")).strip()
        system_changes = str(row.get("System Changes", "")).strip()
        
        if not capability or capability.lower() == 'nan':
            return False
        
        # Create comprehensive text for embedding with enhanced search context
        chunk_text = f"Capability: {capability}\n"
        if scope_description and scope_description.lower() != 'nan':
            chunk_text += f"Business Description: {scope_description}\n"
        if system_changes and system_changes.lower() != 'nan':
            chunk_text += f"System Changes: {system_changes}\n"
        
        # Add searchable keywords for better retrieval
        chunk_text += f"Keywords: {capability.lower()}"
        if scope_description and scope_description.lower() != 'nan':
            chunk_text += f" {scope_description.lower()}"
        if system_changes and system_changes.lower() != 'nan':
            chunk_text += f" {system_changes.lower()}"
        
        embedding = generate_embedding(chunk_text)
        chunk_id = str(uuid.uuid4())
        
        metadata = {
            "file_name": file_path.name,
            "file_path": str(file_path),
            "sheet_name": "Capability List",
            "row_index": row_index,
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
        print(f"Error creating chunk for row {row_index}: {e}")
        return False

def index_all_excel_files():
    """Scan Sample Estimations directory and index all Excel files"""
    print(f"Scanning directory: {SAMPLE_ESTIMATIONS_DIR}")
    
    if not os.path.exists(SAMPLE_ESTIMATIONS_DIR):
        print(f"Directory {SAMPLE_ESTIMATIONS_DIR} does not exist!")
        return
    
    excel_files = list(Path(SAMPLE_ESTIMATIONS_DIR).glob("*.xlsx"))
    print(f"Found {len(excel_files)} Excel files to process")
    
    successful_files = 0
    failed_files = 0
    total_chunks = 0
    
    for excel_file in excel_files:
        try:
            print(f"\n--- Processing file: {excel_file.name} ---")
            chunks_added = process_excel_file(excel_file)
            
            if chunks_added > 0:
                total_chunks += chunks_added
                print(f"✓ Successfully processed {excel_file.name} ({chunks_added} chunks)")
                successful_files += 1
            else:
                print(f"✗ No valid data found in {excel_file.name}")
                failed_files += 1
                
        except Exception as e:
            print(f"✗ Error processing {excel_file.name}: {e}")
            failed_files += 1
            continue
    
    print(f"\n--- Indexing Summary ---")
    print(f"Total files processed: {successful_files + failed_files}")
    print(f"Successful: {successful_files}")
    print(f"Failed: {failed_files}")
    print(f"Total chunks indexed: {total_chunks}")

def query_similar_capabilities(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Query ChromaDB for similar capabilities based on capability, business description, or system changes"""
    _, collection = initialize_chroma_client()
    
    try:
        # Enhance query with context for better retrieval
        enhanced_query = f"Query: {query}\nLooking for: capability business description system changes"
        query_embedding = generate_embedding(enhanced_query)
        
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

def generate_comprehensive_overview(query: str, capability_matches: List[Dict[str, Any]]) -> str:
    """Generate a comprehensive 200-word overview of matched capabilities"""
    if not capability_matches:
        return "No matching capabilities found for the given query."
    
    # Prepare data for Claude
    matches_text = ""
    for i, match in enumerate(capability_matches[:3], 1):  # Top 3 matches
        metadata = match["metadata"]
        similarity = match["similarity_score"]
        
        matches_text += f"""
        Match {i} (Similarity: {similarity:.2f}):
        - Capability: {metadata.get('capability', 'N/A')}
        - Business Description: {metadata.get('scope_description', 'N/A')}
        - System Changes: {metadata.get('system_changes', 'N/A')}
        - Source: {metadata.get('file_name', 'N/A')}
        """
    
    prompt = f"""
    Based on the user query "{query}" and the following capability matches, provide a comprehensive 200-word overview that covers:

    1. Summary of the possible capability matches found
    2. Key systems that would be impacted
    3. Overview of system changes required
    4. Business description and value proposition
    5. How these capabilities relate to the user's query

    Capability Matches:
    {matches_text}

    Please provide a cohesive, informative overview that helps the user understand the scope and impact of these capabilities. Focus on practical insights and business value.
    """
    
    system_prompt = """You are a business analyst providing capability analysis. Create clear, concise overviews that highlight:
    - Business value and impact
    - Technical implementation scope
    - System dependencies and changes
    - Relationship to user requirements
    Keep the response exactly around 200 words and make it actionable."""
    
    try:
        overview = invoke_claude(prompt, system=system_prompt, max_tokens=300)
        return overview.strip()
    except Exception as e:
        print(f"Error generating overview: {e}")
        return f"Overview generation failed. Found {len(capability_matches)} matching capabilities for '{query}'."

def search_capabilities(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Main search function that handles queries about capabilities, business descriptions, or system changes"""
    try:
        print(f"Searching for: '{query}'")
        
        # Query similar capabilities
        similar_capabilities = query_similar_capabilities(query, top_k=max_results)
        
        if not similar_capabilities:
            return {
                "query": query,
                "overview": "No matching capabilities found for the given query.",
                "results": [],
                "total_found": 0,
                "search_timestamp": datetime.now().isoformat()
            }
        
        # Generate comprehensive overview
        overview = generate_comprehensive_overview(query, similar_capabilities)
        
        # Format individual results
        results = []
        for capability_data in similar_capabilities:
            metadata = capability_data["metadata"]
            
            # Create detailed source information
            source_info = {
                "file_name": metadata['file_name'],
                "file_path": metadata['file_path'],
                "sheet_name": metadata['sheet_name'],
                "row_index": metadata['row_index']
            }
            
            results.append({
                "capability": metadata.get('capability', 'N/A'),
                "business_description": metadata.get('scope_description', 'N/A'),
                "system_changes": metadata.get('system_changes', 'N/A'),
                "similarity_score": capability_data["similarity_score"],
                "source": source_info,
                "source_link": f"file://{metadata['file_path']}#sheet={metadata['sheet_name']}&row={metadata['row_index']}"
            })
        
        return {
            "query": query,
            "overview": overview,
            "results": results,
            "total_found": len(similar_capabilities),
            "search_timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Error searching capabilities: {e}")
        return {
            "query": query,
            "overview": f"Search failed: {str(e)}",
            "results": [],
            "error": str(e),
            "search_timestamp": datetime.now().isoformat()
        }

def get_collection_stats() -> Dict[str, Any]:
    """Get statistics about the indexed data"""
    try:
        _, collection = initialize_chroma_client()
        count = collection.count()
        
        if count == 0:
            return {
                "total_chunks": 0,
                "collection_name": "capability_chunks",
                "database_path": CHROMA_DB_PATH,
                "has_data": False,
                "message": "No data indexed yet. Run index_all_excel_files() first."
            }
        
        # Get sample data for analysis
        sample_data = collection.get(limit=min(10, count), include=["metadatas"])
        
        files_indexed = set()
        if sample_data and sample_data.get("metadatas"):
            for metadata in sample_data["metadatas"]:
                if metadata.get("file_name"):
                    files_indexed.add(metadata["file_name"])
        
        return {
            "total_chunks": count,
            "collection_name": "capability_chunks",
            "database_path": CHROMA_DB_PATH,
            "files_indexed": len(files_indexed),
            "sample_files": list(files_indexed),
            "has_data": count > 0
        }
    except Exception as e:
        return {"error": str(e)}

def validate_all_excel_files() -> List[Dict[str, Any]]:
    """Validate all Excel files in the Sample Estimations directory"""
    if not os.path.exists(SAMPLE_ESTIMATIONS_DIR):
        return [{"error": f"Directory {SAMPLE_ESTIMATIONS_DIR} does not exist"}]
    
    excel_files = list(Path(SAMPLE_ESTIMATIONS_DIR).glob("*.xlsx"))
    validation_results = []
    
    for excel_file in excel_files:
        result = validate_excel_file(excel_file)
        validation_results.append(result)
    
    return validation_results

def get_indexed_files_info() -> List[Dict[str, Any]]:
    """Get information about all indexed files"""
    try:
        _, collection = initialize_chroma_client()
        all_data = collection.get(include=["metadatas"])
        
        if not all_data or not all_data.get("metadatas"):
            return []
        
        files_info = {}
        for metadata in all_data["metadatas"]:
            file_name = metadata.get("file_name", "Unknown")
            
            if file_name not in files_info:
                files_info[file_name] = {
                    "file_name": file_name,
                    "file_path": metadata.get("file_path", ""),
                    "chunk_count": 0,
                    "capabilities": [],
                    "indexed_at": metadata.get("indexed_at", "")
                }
            
            files_info[file_name]["chunk_count"] += 1
            
            capability = metadata.get("capability", "")
            if capability and capability not in files_info[file_name]["capabilities"]:
                files_info[file_name]["capabilities"].append(capability)
        
        return list(files_info.values())
        
    except Exception as e:
        return [{"error": str(e)}]

# Command-line interface functions
def search_capability_command(query: str):
    """Command-line interface for searching capabilities"""
    results = search_capabilities(query)
    
    print(f"\n{'='*60}")
    print(f"CAPABILITY SEARCH RESULTS")
    print(f"{'='*60}")
    print(f"Query: '{query}'")
    print(f"Found: {results['total_found']} matches")
    print(f"Timestamp: {results['search_timestamp']}")
    
    if results.get("error"):
        print(f"\nError: {results['error']}")
        return
    
    # Display overview
    print(f"\n{'='*60}")
    print("OVERVIEW")
    print(f"{'='*60}")
    print(results['overview'])
    
    # Display individual results
    if results["results"]:
        print(f"\n{'='*60}")
        print("DETAILED MATCHES")
        print(f"{'='*60}")
        
        for i, result in enumerate(results["results"], 1):
            print(f"\n[{i}] {result['capability']}")
            print(f"    Similarity: {result['similarity_score']:.3f}")
            print(f"    File: {result['source']['file_name']}")
            print(f"    Business Description: {result['business_description']}")
            print(f"    System Changes: {result['system_changes']}")
            print(f"    Source: {result['source_link']}")
    else:
        print("\nNo specific matches found.")

def validate_files_command():
    """Command-line interface for validating Excel files"""
    validation_results = validate_all_excel_files()
    
    print(f"\n{'='*60}")
    print("EXCEL FILES VALIDATION REPORT")
    print(f"{'='*60}")
    
    valid_count = 0
    invalid_count = 0
    
    for result in validation_results:
        if result.get('error'):
            print(f"\nError: {result['error']}")
            continue
            
        status = "✓ VALID" if result['is_valid'] else "✗ INVALID"
        if result['is_valid']:
            valid_count += 1
        else:
            invalid_count += 1
            
        print(f"\nFile: {result['file_name']}")
        print(f"Status: {status}")
        
        if result.get('data_rows') is not None:
            print(f"Data Rows: {result['data_rows']}")
        
        if result.get('errors'):
            for error in result['errors']:
                print(f"  ✗ {error}")
        
        if result.get('warnings'):
            for warning in result['warnings']:
                print(f"  ⚠ {warning}")
    
    print(f"\n{'='*60}")
    print(f"Summary: {valid_count} valid, {invalid_count} invalid files")

def show_indexed_files_command():
    """Command-line interface for showing indexed files"""
    files_info = get_indexed_files_info()
    
    print(f"\n{'='*60}")
    print("INDEXED FILES INFORMATION")
    print(f"{'='*60}")
    
    if not files_info:
        print("No files have been indexed yet.")
        print("Run: python script.py index")
        return
    
    total_chunks = 0
    for file_info in files_info:
        if file_info.get('error'):
            print(f"Error: {file_info['error']}")
            continue
            
        total_chunks += file_info['chunk_count']
        print(f"\nFile: {file_info['file_name']}")
        print(f"Chunks: {file_info['chunk_count']}")
        print(f"Capabilities: {len(file_info['capabilities'])}")
        print(f"Indexed: {file_info['indexed_at']}")
        
        if file_info['capabilities']:
            print("Sample Capabilities:")
            for cap in file_info['capabilities'][:2]:
                print(f"  - {cap}")
            if len(file_info['capabilities']) > 2:
                print(f"  ... and {len(file_info['capabilities']) - 2} more")
    
    print(f"\n{'='*60}")
    print(f"Total: {len(files_info)} files, {total_chunks} chunks")

def main():
    """Main function to demonstrate the capability lookup system"""
    print("Initializing Capability Lookup System...")
    
    # Check current stats
    stats = get_collection_stats()
    print(f"Current database stats: {stats}")
    
    # Index files if needed
    if stats.get("total_chunks", 0) == 0:
        print("No indexed data found. Starting indexing process...")
        index_all_excel_files()
        stats = get_collection_stats()
        print(f"Updated stats: {stats}")
    
    # Test sample queries
    sample_queries = [
        "mutual funds product selection",
        "customer onboarding process",
        "consent management system",
        "entitlement management"
    ]
    
    print("\n" + "="*60)
    print("TESTING SAMPLE QUERIES")
    print("="*60)
    
    for query in sample_queries:
        print(f"\nQuery: '{query}'")
        results = search_capabilities(query, max_results=2)
        print(f"Found {results['total_found']} matches")
        if results['results']:
            print(f"Top match: {results['results'][0]['capability']}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "index":
            print("Starting indexing process...")
            index_all_excel_files()
        elif command == "validate":
            validate_files_command()
        elif command == "files":
            show_indexed_files_command()
        elif command == "stats":
            stats = get_collection_stats()
            print(json.dumps(stats, indent=2))
        elif command == "search":
            if len(sys.argv) > 2:
                query = " ".join(sys.argv[2:])
                search_capability_command(query)
            else:
                print("Please provide a search query: python script.py search 'your query'")
        else:
            # Treat as search query
            query = " ".join(sys.argv[1:])
            search_capability_command(query)
    else:
        # Run main demo
        main()
