import json
import boto3
from botocore.exceptions import ClientError
import urllib3
from typing import Dict, Any, Optional, Union, List
import warnings
import os
import csv
from pathlib import Path
import re
from datetime import datetime

# Configure warnings and disable insecure request warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Unverified HTTPS request")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Model configuration - Updated to Claude Haiku
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"  # Claude 3 Haiku model ID

class UIComponentAnalyzer:
    def __init__(self):
        self.bedrock = self.initialize_bedrock_client()
        self.ui_file_extensions = {
            '.js', '.jsx', '.ts', '.tsx',  # React/JavaScript
            '.vue',  # Vue.js
            '.html', '.htm',  # HTML
            '.css', '.scss', '.sass', '.less',  # Stylesheets
            '.py',  # Python (Django templates, Flask)
            '.php',  # PHP
            '.erb', '.haml',  # Ruby
            '.handlebars', '.hbs',  # Handlebars
            '.svelte',  # Svelte
            '.component.html', '.component.ts'  # Angular
        }
        self.results = []

    def initialize_bedrock_client(self):
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

    def invoke_bedrock_claude(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1000, temperature: float = 0.1) -> str:
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
            response = self.bedrock.invoke_model(
                modelId=MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_payload).encode("utf-8")
            )
            response_body = json.loads(response["body"].read().decode("utf-8"))
            return response_body["content"][0]["text"]
        except ClientError as e:
            print(f"AWS Error: Cannot invoke '{MODEL_ID}'. Reason: {e}")
            return f"Error analyzing file: {e}"
        except Exception as e:
            print(f"General Error: {e}")
            return f"Error analyzing file: {e}"

    def is_ui_component_file(self, file_path: Path) -> bool:
        """Check if file is likely a UI component based on extension and content patterns"""
        # Check file extension
        if file_path.suffix.lower() in self.ui_file_extensions:
            return True
        
        # Check for Angular component files
        if '.component.' in file_path.name:
            return True
            
        # Check for specific UI-related directory patterns
        ui_directories = ['components', 'pages', 'views', 'templates', 'ui', 'widgets', 'layouts']
        if any(ui_dir in str(file_path).lower() for ui_dir in ui_directories):
            return True
            
        return False

    def read_file_content(self, file_path: Path) -> str:
        """Safely read file content with encoding detection"""
        try:
            # Try UTF-8 first
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                # Try with latin-1 encoding
                with open(file_path, 'r', encoding='latin-1') as f:
                    return f.read()
            except Exception as e:
                return f"Error reading file: {e}"
        except Exception as e:
            return f"Error reading file: {e}"

    def detect_framework(self, file_content: str, file_path: Path) -> str:
        """Detect the UI framework/library used"""
        frameworks = []
        
        # React patterns
        if re.search(r'import.*React|from [\'"]react[\'"]|useState|useEffect|jsx|tsx', file_content, re.IGNORECASE):
            frameworks.append('React')
        
        # Angular patterns
        if re.search(r'@Component|@Injectable|@NgModule|import.*@angular', file_content, re.IGNORECASE):
            frameworks.append('Angular')
        
        # Vue patterns
        if re.search(r'<template>|<script>|Vue\.|v-if|v-for|@click', file_content, re.IGNORECASE):
            frameworks.append('Vue.js')
        
        # Svelte patterns
        if file_path.suffix == '.svelte' or re.search(r'\$:|on:|bind:', file_content):
            frameworks.append('Svelte')
        
        # HTML/CSS
        if re.search(r'<html|<div|<span|<button|class=|id=', file_content, re.IGNORECASE):
            frameworks.append('HTML/CSS')
        
        # Bootstrap
        if re.search(r'bootstrap|btn-|col-|row|container-fluid', file_content, re.IGNORECASE):
            frameworks.append('Bootstrap')
        
        # Tailwind CSS
        if re.search(r'tailwind|bg-|text-|flex|grid|p-\d|m-\d', file_content, re.IGNORECASE):
            frameworks.append('Tailwind CSS')
        
        return ', '.join(frameworks) if frameworks else 'Unknown'

    def create_analysis_prompt(self, file_content: str, file_path: str, framework: str) -> str:
        """Create a prompt for Claude to analyze the UI component"""
        return f"""
Analyze this UI component file and provide structured information:

File Path: {file_path}
Detected Framework: {framework}

File Content:
```
{file_content[:3000]}  # Limit content to avoid token limits
```

Please provide the following information in a structured format:

1. Component Type: (e.g., Button, Modal, Form, Page, Layout, etc.)
2. Brief Description: (1-2 sentences describing what this component does)
3. Main Features: (List key features/functionality)
4. UI Elements: (List main UI elements like buttons, inputs, etc.)
5. Props/Inputs: (If applicable, list main props or inputs)
6. Styling Approach: (CSS classes, styled-components, etc.)
7. Interactivity: (Event handlers, state management, etc.)
8. Dependencies: (External libraries or components used)

Format your response as:
COMPONENT_TYPE: [type]
DESCRIPTION: [description]
FEATURES: [features separated by semicolons]
UI_ELEMENTS: [elements separated by semicolons]
PROPS: [props separated by semicolons]
STYLING: [styling approach]
INTERACTIVITY: [interactivity description]
DEPENDENCIES: [dependencies separated by semicolons]
"""

    def parse_claude_response(self, response: str) -> Dict[str, str]:
        """Parse Claude's structured response into a dictionary"""
        result = {
            'component_type': 'Unknown',
            'description': 'No description available',
            'features': 'No features identified',
            'ui_elements': 'No UI elements identified',
            'props': 'No props identified',
            'styling': 'No styling information',
            'interactivity': 'No interactivity identified',
            'dependencies': 'No dependencies identified'
        }
        
        patterns = {
            'component_type': r'COMPONENT_TYPE:\s*(.+?)(?:\n|$)',
            'description': r'DESCRIPTION:\s*(.+?)(?:\n|$)',
            'features': r'FEATURES:\s*(.+?)(?:\n|$)',
            'ui_elements': r'UI_ELEMENTS:\s*(.+?)(?:\n|$)',
            'props': r'PROPS:\s*(.+?)(?:\n|$)',
            'styling': r'STYLING:\s*(.+?)(?:\n|$)',
            'interactivity': r'INTERACTIVITY:\s*(.+?)(?:\n|$)',
            'dependencies': r'DEPENDENCIES:\s*(.+?)(?:\n|$)'
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, response, re.IGNORECASE | re.MULTILINE)
            if match:
                result[key] = match.group(1).strip()
        
        return result

    def analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """Analyze a single file for UI components"""
        print(f"Analyzing: {file_path}")
        
        # Read file content
        content = self.read_file_content(file_path)
        if content.startswith("Error reading file"):
            return {
                'file_path': str(file_path),
                'error': content,
                'framework': 'Unknown',
                'file_size': 0
            }
        
        # Detect framework
        framework = self.detect_framework(content, file_path)
        
        # Skip if file is too small or doesn't contain meaningful UI code
        if len(content.strip()) < 50:
            return None
        
        # Create analysis prompt
        prompt = self.create_analysis_prompt(content, str(file_path), framework)
        
        # Get analysis from Claude
        system_prompt = """You are an expert UI/UX developer and code analyzer. 
        Analyze the provided code file and identify UI components, their functionality, 
        and key characteristics. Be concise but comprehensive in your analysis."""
        
        response = self.invoke_bedrock_claude(prompt, system_prompt, max_tokens=1500)
        
        # Parse response
        parsed_result = self.parse_claude_response(response)
        
        # Compile final result
        result = {
            'file_path': str(file_path),
            'relative_path': str(file_path.relative_to(file_path.parts[0])) if len(file_path.parts) > 1 else str(file_path),
            'file_name': file_path.name,
            'file_extension': file_path.suffix,
            'framework': framework,
            'file_size': len(content),
            'component_type': parsed_result['component_type'],
            'description': parsed_result['description'],
            'features': parsed_result['features'],
            'ui_elements': parsed_result['ui_elements'],
            'props_inputs': parsed_result['props'],
            'styling_approach': parsed_result['styling'],
            'interactivity': parsed_result['interactivity'],
            'dependencies': parsed_result['dependencies'],
            'analysis_timestamp': datetime.now().isoformat()
        }
        
        return result

    def scan_repository(self, repo_path: str, max_files: int = 100) -> List[Dict[str, Any]]:
        """Scan repository for UI component files"""
        repo_path = Path(repo_path)
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        
        ui_files = []
        file_count = 0
        
        # Common directories to skip
        skip_dirs = {
            'node_modules', '.git', '__pycache__', '.pytest_cache', 
            'venv', 'env', 'build', 'dist', '.next', 'coverage',
            '.vscode', '.idea', 'logs', '*.egg-info'
        }
        
        print(f"Scanning repository: {repo_path}")
        
        for file_path in repo_path.rglob('*'):
            # Skip directories and hidden files
            if file_path.is_dir() or file_path.name.startswith('.'):
                continue
            
            # Skip files in excluded directories
            if any(skip_dir in file_path.parts for skip_dir in skip_dirs):
                continue
            
            # Check if it's a UI component file
            if self.is_ui_component_file(file_path):
                ui_files.append(file_path)
                file_count += 1
                
                if file_count >= max_files:
                    print(f"Reached maximum file limit ({max_files})")
                    break
        
        print(f"Found {len(ui_files)} UI component files")
        
        # Analyze each file
        results = []
        for i, file_path in enumerate(ui_files, 1):
            print(f"Progress: {i}/{len(ui_files)}")
            try:
                result = self.analyze_file(file_path)
                if result:
                    results.append(result)
            except Exception as e:
                print(f"Error analyzing {file_path}: {e}")
                results.append({
                    'file_path': str(file_path),
                    'error': str(e),
                    'analysis_timestamp': datetime.now().isoformat()
                })
        
        return results

    def save_to_csv(self, results: List[Dict[str, Any]], output_file: str = 'ui_components_analysis.csv'):
        """Save analysis results to CSV file"""
        if not results:
            print("No results to save")
            return
        
        # Define CSV columns
        columns = [
            'file_path', 'relative_path', 'file_name', 'file_extension', 
            'framework', 'component_type', 'description', 'features', 
            'ui_elements', 'props_inputs', 'styling_approach', 
            'interactivity', 'dependencies', 'file_size', 'analysis_timestamp'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=columns)
            writer.writeheader()
            
            for result in results:
                # Ensure all columns exist in result
                row = {col: result.get(col, '') for col in columns}
                writer.writerow(row)
        
        print(f"Analysis saved to: {output_file}")

    def generate_summary_report(self, results: List[Dict[str, Any]]) -> str:
        """Generate a summary report of the analysis"""
        if not results:
            return "No results to summarize"
        
        total_files = len(results)
        frameworks = {}
        component_types = {}
        
        for result in results:
            # Count frameworks
            framework = result.get('framework', 'Unknown')
            frameworks[framework] = frameworks.get(framework, 0) + 1
            
            # Count component types
            comp_type = result.get('component_type', 'Unknown')
            component_types[comp_type] = component_types.get(comp_type, 0) + 1
        
        summary = f"""
UI Component Analysis Summary
=============================
Total Files Analyzed: {total_files}

Framework Distribution:
{'-' * 22}
"""
        for framework, count in sorted(frameworks.items(), key=lambda x: x[1], reverse=True):
            summary += f"{framework}: {count} files\n"
        
        summary += f"""
Component Type Distribution:
{'-' * 27}
"""
        for comp_type, count in sorted(component_types.items(), key=lambda x: x[1], reverse=True):
            summary += f"{comp_type}: {count} files\n"
        
        return summary

def main():
    """Main function to run the UI Component Analyzer"""
    # Initialize analyzer
    analyzer = UIComponentAnalyzer()
    
    # Get repository path from user
    repo_path = input("Enter the repository path to analyze: ").strip()
    if not repo_path:
        print("No repository path provided")
        return
    
    # Optional: Set maximum files to analyze
    max_files_input = input("Maximum files to analyze (default 100): ").strip()
    max_files = int(max_files_input) if max_files_input.isdigit() else 100
    
    try:
        # Scan repository
        print("Starting repository analysis...")
        results = analyzer.scan_repository(repo_path, max_files)
        
        # Save results to CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"ui_components_analysis_{timestamp}.csv"
        analyzer.save_to_csv(results, output_file)
        
        # Generate and display summary
        summary = analyzer.generate_summary_report(results)
        print(summary)
        
        # Save summary to text file
        summary_file = f"ui_analysis_summary_{timestamp}.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(f"Summary saved to: {summary_file}")
        print(f"Detailed analysis saved to: {output_file}")
        
    except Exception as e:
        print(f"Error during analysis: {e}")

if __name__ == "__main__":
    main()
