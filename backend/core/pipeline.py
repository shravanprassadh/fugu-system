import ast
import os
from openai import OpenAI
import google.generativeai as genai

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
        
        # Dynamically pulls OPENROUTER_API_KEY or GEMINI_API_KEY from Render config
        target_api_key = os.environ.get(f"{step['provider_identifier'].upper()}_API_KEY")
        
        return local_scope['execute_step'](
            payload=current_payload,
            system_prompt=step['system_prompt'],
            model_string=step['model_string'],
            api_key=target_api_key
        )
    except Exception as e:
        return f"Pipeline Execution Fault. Trace: {str(e)}"
