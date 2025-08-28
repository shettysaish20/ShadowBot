import logging
import sys
from pathlib import Path
import json 
import inspect

# Create custom log levels for JSON blocks and prompts
JSON_BLOCK = 25  # Between INFO (20) and WARNING (30)
PROMPT_BLOCK = 26  # Between INFO (20) and WARNING (30)
CODE_BLOCK = 27  # Between INFO (20) and WARNING (30)
STEP_BLOCK = 28  # Between INFO (20) and WARNING (30)
ERROR_BLOCK = 29  # Between INFO (20) and WARNING (30)
logging.addLevelName(CODE_BLOCK, 'CODE_BLOCK')
logging.addLevelName(JSON_BLOCK, 'JSON_BLOCK')
logging.addLevelName(PROMPT_BLOCK, 'PROMPT_BLOCK')
logging.addLevelName(STEP_BLOCK, 'STEP_BLOCK')
logging.addLevelName(ERROR_BLOCK, 'ERROR_BLOCK')

# Global flag to track if logging has been initialized
_logging_initialized = False

def setup_logging(module_name: str):
    """
    Simple logging setup with both file and console output
    Args:
        module_name: Name of the module for log messages
    """
    global _logging_initialized
    
    # Only initialize once
    if not _logging_initialized:
        # Create logs directory if it doesn't exist
        log_dir = Path(__file__).parent.parent / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        # Common log file path
        log_file = log_dir / 'common.log'

        # Format to include timestamp, level, module name, function name, line number
        log_format = '%(asctime)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s'
        
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(log_file, mode='w', encoding='utf-8'),
                #logging.StreamHandler(sys.stdout)
            ]
        )
        _logging_initialized = True

    return logging.getLogger(module_name)

def get_logger(module_name: str = None):
    """
    Get a logger for the specified module or auto-detect the calling module.
    This eliminates the need to call setup_logging in every file.
    """
    if module_name is None:
        # Auto-detect the calling module
        try:
            frame = inspect.currentframe()
            if frame and frame.f_back:
                module_name = frame.f_back.f_globals.get('__name__', 'unknown')
            else:
                module_name = 'unknown'
        except:
            module_name = 'unknown'
    
    return setup_logging(module_name)

def logger_step(logger, title: str, payload=None, symbol: str = "🟢"):
    """Log a step with optional payload in a clean, readable format"""
    try:
        # Create a separator
        separator = "=" * 80
        
        # Create the complete message
        complete_message = f"\n{separator}\n"
        complete_message += f"{symbol} {title}\n"
        
        # Add payload if provided
        if payload:
            complete_message += f"{separator}\n"
            complete_message += "📊 Payload:\n"
            complete_message += f"{separator}\n"
            # Format payload as JSON if it's a dictionary
            if isinstance(payload, dict):
                payload_str = json.dumps(payload, indent=2, sort_keys=True)
                for line in payload_str.split('\n'):
                    complete_message += f"  {line}\n"
            else:
                complete_message += f"  {payload}\n"
        
        complete_message += f"{separator}\n"
        
        # Log using the custom level
        logger.log(STEP_BLOCK, complete_message)
    except Exception as e:
        logger.error(f"Failed to format step: {e}")
        logger.info(f"{symbol} {title}: {payload}")

def logger_error(logger, message: str, err: Exception = None):
    """Log an error with optional exception details in a clean, readable format"""
    try:
        # Create a separator
        separator = "=" * 80
        
        # Create the complete message
        complete_message = f"\n{separator}\n"
        complete_message += f"❌ {message}\n"
        
        # Add error details if provided
        if err:
            complete_message += f"{separator}\n"
            complete_message += " Error Details:\n"
            complete_message += f"{separator}\n"
            complete_message += f"  Type: {type(err).__name__}\n"
            complete_message += f"  Message: {str(err)}\n"
            
            # Add traceback if available
            import traceback
            tb_lines = traceback.format_exc().split('\n')
            if len(tb_lines) > 1:
                complete_message += f"  Traceback:\n"
                for line in tb_lines:
                    if line.strip():
                        complete_message += f"    {line}\n"
        
        complete_message += f"{separator}\n"
        
        # Log using the custom level
        logger.log(ERROR_BLOCK, complete_message)
    except Exception as e:
        logger.error(f"Failed to format error: {e}")
        if err:
            logger.error(f"❌ {message}: {str(err)}")
        else:
            logger.error(f"❌ {message}")

def logger_json_block(logger, message, data):
    """Log JSON data in a clean block format without timestamps"""
    try:
        # Create a separator
        separator = "=" * 80
        
        # Create the formatted JSON string
        json_str = json.dumps(data, indent=2, sort_keys=False)
        
        # Create the complete message
        complete_message = f"\n{separator}\n📌 {message}\n{separator}\n{json_str}\n{separator}\n"
        
        # Log using the custom level
        logger.log(JSON_BLOCK, complete_message)
    except Exception as e:
        logger.error(f"Failed to format JSON: {e}")
        logger.info(f"{message}: {data}")

def logger_prompt(logger, message, prompt):
    """Log prompts in a clean, readable format without timestamps"""
    try:
        # Create a separator
        separator = "=" * 80
        
        # Create the complete message
        prompt_lines = prompt.split('\n')
        formatted_lines = []
        for line in prompt_lines:
            # Skip empty lines
            if not line.strip():
                continue
            # Skip markdown code block markers
            if line.strip() in ['```json', '```', '---']:
                continue
            # Add the line with proper indentation
            formatted_lines.append(f"  {line}")
        
        complete_message = f"\n{separator}\n📝 {message}\n{separator}\n" + "\n".join(formatted_lines) + f"\n{separator}\n"
        
        # Log using the custom level
        logger.log(PROMPT_BLOCK, complete_message)
    except Exception as e:
        logger.error(f"Failed to format prompt: {e}")
        logger.info(f"{message}: {prompt}")

def logger_code_block(logger, message, code, output=None):
    """Log code and its output in a clean, readable format"""
    try:
        # Create a separator
        separator = "=" * 80
        
        # Create the complete message
        complete_message = f"\n{separator}\n"
        complete_message += f"📝 {message}\n"
        complete_message += f"{separator}\n"
        
        # Add code section
        complete_message += "🔧 Code:\n"
        complete_message += f"{separator}\n"
        # Split code into lines and add proper indentation
        code_lines = code.split('\n')
        for line in code_lines:
            complete_message += f"  {line}\n"
        
        # Add output section if provided
        if output:
            complete_message += f"\n{separator}\n"
            complete_message += "📊 Output:\n"
            complete_message += f"{separator}\n"
            # Format output as JSON if it's a dictionary
            if isinstance(output, dict):
                output_str = json.dumps(output, indent=2, sort_keys=True)
                for line in output_str.split('\n'):
                    complete_message += f"  {line}\n"
            else:
                complete_message += f"  {output}\n"
        
        complete_message += f"{separator}\n"
        
        # Log using the custom level
        logger.log(CODE_BLOCK, complete_message)
    except Exception as e:
        logger.error(f"Failed to format code block: {e}")
        logger.info(f"{message}: {code}")