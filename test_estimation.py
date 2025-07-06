import json
import boto3
from botocore.exceptions import ClientError
import urllib3
from typing import Dict, Any, Optional, Union, List, Tuple
import warnings
import os
import pandas as pd
import numpy as np
from pathlib import Path
import chromadb
from chromadb.config import Settings
import hashlib
import re
from dataclasses import dataclass
from collections import defaultdict

# Configure warnings and disable insecure request warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Unverified HTTPS request")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Model configuration
CLAUDE_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"

@dataclass
class CapabilityDocument:
    """Data class to store capability information"""
    capability: str
    scope_description: str
    file_name: str
    file_path: str
    sheet_name: str
    system_changes: str = ""
    system_leads: str = ""
    additional_info: str = ""
    # Project T-Shirt specific fields
    cost_estimation: str = ""
    team_responsible: str = ""
    estimation_contact: str = ""
    accountable_sto: str = ""
    accountable_lto: str = ""
    intake_bc: str = ""
    intake_sa: str = ""
    cost_breakdown: Dict[str, str] = None
    
    def __post_init__(self):
        if self.cost_breakdown is None:
            self.cost_breakdown = {}

class AWSBedrockClient:
    """AWS Bedrock client for LLM and embedding operations"""
    
    def __init__(self):
        self.bedrock_client = self._initialize_bedrock_client()
    
    def _initialize_bedrock_client(self):
        """Initialize and return AWS Bedrock client with credentials from environment variables"""
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_session_token = os.getenv("AWS_SESSION_TOKEN")

        session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token
        )

        bedrock = session.client(service_name='bedrock-runtime', region_name='us-east-1', verify=False)
        return bedrock

    def invoke_claude(
        self, 
        prompt: str, 
        system: Optional[str] = None, 
        max_tokens: int = 512, 
        temperature: float = 0.1
    ) -> str:
        """Invoke Claude model through AWS Bedrock"""
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
            response = self.bedrock_client.invoke_model(
                modelId=CLAUDE_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_payload).encode("utf-8")
            )
            response_body = json.loads(response["body"].read().decode("utf-8"))
            return response_body["content"][0]["text"]
        except ClientError as e:
            print(f"AWS Error: Cannot invoke '{CLAUDE_MODEL_ID}'. Reason: {e}")
            raise
        except Exception as e:
            print(f"General Error: {e}")
            raise

    def get_embedding(self, text: str) -> List[float]:
        """Generate embeddings using Amazon Titan"""
        try:
            request_payload = {
                "inputText": text,
                "dimensions": 1024,
                "normalize": True
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=EMBEDDING_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_payload).encode("utf-8")
            )
            
            response_body = json.loads(response["body"].read().decode("utf-8"))
            return response_body["embedding"]
        except Exception as e:
            print(f"Error generating embedding: {e}")
            raise

class ExcelProcessor:
    """Process Excel files to extract capability information"""
    
    def __init__(self, sample_estimations_dir: str):
        self.sample_estimations_dir = Path(sample_estimations_dir)
        self.documents = []
    
    def process_excel_files(self) -> List[CapabilityDocument]:
        """Process all Excel files in the directory and extract capabilities"""
        excel_files = list(self.sample_estimations_dir.glob("*.xlsx")) + list(self.sample_estimations_dir.glob("*.xls"))
        
        for excel_file in excel_files:
            try:
                self._process_single_excel(excel_file)
            except Exception as e:
                print(f"Error processing {excel_file}: {e}")
                continue
        
        return self.documents
    
    def _process_single_excel(self, excel_file: Path):
        """Process a single Excel file"""
        try:
            # Read Excel file and get all sheet names
            xl_file = pd.ExcelFile(excel_file)
            sheet_names = xl_file.sheet_names
            
            # Look for "Capability List" and "Project T-Shirt" sheets
            capability_sheet = None
            project_sheet = None
            
            for sheet in sheet_names:
                if "capability" in sheet.lower() and "list" in sheet.lower():
                    capability_sheet = sheet
                elif "project" in sheet.lower() and "t-shirt" in sheet.lower():
                    project_sheet = sheet
            
            if capability_sheet:
                self._extract_from_capability_sheet(xl_file, capability_sheet, excel_file)
            
            if project_sheet:
                self._extract_from_project_sheet(xl_file, project_sheet, excel_file)
                
        except Exception as e:
            print(f"Error reading Excel file {excel_file}: {e}")
    
    def _extract_from_capability_sheet(self, xl_file: pd.ExcelFile, sheet_name: str, excel_file: Path):
        """Extract capabilities from Capability List sheet"""
        try:
            df = pd.read_excel(xl_file, sheet_name=sheet_name)
            
            # Clean column names
            df.columns = df.columns.str.strip().str.lower()
            
            # Find relevant columns (flexible column matching)
            capability_col = self._find_column(df, ['capability', 'capabilities'])
            scope_col = self._find_column(df, ['scope', 'business description', 'description'])
            system_changes_col = self._find_column(df, ['system changes', 'changes'])
            system_leads_col = self._find_column(df, ['system leads', 'leads'])
            
            if capability_col and scope_col:
                for idx, row in df.iterrows():
                    capability = str(row[capability_col]).strip()
                    scope = str(row[scope_col]).strip()
                    
                    if capability and capability.lower() not in ['nan', 'none', ''] and \
                       scope and scope.lower() not in ['nan', 'none', '']:
                        
                        system_changes = str(row[system_changes_col]).strip() if system_changes_col else ""
                        system_leads = str(row[system_leads_col]).strip() if system_leads_col else ""
                        
                        doc = CapabilityDocument(
                            capability=capability,
                            scope_description=scope,
                            file_name=excel_file.name,
                            file_path=str(excel_file),
                            sheet_name=sheet_name,
                            system_changes=system_changes,
                            system_leads=system_leads
                        )
                        self.documents.append(doc)
                        
        except Exception as e:
            print(f"Error extracting from capability sheet {sheet_name}: {e}")
    
    def _extract_from_project_sheet(self, xl_file: pd.ExcelFile, sheet_name: str, excel_file: Path):
        """Extract capabilities from Project T-Shirt sheet with cost and team information"""
        try:
            # Read the sheet with header detection
            df = pd.read_excel(xl_file, sheet_name=sheet_name, header=None)
            
            # Find the header row (usually contains 'Capability' and other column names)
            header_row = None
            for i, row in df.iterrows():
                if any(str(cell).lower().strip() in ['capability', 'capabilities'] for cell in row if pd.notna(cell)):
                    header_row = i
                    break
            
            if header_row is not None:
                # Re-read with proper header
                df = pd.read_excel(xl_file, sheet_name=sheet_name, header=header_row)
            else:
                # Fallback to default reading
                df = pd.read_excel(xl_file, sheet_name=sheet_name)
            
            # Clean column names
            df.columns = df.columns.astype(str).str.strip().str.lower()
            
            # Find relevant columns with flexible matching
            capability_col = self._find_column(df, ['capability', 'capabilities'])
            
            # Cost-related columns
            cost_cols = self._find_cost_columns(df)
            
            # Team and responsibility columns
            team_cols = self._find_team_columns(df)
            
            # Extract project metadata (usually in top rows)
            project_metadata = self._extract_project_metadata(df)
            
            if capability_col:
                for idx, row in df.iterrows():
                    capability = str(row[capability_col]).strip()
                    if capability and capability.lower() not in ['nan', 'none', '', 'capability']:
                        
                        # Extract cost information
                        cost_info = self._extract_cost_info(row, cost_cols)
                        
                        # Extract team information
                        team_info = self._extract_team_info(row, team_cols)
                        
                        # Combine all information
                        additional_info = self._compile_project_info(row, cost_info, team_info, project_metadata)
                        
                        doc = CapabilityDocument(
                            capability=capability,
                            scope_description=additional_info,
                            file_name=excel_file.name,
                            file_path=str(excel_file),
                            sheet_name=sheet_name,
                            additional_info=additional_info,
                            cost_estimation=cost_info.get('total_cost', ''),
                            team_responsible=team_info.get('primary_team', ''),
                            estimation_contact=project_metadata.get('estimation_contact', ''),
                            accountable_sto=project_metadata.get('accountable_sto', ''),
                            accountable_lto=project_metadata.get('accountable_lto', ''),
                            intake_bc=project_metadata.get('intake_bc', ''),
                            intake_sa=project_metadata.get('intake_sa', ''),
                            cost_breakdown=cost_info
                        )
                        self.documents.append(doc)
                        
        except Exception as e:
            print(f"Error extracting from project sheet {sheet_name}: {e}")
    
    def _find_cost_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """Find cost-related columns"""
        cost_columns = {}
        
        # Common cost column patterns
        cost_patterns = [
            'low', 'mid', 'upper', 'high',
            'olbb', 'cua', 'hp', 'rpt', 'pymt',
            'estimation', 'cost', 'effort', 'hours',
            'ba & qa', 'support'
        ]
        
        for col in df.columns:
            col_lower = str(col).lower()
            for pattern in cost_patterns:
                if pattern in col_lower:
                    cost_columns[pattern] = col
                    break
        
        return cost_columns
    
    def _find_team_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """Find team-related columns"""
        team_columns = {}
        
        # Team column patterns
        team_patterns = [
            'olbb', 'cua', 'hp', 'rpt', 'pymt', 'idp',
            'livelink', 'system', 'team', 'responsible',
            'lead', 'contact'
        ]
        
        for col in df.columns:
            col_lower = str(col).lower()
            for pattern in team_patterns:
                if pattern in col_lower:
                    team_columns[pattern] = col
                    break
        
        return team_columns
    
    def _extract_project_metadata(self, df: pd.DataFrame) -> Dict[str, str]:
        """Extract project metadata from the top rows"""
        metadata = {}
        
        # Look for metadata in the first few rows
        metadata_keys = [
            'estimation contact', 'accountable sto', 'accountable lto',
            'intake bc', 'intake sa', 'tps intake #', 'sizing level'
        ]
        
        for i in range(min(10, len(df))):  # Check first 10 rows
            for j, cell in enumerate(df.iloc[i]):
                if pd.notna(cell) and str(cell).lower().strip() in metadata_keys:
                    # Look for corresponding value in next column
                    if j + 1 < len(df.columns):
                        value = df.iloc[i, j + 1]
                        if pd.notna(value):
                            metadata[str(cell).lower().strip().replace(' ', '_')] = str(value).strip()
        
        return metadata
    
    def _extract_cost_info(self, row: pd.Series, cost_cols: Dict[str, str]) -> Dict[str, str]:
        """Extract cost information from a row"""
        cost_info = {}
        
        for pattern, col in cost_cols.items():
            if col in row.index:
                value = row[col]
                if pd.notna(value) and str(value).strip():
                    cost_info[pattern] = str(value).strip()
        
        # Try to identify total cost
        if 'total' in cost_info:
            cost_info['total_cost'] = cost_info['total']
        elif 'mid' in cost_info:
            cost_info['total_cost'] = cost_info['mid']
        elif 'estimation' in cost_info:
            cost_info['total_cost'] = cost_info['estimation']
        
        return cost_info
    
    def _extract_team_info(self, row: pd.Series, team_cols: Dict[str, str]) -> Dict[str, str]:
        """Extract team information from a row"""
        team_info = {}
        
        for pattern, col in team_cols.items():
            if col in row.index:
                value = row[col]
                if pd.notna(value) and str(value).strip():
                    team_info[pattern] = str(value).strip()
        
        # Identify primary team (usually OLBB)
        if 'olbb' in team_info:
            team_info['primary_team'] = 'OLBB'
        else:
            # Find the first non-empty team
            for pattern, value in team_info.items():
                if value and pattern != 'primary_team':
                    team_info['primary_team'] = pattern.upper()
                    break
        
        return team_info
    
    def _compile_project_info(self, row: pd.Series, cost_info: Dict[str, str], 
                             team_info: Dict[str, str], metadata: Dict[str, str]) -> str:
        """Compile all project information into a comprehensive string"""
        info_parts = []
        
        # Add cost information
        if cost_info:
            info_parts.append("COST INFORMATION:")
            for key, value in cost_info.items():
                info_parts.append(f"  {key.replace('_', ' ').title()}: {value}")
        
        # Add team information
        if team_info:
            info_parts.append("TEAM INFORMATION:")
            for key, value in team_info.items():
                info_parts.append(f"  {key.replace('_', ' ').title()}: {value}")
        
        # Add project metadata
        if metadata:
            info_parts.append("PROJECT METADATA:")
            for key, value in metadata.items():
                info_parts.append(f"  {key.replace('_', ' ').title()}: {value}")
        
        # Add other row information
        other_info = []
        for col, value in row.items():
            if pd.notna(value) and str(value).strip() and str(value).lower() not in ['nan', 'none', '']:
                other_info.append(f"{col}: {value}")
        
        if other_info:
            info_parts.append("ADDITIONAL INFORMATION:")
            info_parts.extend(f"  {info}" for info in other_info[:10])  # Limit to prevent too long text
        
        return "\n".join(info_parts)
    
    def _find_column(self, df: pd.DataFrame, possible_names: List[str]) -> Optional[str]:
        """Find column by possible names"""
        for col in df.columns:
            for name in possible_names:
                if name in col.lower():
                    return col
        return None
    
    def _extract_additional_info(self, row: pd.Series) -> str:
        """Extract additional information from a row"""
        info_parts = []
        for col, value in row.items():
            if pd.notna(value) and str(value).strip():
                info_parts.append(f"{col}: {value}")
        return " | ".join(info_parts)

class DocumentChunker:
    """Create chunks from capability documents without external frameworks"""
    
    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def create_chunks(self, documents: List[CapabilityDocument]) -> List[Dict[str, Any]]:
        """Create chunks from documents"""
        chunks = []
        
        for doc in documents:
            # Combine all text content with enhanced project information
            full_text = f"Capability: {doc.capability}\n"
            full_text += f"Scope/Description: {doc.scope_description}\n"
            
            if doc.system_changes:
                full_text += f"System Changes: {doc.system_changes}\n"
            if doc.system_leads:
                full_text += f"System Leads: {doc.system_leads}\n"
            
            # Add project-specific information
            if doc.cost_estimation:
                full_text += f"Cost Estimation: {doc.cost_estimation}\n"
            if doc.team_responsible:
                full_text += f"Team Responsible: {doc.team_responsible}\n"
            if doc.estimation_contact:
                full_text += f"Estimation Contact: {doc.estimation_contact}\n"
            if doc.accountable_sto:
                full_text += f"Accountable STO: {doc.accountable_sto}\n"
            if doc.accountable_lto:
                full_text += f"Accountable LTO: {doc.accountable_lto}\n"
            if doc.intake_bc:
                full_text += f"Intake BC: {doc.intake_bc}\n"
            if doc.intake_sa:
                full_text += f"Intake SA: {doc.intake_sa}\n"
            
            # Add cost breakdown
            if doc.cost_breakdown:
                full_text += "Cost Breakdown:\n"
                for cost_type, value in doc.cost_breakdown.items():
                    full_text += f"  {cost_type}: {value}\n"
            
            if doc.additional_info:
                full_text += f"Additional Info: {doc.additional_info}\n"
            
            # Create chunks
            text_chunks = self._split_text(full_text)
            
            for i, chunk_text in enumerate(text_chunks):
                chunk = {
                    'id': f"{doc.file_name}_{doc.sheet_name}_{i}",
                    'text': chunk_text,
                    'capability': doc.capability,
                    'file_name': doc.file_name,
                    'file_path': doc.file_path,
                    'sheet_name': doc.sheet_name,
                    'chunk_index': i,
                    # Add project-specific metadata
                    'cost_estimation': doc.cost_estimation,
                    'team_responsible': doc.team_responsible,
                    'estimation_contact': doc.estimation_contact,
                    'accountable_sto': doc.accountable_sto,
                    'accountable_lto': doc.accountable_lto,
                    'intake_bc': doc.intake_bc,
                    'intake_sa': doc.intake_sa,
                    'cost_breakdown': doc.cost_breakdown
                }
                chunks.append(chunk)
        
        return chunks
    
    def _split_text(self, text: str) -> List[str]:
        """Split text into chunks with overlap"""
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), self.chunk_size - self.overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = ' '.join(chunk_words)
            chunks.append(chunk_text)
            
            if i + self.chunk_size >= len(words):
                break
        
        return chunks

class VectorStore:
    """ChromaDB vector store for similarity search"""
    
    def __init__(self, collection_name: str = "capability_search"):
        self.client = chromadb.PersistentClient(
            path="./chroma_db",
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection_name = collection_name
        self.collection = None
        self.aws_client = AWSBedrockClient()
    
    def create_collection(self):
        """Create or get collection"""
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
            print(f"Collection '{self.collection_name}' loaded successfully")
        except:
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Capability search collection"}
            )
            print(f"Collection '{self.collection_name}' created successfully")
    
    def add_documents(self, chunks: List[Dict[str, Any]]):
        """Add document chunks to vector store"""
        if not self.collection:
            self.create_collection()
        
        # Generate embeddings for all chunks
        texts = [chunk['text'] for chunk in chunks]
        embeddings = []
        
        print(f"Generating embeddings for {len(texts)} chunks...")
        for i, text in enumerate(texts):
            if i % 10 == 0:
                print(f"Processing chunk {i+1}/{len(texts)}")
            
            embedding = self.aws_client.get_embedding(text)
            embeddings.append(embedding)
        
        # Prepare data for ChromaDB
        ids = [chunk['id'] for chunk in chunks]
        documents = [chunk['text'] for chunk in chunks]
        metadatas = [
            {
                'capability': chunk['capability'],
                'file_name': chunk['file_name'],
                'file_path': chunk['file_path'],
                'sheet_name': chunk['sheet_name'],
                'chunk_index': chunk['chunk_index'],
                'cost_estimation': chunk.get('cost_estimation', ''),
                'team_responsible': chunk.get('team_responsible', ''),
                'estimation_contact': chunk.get('estimation_contact', ''),
                'accountable_sto': chunk.get('accountable_sto', ''),
                'accountable_lto': chunk.get('accountable_lto', ''),
                'intake_bc': chunk.get('intake_bc', ''),
                'intake_sa': chunk.get('intake_sa', ''),
                'cost_breakdown': str(chunk.get('cost_breakdown', {}))
            }
            for chunk in chunks
        ]
        
        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        print(f"Added {len(chunks)} chunks to vector store")
    
    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search for similar documents"""
        if not self.collection:
            self.create_collection()
        
        # Generate query embedding
        query_embedding = self.aws_client.get_embedding(query)
        
        # Search in ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Format results
        formatted_results = []
        for i in range(len(results['ids'][0])):
            result = {
                'id': results['ids'][0][i],
                'document': results['documents'][0][i],
                'distance': results['distances'][0][i],
                'metadata': results['metadatas'][0][i]
            }
            formatted_results.append(result)
        
        return formatted_results

class CapabilitySearchEngine:
    """Main search engine that orchestrates all components"""
    
    def __init__(self, sample_estimations_dir: str):
        self.sample_estimations_dir = sample_estimations_dir
        self.aws_client = AWSBedrockClient()
        self.vector_store = VectorStore()
        self.is_initialized = False
    
    def initialize(self):
        """Initialize the search engine by processing Excel files"""
        print("Initializing Capability Search Engine...")
        
        # Process Excel files
        print("Processing Excel files...")
        processor = ExcelProcessor(self.sample_estimations_dir)
        documents = processor.process_excel_files()
        print(f"Extracted {len(documents)} capability documents")
        
        # Create chunks
        print("Creating document chunks...")
        chunker = DocumentChunker()
        chunks = chunker.create_chunks(documents)
        print(f"Created {len(chunks)} chunks")
        
        # Add to vector store
        print("Adding chunks to vector store...")
        self.vector_store.add_documents(chunks)
        
        self.is_initialized = True
        print("Initialization complete!")
    
    def search_capability(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        """Search for capabilities and generate comprehensive summary with cost and team analysis"""
        if not self.is_initialized:
            raise Exception("Search engine not initialized. Call initialize() first.")
        
        print(f"Searching for: {query}")
        
        # Search for relevant documents
        search_results = self.vector_store.search(query, top_k)
        
        if not search_results:
            return {
                'query': query,
                'summary': 'No relevant capabilities found.',
                'cost_analysis': 'No cost information available.',
                'team_analysis': 'No team information available.',
                'results': []
            }
        
        # Get the best matching result's file for detailed analysis
        best_match = search_results[0]
        detailed_analysis = self._get_detailed_project_analysis(best_match, query)
        system_changes_analysis = self._generate_system_changes_analysis(query, search_results)
        # Generate summary using Claude
        summary = self._generate_comprehensive_summary(query, search_results, detailed_analysis)
        
        # Generate cost analysis
        cost_analysis = self._generate_cost_analysis(query, search_results, detailed_analysis)
        
        # Generate team analysis
        team_analysis = self._generate_team_analysis(query, search_results, detailed_analysis)
        
        # Format results
        formatted_results = []
        for result in search_results:
            formatted_result = {
                'capability': result['metadata']['capability'],
                'file_name': result['metadata']['file_name'],
                'file_path': result['metadata']['file_path'],
                'sheet_name': result['metadata']['sheet_name'],
                'relevance_score': 1 - result['distance'],
                'cost_estimation': result['metadata'].get('cost_estimation', ''),
                'team_responsible': result['metadata'].get('team_responsible', ''),
                'estimation_contact': result['metadata'].get('estimation_contact', ''),
                'accountable_sto': result['metadata'].get('accountable_sto', ''),
                'accountable_lto': result['metadata'].get('accountable_lto', ''),
                'intake_bc': result['metadata'].get('intake_bc', ''),
                'intake_sa': result['metadata'].get('intake_sa', ''),
                'excerpt': result['document'][:300] + "..." if len(result['document']) > 300 else result['document']
            }
            formatted_results.append(formatted_result)
        
        return {
            'query': query,
            'summary': summary,
            'cost_analysis': cost_analysis,
            'team_analysis': team_analysis,
            'system_changes_analysis': system_changes_analysis,
            'detailed_analysis': detailed_analysis,
            'results': formatted_results
        }
    
    def _get_detailed_project_analysis(self, best_match: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Get detailed analysis from the best matching project sheet"""
        try:
            file_path = best_match['metadata']['file_path']
            
            # Re-read the Excel file to get complete project T-shirt data
            xl_file = pd.ExcelFile(file_path)
            
            # Find Project T-Shirt sheet
            project_sheet = None
            for sheet in xl_file.sheet_names:
                if "project" in sheet.lower() and "t-shirt" in sheet.lower():
                    project_sheet = sheet
                    break
            
            if not project_sheet:
                return {'error': 'Project T-Shirt sheet not found'}
            
            # Read the sheet
            df = pd.read_excel(xl_file, sheet_name=project_sheet)
            
            # Convert to string for analysis
            sheet_data = df.to_string(index=False)
            
            return {
                'file_name': best_match['metadata']['file_name'],
                'sheet_name': project_sheet,
                'sheet_data': sheet_data,
                'capability': best_match['metadata']['capability']
            }
        except Exception as e:
            return {'error': f'Error analyzing project sheet: {e}'}
    
    def _generate_comprehensive_summary(self, query: str, search_results: List[Dict[str, Any]], 
                                      detailed_analysis: Dict[str, Any]) -> str:
        """Generate comprehensive summary using Claude"""
        context = self._build_context(search_results, detailed_analysis)
        
        system_prompt = """You are an expert business capability analyst specializing in project estimation and team analysis. 
        Your task is to provide comprehensive summaries of capabilities based on project documentation.
        
        Guidelines:
        1. Provide a clear, concise summary of the capability
        2. Highlight key business descriptions and scope
        3. Focus on practical implementation aspects
        4. Reference source files appropriately
        5. Keep the summary professional and actionable
        """
        
        user_prompt = f"""
        Analyze the capability "{query}" based on the following information:

        {context}

        Please provide a comprehensive summary covering:
        1. What this capability entails
        2. Key business scope and objectives
        3. Implementation considerations
        4. Source references

        Format your response as a clear, professional summary.
        """
        
        try:
            return self.aws_client.invoke_claude(
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=800,
                temperature=0.3
            )
        except Exception as e:
            return f"Error generating summary: {e}"
    def _generate_system_changes_analysis(self, query: str, search_results: List[Dict[str, Any]]) -> str:
        """Generate system changes analysis using Claude"""
        # Extract system changes info from results
        system_changes_data = []
        for result in search_results:
            if 'system_changes' in result['metadata'] and result['metadata']['system_changes']:
                system_changes_data.append({
                    'capability': result['metadata']['capability'],
                    'system_changes': result['metadata']['system_changes'],
                    'system_leads': result['metadata'].get('system_leads', 'Not specified')
                })
        
        if not system_changes_data:
            return "No system changes information found for this capability."
        
        # Prepare context for Claude
        context = "System Changes Information:\n\n"
        for item in system_changes_data:
            context += f"Capability: {item['capability']}\n"
            context += f"System Changes: {item['system_changes']}\n"
            context += f"System Leads: {item['system_leads']}\n\n"
        
        system_prompt = """You are an enterprise architecture expert specializing in system integration.
        Your task is to analyze system changes required for implementing capabilities.
        
        Focus on:
        1. What systems will be impacted
        2. Nature of changes required
        3. Integration points and dependencies
        4. Responsible system leads
        """
        
        user_prompt = f"""
        Analyze the system changes required for implementing capability "{query}" based on:
        
        {context}
        
        Please provide:
        1. List of systems impacted
        2. Description of changes needed for each system
        3. Integration points and dependencies
        4. Key system leads and their responsibilities
        5. Implementation considerations
        """
        
        try:
            return self.aws_client.invoke_claude(
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=600,
                temperature=0.2
            )
        except Exception as e:
            return f"Error generating system changes analysis: {e}"
        
    def _generate_cost_analysis(self, query: str, search_results: List[Dict[str, Any]], 
                               detailed_analysis: Dict[str, Any]) -> str:
        """Generate cost analysis using Claude"""
        context = self._build_context(search_results, detailed_analysis)
        
        system_prompt = """You are a financial analyst specializing in IT project cost estimation. 
        Your expertise includes analyzing project T-shirt sizing, team allocation costs, and budget planning.
        
        Focus on:
        1. Cost breakdowns by team (OLBB, CUA, HP, RPT, PYMT, etc.)
        2. Estimation ranges (Low, Mid, Upper)
        3. Team-specific charges and rates
        4. Total project cost implications
        5. Budget planning recommendations
        """
        
        user_prompt = f"""
        Analyze the cost implications for the capability "{query}" based on the following project data:

        {context}

        Please provide a detailed cost analysis including:
        1. Total estimated cost (if available)
        2. Cost breakdown by team/system
        3. Estimation ranges (Low, Mid, Upper bounds)
        4. Team-specific costs and who handles what
        5. Any additional teams required and their estimated costs
        6. Budget planning recommendations

        If OLBB team is primarily responsible, highlight that. If other teams are involved, explain their roles and costs.
        """
        
        try:
            return self.aws_client.invoke_claude(
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=800,
                temperature=0.2
            )
        except Exception as e:
            return f"Error generating cost analysis: {e}"
    
    def _generate_team_analysis(self, query: str, search_results: List[Dict[str, Any]], 
                               detailed_analysis: Dict[str, Any]) -> str:
        """Generate team analysis using Claude"""
        context = self._build_context(search_results, detailed_analysis)
        
        system_prompt = """You are an organizational analyst specializing in IT project team structure and responsibilities. 
        Your expertise includes team allocation, role definition, and project governance.
        
        Focus on:
        1. Primary team responsibility (especially OLBB teams)
        2. Supporting teams and their roles
        3. Key contacts and stakeholders
        4. Accountability structure (STO, LTO, BC, SA)
        5. Team coordination requirements
        """
        
        user_prompt = f"""
        Analyze the team structure and responsibilities for the capability "{query}" based on the following project data:

        {context}

        Please provide a detailed team analysis including:
        1. Primary team responsible (highlight if OLBB or other teams)
        2. Supporting teams required and their specific roles
        3. Key contacts and stakeholders:
           - Estimation Contact
           - Accountable STO (Senior Technical Officer)
           - Accountable LTO (Lead Technical Officer)
           - Intake BC (Business Contact)
           - Intake SA (Solution Architect)
        4. Team coordination requirements
        5. Any special considerations for non-OLBB teams

        Comment specifically on OLBB team involvement and any other teams mentioned.
        """
        
        try:
            return self.aws_client.invoke_claude(
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=800,
                temperature=0.2
            )
        except Exception as e:
            return f"Error generating team analysis: {e}"
    
    def _build_context(self, search_results: List[Dict[str, Any]], detailed_analysis: Dict[str, Any]) -> str:
        """Build comprehensive context for Claude analysis"""
        context_parts = []
        
        # Add search results
        context_parts.append("=== SEARCH RESULTS ===")
        for i, result in enumerate(search_results, 1):
            context_parts.append(f"Result {i}:")
            context_parts.append(f"Capability: {result['metadata']['capability']}")
            context_parts.append(f"File: {result['metadata']['file_name']}")
            context_parts.append(f"Sheet: {result['metadata']['sheet_name']}")
            context_parts.append(f"Content: {result['document']}")
            
            # Add metadata
            metadata = result['metadata']
            if metadata.get('cost_estimation'):
                context_parts.append(f"Cost Estimation: {metadata['cost_estimation']}")
            if metadata.get('team_responsible'):
                context_parts.append(f"Team Responsible: {metadata['team_responsible']}")
            if metadata.get('estimation_contact'):
                context_parts.append(f"Estimation Contact: {metadata['estimation_contact']}")
            if metadata.get('accountable_sto'):
                context_parts.append(f"Accountable STO: {metadata['accountable_sto']}")
            if metadata.get('accountable_lto'):
                context_parts.append(f"Accountable LTO: {metadata['accountable_lto']}")
            if metadata.get('intake_bc'):
                context_parts.append(f"Intake BC: {metadata['intake_bc']}")
            if metadata.get('intake_sa'):
                context_parts.append(f"Intake SA: {metadata['intake_sa']}")
            
            context_parts.append("-" * 50)
        
        # Add detailed analysis
        if detailed_analysis and 'sheet_data' in detailed_analysis:
            context_parts.append("=== DETAILED PROJECT T-SHIRT ANALYSIS ===")
            context_parts.append(f"File: {detailed_analysis['file_name']}")
            context_parts.append(f"Sheet: {detailed_analysis['sheet_name']}")
            context_parts.append("Complete Sheet Data:")
            context_parts.append(detailed_analysis['sheet_data'])
        
        return "\n".join(context_parts)
    
    def _generate_summary(self, query: str, search_results: List[Dict[str, Any]]) -> str:
        """Generate summary using Claude"""
        # Prepare context from search results
        context = []
        for i, result in enumerate(search_results, 1):
            context.append(f"Result {i}:")
            context.append(f"Capability: {result['metadata']['capability']}")
            context.append(f"File: {result['metadata']['file_name']}")
            context.append(f"Sheet: {result['metadata']['sheet_name']}")
            context.append(f"Content: {result['document']}")
            context.append("-" * 50)
        
        context_text = "\n".join(context)
        
        system_prompt = """You are an expert analyst specializing in business capability analysis. 
        Your task is to analyze search results and provide a comprehensive summary of capabilities.
        
        Guidelines:
        1. Provide a clear, concise summary of the capability
        2. Highlight key business descriptions and scope
        3. Mention system changes and leads if available
        4. Reference the source files
        5. Keep the summary professional and informative
        6. If multiple similar capabilities are found, synthesize them into a coherent summary
        """
        
        user_prompt = f"""
        Based on the search query "{query}" and the following search results, provide a comprehensive summary:

        {context_text}

        Please provide:
        1. A summary of what this capability entails
        2. Key business descriptions and scope
        3. Any system changes or technical details mentioned
        4. References to the source files

        Format your response as a clear, professional summary.
        """
        
        try:
            summary = self.aws_client.invoke_claude(
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=1000,
                temperature=0.3
            )
            return summary
        except Exception as e:
            print(f"Error generating summary: {e}")
            return f"Error generating summary for query: {query}"

def main():
    """Main function to demonstrate usage"""
    # Example usage
    sample_dir = "path/to/your/Sample_Estimations"  # Update this path
    
    # Initialize search engine
    search_engine = CapabilitySearchEngine(sample_dir)
    
    # Initialize (this will process all Excel files)
    search_engine.initialize()
    
    # Example searches
    example_queries = [
        "review current consent",
        "mutual funds product selection",
        "onboarding process",
        "account management"
    ]
    
    for query in example_queries:
        print(f"\n{'='*50}")
        print(f"Query: {query}")
        print('='*50)
        
        result = search_engine.search_capability(query)
        
        print(f"Summary: {result['summary']}")
        print(f"\nTop {len(result['results'])} Results:")
        
        for i, res in enumerate(result['results'], 1):
            print(f"\n{i}. Capability: {res['capability']}")
            print(f"   File: {res['file_name']}")
            print(f"   Sheet: {res['sheet_name']}")
            print(f"   Relevance: {res['relevance_score']:.2f}")
            print(f"   Excerpt: {res['excerpt']}")

if __name__ == "__main__":
    main()
