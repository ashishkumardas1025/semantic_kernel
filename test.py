import json
import boto3
from botocore.exceptions import ClientError
import urllib3
from typing import Dict, Any, Optional, Union, List, Set, Tuple
import warnings
import os
import csv
import pandas as pd
from pathlib import Path
import re
from datetime import datetime
from collections import defaultdict, Counter
import networkx as nx
from dataclasses import dataclass
import math

# Configure warnings and disable insecure request warnings
warnings.filterwarnings("ignore", category=UserWarning, message="Unverified HTTPS request")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Model configuration - Claude Haiku
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

@dataclass
class UIComponent:
    """Data class to represent a UI component from Excel"""
    name: str
    file_type: str
    component_type: str
    category: str
    
@dataclass
class ComponentUsage:
    """Data class to track component usage"""
    component: UIComponent
    file_path: str
    line_number: int
    context: str
    usage_type: str  # 'import', 'declaration', 'usage', 'styling'

@dataclass
class ComponentAnalytics:
    """Data class for component analytics"""
    component: UIComponent
    total_usage_count: int
    files_using_component: Set[str]
    usage_by_file_type: Dict[str, int]
    co_occurring_components: Dict[str, int]
    usage_patterns: List[str]
    first_found: Optional[str]
    last_found: Optional[str]

class AngularUIComponentTracker:
    def __init__(self):
        self.bedrock = self.initialize_bedrock_client()
        self.ui_components: List[UIComponent] = []
        self.usage_data: List[ComponentUsage] = []
        self.analytics: Dict[str, ComponentAnalytics] = {}
        self.dependency_graph = nx.DiGraph()
        
        # Angular-specific file patterns
        self.angular_file_patterns = {
            '.ts': ['component.ts', 'service.ts', 'module.ts', 'directive.ts', 'pipe.ts'],
            '.html': ['component.html', 'index.html'],
            '.css': ['component.css', 'styles.css'],
            '.scss': ['component.scss', 'styles.scss'],
            '.js': ['*.js'],
            '.json': ['package.json', 'angular.json', 'tsconfig.json']
        }
        
        # Component detection patterns
        self.detection_patterns = {
            'CSS Class': {
                'html': r'class=["\']([^"\']*{component_name}[^"\']*)["\']',
                'ts': r'["\']([^"\']*{component_name}[^"\']*)["\']',
                'css': r'\.{component_name}[^{{]*{{|\.{component_name}\s*{{',
                'scss': r'\.{component_name}[^{{]*{{|\.{component_name}\s*{{'
            },
            'Custom Element': {
                'html': r'<{component_name}[^>]*>|</{component_name}>',
                'ts': r'{component_name}|["\']({component_name})["\']'
            },
            'React Component': {
                'ts': r'import.*{component_name}|from.*{component_name}|<{component_name}[^>]*>',
                'tsx': r'import.*{component_name}|from.*{component_name}|<{component_name}[^>]*>',
                'html': r'<{component_name}[^>]*>'
            }
        }

    def initialize_bedrock_client(self):
        """Initialize and return AWS Bedrock client"""
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_session_token = os.getenv("AWS_SESSION_TOKEN")

        session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token
        )

        return session.client(service_name='bedrock-runtime', region_name='us-east-1', verify=False)

    def invoke_bedrock_claude(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1500, temperature: float = 0.1) -> str:
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
        except Exception as e:
            print(f"Error invoking Claude: {e}")
            return ""

    def load_ui_components_from_excel(self, excel_path: str) -> List[UIComponent]:
        """Load UI components from Excel file"""
        try:
            df = pd.read_excel(excel_path)
            print(f"Loaded {len(df)} components from Excel file")
            
            components = []
            for _, row in df.iterrows():
                component = UIComponent(
                    name=str(row['name']).strip(),
                    file_type=str(row['file']).strip(),
                    component_type=str(row['type']).strip(),
                    category=str(row['components']).strip()
                )
                components.append(component)
            
            self.ui_components = components
            print(f"Successfully loaded {len(components)} UI components")
            return components
            
        except Exception as e:
            print(f"Error loading Excel file: {e}")
            return []

    def scan_angular_repository(self, repo_path: str) -> List[Path]:
        """Scan Angular repository for relevant files"""
        repo_path = Path(repo_path)
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        
        relevant_files = []
        skip_dirs = {
            'node_modules', '.git', '__pycache__', 'dist', '.angular', 
            'coverage', '.nyc_output', 'e2e', 'docs'
        }
        
        # File extensions to analyze
        target_extensions = {'.ts', '.html', '.css', '.scss', '.js', '.json'}
        
        for file_path in repo_path.rglob('*'):
            if file_path.is_dir():
                continue
                
            # Skip excluded directories
            if any(skip_dir in file_path.parts for skip_dir in skip_dirs):
                continue
                
            # Include relevant file types
            if file_path.suffix.lower() in target_extensions:
                relevant_files.append(file_path)
        
        print(f"Found {len(relevant_files)} files to analyze")
        return relevant_files

    def read_file_safely(self, file_path: Path) -> str:
        """Safely read file content"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    return f.read()
            except Exception as e:
                print(f"Error reading {file_path}: {e}")
                return ""
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return ""

    def detect_component_usage(self, content: str, file_path: Path, component: UIComponent) -> List[ComponentUsage]:
        """Detect component usage in file content using pattern matching"""
        usages = []
        lines = content.split('\n')
        file_ext = file_path.suffix.lower().lstrip('.')
        
        # Get detection patterns for this component type
        patterns = self.detection_patterns.get(component.component_type, {})
        
        for line_num, line in enumerate(lines, 1):
            line_lower = line.lower()
            component_name_lower = component.name.lower()
            
            # Basic name matching
            if component_name_lower in line_lower:
                # More specific pattern matching based on file type and component type
                pattern_found = False
                usage_type = 'usage'
                
                if file_ext in patterns:
                    pattern = patterns[file_ext].format(component_name=re.escape(component.name))
                    if re.search(pattern, line, re.IGNORECASE):
                        pattern_found = True
                
                # Additional context-aware detection
                if 'import' in line_lower and component_name_lower in line_lower:
                    usage_type = 'import'
                    pattern_found = True
                elif 'class=' in line_lower and component_name_lower in line_lower:
                    usage_type = 'styling'
                    pattern_found = True
                elif file_ext == 'ts' and ('selector:' in line_lower or 'component' in line_lower):
                    usage_type = 'declaration'
                    pattern_found = True
                elif not pattern_found and component_name_lower in line_lower:
                    # Fallback for simple name matches
                    pattern_found = True
                
                if pattern_found:
                    usage = ComponentUsage(
                        component=component,
                        file_path=str(file_path),
                        line_number=line_num,
                        context=line.strip()[:200],  # Limit context length
                        usage_type=usage_type
                    )
                    usages.append(usage)
        
        return usages

    def enhanced_component_analysis(self, content: str, file_path: Path, components_in_file: List[UIComponent]) -> str:
        """Use Claude for enhanced component analysis"""
        if not components_in_file:
            return ""
        
        component_names = [comp.name for comp in components_in_file]
        
        prompt = f"""
Analyze this Angular code file and provide detailed information about UI component usage:

File: {file_path}
Components to look for: {', '.join(component_names)}

Code content (first 2000 characters):
{content[:2000]}

Please analyze and provide:
1. Usage patterns for each component found
2. How components interact with each other
3. Context of usage (styling, imports, declarations, etc.)
4. Any component dependencies or relationships

Format response as:
COMPONENT: [component_name]
USAGE_PATTERN: [description]
INTERACTIONS: [other components it works with]
CONTEXT: [how it's used]
---
"""
        
        system_prompt = """You are an expert Angular developer analyzing component usage in codebases. 
        Focus on identifying UI component patterns, relationships, and usage contexts."""
        
        return self.invoke_bedrock_claude(prompt, system_prompt, max_tokens=1000)

    def analyze_repository(self, repo_path: str) -> Dict[str, Any]:
        """Main analysis function"""
        print("Starting repository analysis...")
        
        # Scan repository files
        files = self.scan_angular_repository(repo_path)
        
        # Track progress
        total_files = len(files)
        processed_files = 0
        
        # Store all usage data
        all_usages = []
        file_component_map = defaultdict(list)  # Track which components are in which files
        
        for file_path in files:
            processed_files += 1
            if processed_files % 50 == 0:
                print(f"Progress: {processed_files}/{total_files} files processed")
            
            content = self.read_file_safely(file_path)
            if not content:
                continue
            
            # Find components in this file
            components_in_file = []
            file_usages = []
            
            for component in self.ui_components:
                usages = self.detect_component_usage(content, file_path, component)
                if usages:
                    file_usages.extend(usages)
                    components_in_file.append(component)
                    file_component_map[str(file_path)].extend([comp.name for comp in components_in_file])
            
            # Enhanced analysis for files with multiple components
            if len(components_in_file) > 1:
                enhanced_analysis = self.enhanced_component_analysis(content, file_path, components_in_file)
                # Process enhanced analysis results (can be extended based on needs)
            
            all_usages.extend(file_usages)
        
        self.usage_data = all_usages
        print(f"Found {len(all_usages)} component usages across {processed_files} files")
        
        # Generate analytics
        self.generate_analytics()
        self.build_dependency_graph(file_component_map)
        
        return self.compile_results()

    def generate_analytics(self):
        """Generate comprehensive analytics from usage data"""
        print("Generating analytics...")
        
        component_stats = defaultdict(lambda: {
            'total_usage': 0,
            'files': set(),
            'file_types': defaultdict(int),
            'usage_types': defaultdict(int),
            'co_occurring': defaultdict(int),
            'contexts': [],
            'first_found': None,
            'last_found': None
        })
        
        # Process usage data
        for usage in self.usage_data:
            comp_name = usage.component.name
            stats = component_stats[comp_name]
            
            stats['total_usage'] += 1
            stats['files'].add(usage.file_path)
            
            # File type analysis
            file_ext = Path(usage.file_path).suffix.lower()
            stats['file_types'][file_ext] += 1
            
            # Usage type analysis
            stats['usage_types'][usage.usage_type] += 1
            
            # Context storage
            stats['contexts'].append(usage.context)
            
            # Track first and last occurrences
            if stats['first_found'] is None:
                stats['first_found'] = usage.file_path
            stats['last_found'] = usage.file_path
        
        # Find co-occurring components
        file_components = defaultdict(set)
        for usage in self.usage_data:
            file_components[usage.file_path].add(usage.component.name)
        
        for file_path, components in file_components.items():
            for comp1 in components:
                for comp2 in components:
                    if comp1 != comp2:
                        component_stats[comp1]['co_occurring'][comp2] += 1
        
        # Create ComponentAnalytics objects
        for component in self.ui_components:
            comp_name = component.name
            stats = component_stats[comp_name]
            
            self.analytics[comp_name] = ComponentAnalytics(
                component=component,
                total_usage_count=stats['total_usage'],
                files_using_component=stats['files'],
                usage_by_file_type=dict(stats['file_types']),
                co_occurring_components=dict(stats['co_occurring']),
                usage_patterns=self.identify_usage_patterns(stats),
                first_found=stats['first_found'],
                last_found=stats['last_found']
            )

    def identify_usage_patterns(self, stats: Dict) -> List[str]:
        """Identify usage patterns from statistics"""
        patterns = []
        
        # Most common file type
        if stats['file_types']:
            most_common_type = max(stats['file_types'], key=stats['file_types'].get)
            patterns.append(f"Primarily used in {most_common_type} files")
        
        # Usage type patterns
        if stats['usage_types']:
            most_common_usage = max(stats['usage_types'], key=stats['usage_types'].get)
            patterns.append(f"Most common usage: {most_common_usage}")
        
        # Co-occurrence patterns
        if stats['co_occurring']:
            top_co_occurring = sorted(stats['co_occurring'].items(), key=lambda x: x[1], reverse=True)[:3]
            if top_co_occurring:
                partners = [comp for comp, count in top_co_occurring]
                patterns.append(f"Often used with: {', '.join(partners)}")
        
        return patterns

    def build_dependency_graph(self, file_component_map: Dict[str, List[str]]):
        """Build component dependency graph"""
        print("Building dependency graph...")
        
        # Add nodes for all components
        for component in self.ui_components:
            self.dependency_graph.add_node(component.name, type=component.component_type)
        
        # Add edges based on co-occurrence in files
        for file_path, components in file_component_map.items():
            unique_components = list(set(components))
            for i, comp1 in enumerate(unique_components):
                for comp2 in unique_components[i+1:]:
                    if self.dependency_graph.has_edge(comp1, comp2):
                        self.dependency_graph[comp1][comp2]['weight'] += 1
                    else:
                        self.dependency_graph.add_edge(comp1, comp2, weight=1, files=[file_path])

    def compile_results(self) -> Dict[str, Any]:
        """Compile comprehensive results"""
        results = {
            'summary': self.generate_summary(),
            'component_analytics': {},
            'usage_statistics': self.generate_usage_statistics(),
            'dependency_analysis': self.analyze_dependencies(),
            'file_type_breakdown': self.analyze_file_type_usage(),
            'recommendations': self.generate_recommendations()
        }
        
        # Convert analytics to serializable format
        for comp_name, analytics in self.analytics.items():
            results['component_analytics'][comp_name] = {
                'component_name': analytics.component.name,
                'component_type': analytics.component.component_type,
                'category': analytics.component.category,
                'total_usage_count': analytics.total_usage_count,
                'files_count': len(analytics.files_using_component),
                'files_using_component': list(analytics.files_using_component),
                'usage_by_file_type': analytics.usage_by_file_type,
                'top_co_occurring_components': dict(sorted(
                    analytics.co_occurring_components.items(), 
                    key=lambda x: x[1], reverse=True
                )[:5]),
                'usage_patterns': analytics.usage_patterns,
                'first_found': analytics.first_found,
                'last_found': analytics.last_found
            }
        
        return results

    def generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics"""
        total_components = len(self.ui_components)
        used_components = len([comp for comp in self.analytics.values() if comp.total_usage_count > 0])
        unused_components = total_components - used_components
        total_usages = sum(comp.total_usage_count for comp in self.analytics.values())
        
        return {
            'total_components_in_excel': total_components,
            'components_found_in_repository': used_components,
            'unused_components': unused_components,
            'usage_rate': f"{(used_components/total_components)*100:.1f}%" if total_components > 0 else "0%",
            'total_usage_instances': total_usages,
            'average_usage_per_component': total_usages / used_components if used_components > 0 else 0
        }

    def generate_usage_statistics(self) -> Dict[str, Any]:
        """Generate detailed usage statistics"""
        # Most used components
        most_used = sorted(
            [(name, analytics.total_usage_count) for name, analytics in self.analytics.items()],
            key=lambda x: x[1], reverse=True
        )[:10]
        
        # Components by type usage
        type_usage = defaultdict(int)
        for analytics in self.analytics.values():
            if analytics.total_usage_count > 0:
                type_usage[analytics.component.component_type] += 1
        
        return {
            'most_used_components': most_used,
            'usage_by_component_type': dict(type_usage),
            'unused_components': [
                name for name, analytics in self.analytics.items() 
                if analytics.total_usage_count == 0
            ]
        }

    def analyze_dependencies(self) -> Dict[str, Any]:
        """Analyze component dependencies"""
        # Find strongly connected components
        strongly_connected = list(nx.strongly_connected_components(self.dependency_graph))
        
        # Find most central components
        centrality = nx.degree_centrality(self.dependency_graph)
        most_central = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Find component clusters
        if len(self.dependency_graph.nodes) > 0:
            try:
                clusters = list(nx.connected_components(self.dependency_graph.to_undirected()))
            except:
                clusters = []
        else:
            clusters = []
        
        return {
            'strongly_connected_groups': [list(group) for group in strongly_connected if len(group) > 1],
            'most_central_components': most_central,
            'component_clusters': [list(cluster) for cluster in clusters if len(cluster) > 1],
            'total_dependencies': self.dependency_graph.number_of_edges()
        }

    def analyze_file_type_usage(self) -> Dict[str, Any]:
        """Analyze usage breakdown by file types"""
        file_type_stats = defaultdict(lambda: {'components': set(), 'total_usage': 0})
        
        for usage in self.usage_data:
            file_ext = Path(usage.file_path).suffix.lower()
            file_type_stats[file_ext]['components'].add(usage.component.name)
            file_type_stats[file_ext]['total_usage'] += 1
        
        # Convert to serializable format
        result = {}
        for file_type, stats in file_type_stats.items():
            result[file_type] = {
                'unique_components': len(stats['components']),
                'total_usage_instances': stats['total_usage'],
                'component_list': list(stats['components'])
            }
        
        return result

    def generate_recommendations(self) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        # Unused components
        unused = [name for name, analytics in self.analytics.items() if analytics.total_usage_count == 0]
        if unused:
            recommendations.append(f"Consider reviewing {len(unused)} unused components for potential removal")
        
        # Overused components
        overused = [name for name, analytics in self.analytics.items() if analytics.total_usage_count > 50]
        if overused:
            recommendations.append(f"Consider optimizing {len(overused)} heavily used components for performance")
        
        # Isolated components
        isolated = [node for node in self.dependency_graph.nodes() if self.dependency_graph.degree(node) == 0]
        if isolated:
            recommendations.append(f"Review {len(isolated)} isolated components that don't interact with others")
        
        return recommendations

    def save_results_to_csv(self, results: Dict[str, Any], output_dir: str = "analysis_output"):
        """Save comprehensive results to multiple CSV files"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. Component Usage Summary
        usage_summary_file = output_path / f"component_usage_summary_{timestamp}.csv"
        with open(usage_summary_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Component Name', 'Type', 'Category', 'Total Usage', 'Files Count', 
                'Primary File Type', 'Usage Rate', 'Top Co-occurring Components'
            ])
            
            for comp_name, analytics in results['component_analytics'].items():
                primary_file_type = max(analytics['usage_by_file_type'], 
                                      key=analytics['usage_by_file_type'].get) if analytics['usage_by_file_type'] else 'None'
                top_co_occurring = ', '.join(list(analytics['top_co_occurring_components'].keys())[:3])
                
                writer.writerow([
                    comp_name,
                    analytics['component_type'],
                    analytics['category'],
                    analytics['total_usage_count'],
                    analytics['files_count'],
                    primary_file_type,
                    'Used' if analytics['total_usage_count'] > 0 else 'Unused',
                    top_co_occurring
                ])
        
        # 2. Detailed Usage Data
        detailed_usage_file = output_path / f"detailed_usage_data_{timestamp}.csv"
        with open(detailed_usage_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Component Name', 'File Path', 'Line Number', 'Usage Type', 'Context'
            ])
            
            for usage in self.usage_data:
                writer.writerow([
                    usage.component.name,
                    usage.file_path,
                    usage.line_number,
                    usage.usage_type,
                    usage.context[:100]  # Limit context length
                ])
        
        # 3. File Type Breakdown
        file_type_file = output_path / f"file_type_breakdown_{timestamp}.csv"
        with open(file_type_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'File Type', 'Unique Components', 'Total Usage Instances', 'Component List'
            ])
            
            for file_type, stats in results['file_type_breakdown'].items():
                writer.writerow([
                    file_type,
                    stats['unique_components'],
                    stats['total_usage_instances'],
                    ', '.join(stats['component_list'][:10])  # Limit list length
                ])
        
        # 4. Dependency Analysis
        dependency_file = output_path / f"component_dependencies_{timestamp}.csv"
        with open(dependency_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Component 1', 'Component 2', 'Co-occurrence Count'])
            
            for edge in self.dependency_graph.edges(data=True):
                writer.writerow([edge[0], edge[1], edge[2].get('weight', 1)])
        
        # 5. Summary Report
        summary_file = output_path / f"analysis_summary_{timestamp}.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("Angular UI Component Usage Analysis Report\n")
            f.write("=" * 50 + "\n\n")
            
            # Summary statistics
            f.write("SUMMARY STATISTICS:\n")
            f.write("-" * 20 + "\n")
            for key, value in results['summary'].items():
                f.write(f"{key.replace('_', ' ').title()}: {value}\n")
            
            f.write("\nMOST USED COMPONENTS:\n")
            f.write("-" * 20 + "\n")
            for comp_name, usage_count in results['usage_statistics']['most_used_components']:
                f.write(f"{comp_name}: {usage_count} usages\n")
            
            f.write("\nRECOMMENDALIONS:\n")
            f.write("-" * 15 + "\n")
            for recommendation in results['recommendations']:
                f.write(f"• {recommendation}\n")
        
        print(f"Analysis results saved to {output_path}")
        return output_path

def main():
    """Main function to run the Angular UI Component Tracker"""
    tracker = AngularUIComponentTracker()
    
    # Get inputs from user
    excel_path = input("Enter path to Excel file with UI components: ").strip()
    if not excel_path or not Path(excel_path).exists():
        print("Invalid Excel file path")
        return
    
    repo_path = input("Enter Angular repository path: ").strip()
    if not repo_path or not Path(repo_path).exists():
        print("Invalid repository path")
        return
    
    try:
        # Load components from Excel
        print("Loading UI components from Excel...")
        components = tracker.load_ui_components_from_excel(excel_path)
        
        if not components:
            print("No components loaded from Excel file")
            return
        
        # Analyze repository
        print("Analyzing Angular repository...")
        results = tracker.analyze_repository(repo_path)
        
        # Save results
        output_dir = tracker.save_results_to_csv(results)
        
        # Display summary
        print("\n" + "="*50)
        print("ANALYSIS COMPLETE")
        print("="*50)
        print(f"Total Components: {results['summary']['total_components_in_excel']}")
        print(f"Components Found: {results['summary']['components_found_in_repository']}")
        print(f"Usage Rate: {results['summary']['usage_rate']}")
        print(f"Total Usage Instances: {results['summary']['total_usage_instances']}")
        print(f"Results saved to: {output_dir}")
        
    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
