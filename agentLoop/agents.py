import yaml
import json
from pathlib import Path
from typing import Optional, List
from agentLoop.model_manager import ModelManager
from utils.json_parser import parse_llm_json
from utils.utils import log_step, log_error
from PIL import Image
import os

class AgentRunner:
    def __init__(self, multi_mcp):
        self.multi_mcp = multi_mcp
        
        # Load agent configurations
        config_path = Path("config/agent_config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            self.agent_configs = yaml.safe_load(f)["agents"]

    def _analyze_file_strategy(self, uploaded_files):
        """Analyze files to determine best upload strategy"""
        total_size = 0
        file_info = []
        
        for file_path in uploaded_files:
            path = Path(file_path)
            if path.exists():
                size = path.stat().st_size
                total_size += size
                file_info.append({
                    'path': file_path,
                    'size': size,
                    'extension': path.suffix.lower()
                })
        
        # Decision logic
        if total_size < 15_000_000:  # < 15MB total (leave 5MB buffer for 20MB limit)
            return "inline_batch"  # Send all as inline data
        elif len(file_info) == 1 and total_size < 50_000_000:  # Single file < 50MB
            return "files_api_single"  # Use Files API for single file
        else:
            return "files_api_individual"  # Use Files API for each file

    def _get_mime_type(self, extension):
        """Get MIME type for file extension"""
        mime_type_map = {
            # Documents  
            '.pdf': 'application/pdf',
            '.txt': 'text/plain',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.rtf': 'application/rtf',
            '.json': 'application/json',
            
            # Spreadsheets
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
            '.xls': 'application/vnd.ms-excel',
            '.csv': 'text/csv',
            '.tsv': 'text/tab-separated-values',
            
            # Presentations 
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            
            # Images
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg', 
            '.webp': 'image/webp',
            '.heif': 'image/heif',
            
            # Videos
            '.mp4': 'video/mp4',
            '.mpeg': 'video/mpeg',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.mpg': 'video/mpeg',
            '.webm': 'video/webm',
            '.wmv': 'video/x-ms-wmv',
            '.flv': 'video/x-flv',
            '.3gp': 'video/3gpp',
            
            # Code files
            '.c': 'text/x-c',
            '.cpp': 'text/x-c++',
            '.py': 'text/x-python',
            '.java': 'text/x-java',
            '.php': 'text/x-php',
            '.sql': 'application/sql',
            '.html': 'text/html',
            '.htm': 'text/html',
            '.css': 'text/css',          
            '.js': 'text/javascript',    
            '.json': 'application/json', 
            '.xml': 'text/xml',          
            '.md': 'text/markdown',      
            '.txt': 'text/plain', 
        }
        
        return mime_type_map.get(extension, 'application/octet-stream')

    def _load_file_content(self, file_path: str, strategy: str = "auto"):
        """Load file using optimal strategy based on analysis"""
        try:
            path = Path(file_path)
            if not path.exists():
                log_error(f"File not found: {file_path}")
                return None
                
            if strategy == "inline_batch":
                # For small files - use inline data
                from google.genai import types
                return types.Part.from_bytes(
                    data=path.read_bytes(),
                    mime_type=self._get_mime_type(path.suffix.lower())
                )
                
            elif strategy in ["files_api_single", "files_api_individual"]:
                # For large files - use Files API (handled in run_agent)
                return {
                    "upload_to_files_api": True,
                    "file_path": str(path),
                    "mime_type": self._get_mime_type(path.suffix.lower())
                }
                
        except Exception as e:
            log_error(f"Error loading file {file_path}: {e}")
            return None

    def _detect_files_in_inputs(self, input_data):
        """Detect file paths in the inputs - handles both 'files' and 'inputs' parameters"""
        all_files = []
        
        # Check 'files' parameter (direct file list)
        if 'files' in input_data and input_data['files']:
            all_files.extend(input_data['files'])
        
        # Check 'image' parameter (single image)
        if 'image' in input_data and input_data['image']:
            all_files.append(input_data['image'])
        
        # ✅ CHECK 'inputs' parameter - ONLY treat as file if it actually exists
        if 'inputs' in input_data and input_data['inputs']:
            inputs = input_data['inputs']
            if isinstance(inputs, dict):
                for key, value in inputs.items():
                    if isinstance(value, str):
                        # ✅ SIMPLE: Just check if the path exists!
                        if os.path.exists(value):
                            all_files.append(value)
                            log_step(f"✅ Found actual file: {value}", symbol="📁")
                        # ✅ Don't log errors for non-existent paths (they're just regular data)
        
        return all_files

    async def run_agent(self, agent_type, input_data):
        """Run a specific agent with the given input data"""
        try:
            # Get agent config
            if agent_type not in self.agent_configs:
                return {"success": False, "error": f"Unknown agent: {agent_type}"}
            
            agent_config = self.agent_configs[agent_type]
            
            # ✅ UNIFIED FILE DETECTION - Check multiple input sources
            all_files = self._detect_files_in_inputs(input_data)
            file_contents = []
            
            # Process files if found
            if all_files:
                strategy = self._analyze_file_strategy(all_files)
                # log_step(f"📁 File strategy: {strategy} for {len(all_files)} files")
                
                # Initialize model manager for Files API uploads
                model_manager = ModelManager(agent_config.get("model", "gemini-2.0-flash"))
                
                # Process files based on strategy
                for file_path in all_files:
                    if strategy == "inline_batch":
                        # Load as inline data
                        content = self._load_file_content(file_path, strategy)
                        if content:
                            file_contents.append(content)
                    else:
                        # Upload to Files API
                        uploaded_file = model_manager.client.files.upload(
                            file=file_path
                        )
                        file_contents.append(uploaded_file)
                        # log_step(f"📤 Uploaded {file_path} to Files API")
            else:
                # Initialize model manager for text-only requests
                model_manager = ModelManager(agent_config.get("model", "gemini-2.0-flash"))

            # Load system prompt
            prompt_file_path = agent_config.get('prompt_file')
            if not prompt_file_path:
                return {"success": False, "error": f"No prompt_file configured for {agent_type}"}
            
            system_prompt_path = Path(prompt_file_path)
            if not system_prompt_path.exists():
                return {"success": False, "error": f"Prompt file not found: {prompt_file_path}"}
                
            with open(system_prompt_path, "r", encoding="utf-8") as f:
                system_prompt = f.read()

            # Build the full prompt
            full_prompt = self._build_prompt(system_prompt, input_data)
            
            # ✅ TRACK RESPONSE AND METADATA
            if file_contents:
                # Files present - send files + prompt
                log_step(f"🤖 {agent_type} (with {len(file_contents)} files)")
                response = await model_manager.generate_content([*file_contents, full_prompt])
            else:
                # Text only
                log_step(f"💬 {agent_type} (text only)")
                response = await model_manager.generate_text(full_prompt)

            # ✅ PARSE JSON AND INCLUDE METADATA (like original)
            try:
                # Try to parse as JSON first
                parsed_output = parse_llm_json(response)
                
                # ✅ FIXED: Correct Gemini 2.0 Flash pricing
                input_token_count = len(full_prompt.split()) * 1.5  # Fixed: 1.5 not 1.3
                output_token_count = len(response.split()) * 1.5   # Fixed: 1.5 not 1.3
                estimated_cost = (input_token_count * 0.00000015) + (output_token_count * 0.0000006)  # Correct Gemini pricing
                
                result_with_metadata = {
                    **parsed_output,
                    "cost": estimated_cost,
                    "input_tokens": input_token_count,
                    "output_tokens": output_token_count,
                    "total_tokens": input_token_count + output_token_count
                }
                
                return {"success": True, "output": result_with_metadata}
                
            except Exception as e:
                # If JSON parsing fails, return raw response
                log_error(f"JSON parsing failed for {agent_type}: {e}")
                return {"success": True, "output": {"response": response}}
            
        except Exception as e:
            log_error(f"Agent {agent_type} failed: {e}")
            return {"success": False, "error": str(e)}

    def _build_prompt(self, system_prompt, input_data):
        """Build the complete prompt from system prompt and input data"""
        # Start with system prompt
        prompt_parts = [system_prompt]
        
        # Add input data context
        if input_data:
            prompt_parts.append("\n--- Input Data ---")
            for key, value in input_data.items():
                if key == 'inputs' and isinstance(value, dict):
                    # ✅ HANDLE GRAPH INPUTS - Include the actual data from previous nodes
                    prompt_parts.append("\n--- Context from Previous Steps ---")
                    for input_key, input_value in value.items():
                        if isinstance(input_value, (dict, list)):
                            prompt_parts.append(f"{input_key}: {json.dumps(input_value, indent=2)}")
                        else:
                            prompt_parts.append(f"{input_key}: {input_value}")
                elif key not in ['files', 'image']:  # Only exclude file-related data
                    prompt_parts.append(f"{key}: {value}")
        
        return "\n".join(prompt_parts)