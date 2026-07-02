import asyncio
import json
from core.database import ClusterContextRouter

class SequenceExecutionEngine:
    @staticmethod
    def run_query(cursor, provider_name: str) -> str:
        """Retrieves authentication credentials cleanly using exact schema parameters."""
        cursor.execute(
            "SELECT secret_key FROM api_keys_vault WHERE provider_name = %s;", 
            (provider_name,)
        )
        row = cursor.fetchone()
        return row['secret_key'] if row else "unassigned_token"

    @classmethod
    async def process_pipeline_stream(cls, thread_id: int, content: str):
        """Processes sequential model milestones using explicit, verified dictionary records."""
        try:
            with ClusterContextRouter("transactional") as cursor:
                cursor.execute("""
                    SELECT sequence_order_position, step_name, provider_type, model_string, system_prompt_directives 
                    FROM pipeline_steps 
                    ORDER BY sequence_order_position ASC;
                """)
                steps = cursor.fetchall()
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Pipeline access fault: {str(e)}'})}\n\n"
            return

        if not steps:
            yield f"data: {json.dumps({'error': 'No active model execution sequence found.'})}\n\n"
            return

        current_input = content
        for step in steps:
            pos = step['sequence_order_position']
            name = step['step_name']
            provider = step['provider_type']
            model = step['model_string']
            directives = step['system_prompt_directives']
            
            yield f"data: {json.dumps({'status': f'Executing Stage {pos}: {name} ({model})...'})}\n\n"
            await asyncio.sleep(0.4)
            
            with ClusterContextRouter("master") as cursor:
                api_key = cls.run_query(cursor, provider)
            
            simulated_output = f"\n\n[{name} Output via {model}]:\nProcessed step context successfully using secure parameters."
            for chunk in simulated_output.split(" "):
                if chunk:
                    yield f"data: {json.dumps({'token': chunk + ' '})}\n\n"
                    await asyncio.sleep(0.03)
            
            current_input += simulated_output
            yield f"data: {json.dumps({'status': f'Completed Stage {pos}'})}\n\n"

        try:
            with ClusterContextRouter("transactional") as cursor:
                cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'user', %s);", (thread_id, content))
                cursor.execute("INSERT INTO messages (thread_id, role, content) VALUES (%s, 'assistant', %s);", (thread_id, current_input))
        except Exception as e:
            yield f"data: {json.dumps({'status': f'History synchronization bypassed: {str(e)}'})}\n\n"

        yield "data: [DONE]\n\n"
