import ast
import os
from openai import OpenAI
import google.generativeai as genai
from core.database import run_query

def verify_code_safety(code_string: str) -> bool:
    try:
        tree = ast.parse(code_string)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)): return False
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ["eval", "exec", "open", "compile", "globals", "locals", "subprocess"]: return False
        return True
    except Exception:
        return False

def execute_pipeline_step(step, current_payload):
    if not verify_code_safety(step['python_code_body']):
        return "Security Halt: Code execution string failed parameters."
    
    local_scope = {}
    global_scope = {"OpenAI": OpenAI, "genai": genai}
    
    try:
        exec(step['python_code_body'], global_scope, local_scope)
        
        # 1. Look up credential mappings inside database vault first
        provider_name = step['provider_identifier'].strip().lower()
        db_key_lookup = run_query("SELECT api_key FROM api_keys_vault WHERE provider_identifier = %s;", (provider_name,))
        
        if db_key_lookup and db_key_lookup[0].get('api_key'):
            target_api_key = db_key_lookup[0]['api_key']
        else:
            # 2. Fall back to system environment variables if database row is empty
            target_api_key = os.environ.get(f"{step['provider_identifier'].upper()}_API_KEY")
        
        return local_scope['execute_step'](
            payload=current_payload,
            system_prompt=step['system_prompt'],
            model_string=step['model_string'],
            api_key=target_api_key
        )
    except Exception as e:
        return f"Pipeline Execution Fault. Trace: {str(e)}"
