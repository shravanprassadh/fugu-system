import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

def run_heartbeat():
    print("🧬 Initializing Sovereign Infrastructure Keep-Alive Protocol...")
    
    master_url = os.environ.get("MASTER_ROUTER_DB_URL")
    if not master_url:
        print("❌ Critical Failure: MASTER_ROUTER_DB_URL variable is missing.")
        sys.exit(1)
        
    try:
        print("🔗 Connecting to Master Router DB...")
        router_conn = psycopg2.connect(master_url)
        
        with router_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM db_routing_matrix;")
            rows = cur.fetchall()
            matrix = {row['operation']: row['connection_string'] for row in rows}
            
        router_conn.close()
        print("✅ Master Router mapping matrix verified.")
        
    except Exception as e:
        print(f"❌ Master Router Connection Fault: {str(e)}")
        sys.exit(1)

    threads_db_url = matrix.get("threads", master_url)
    messages_db_url = matrix.get("messages", master_url)

    print("📁 Triggering activity on Sidebar Metadata DB...")
    try:
        threads_conn = psycopg2.connect(threads_db_url)
        with threads_conn.cursor() as cur:
            cur.execute("INSERT INTO threads (name) VALUES ('__SYSTEM_HEARTBEAT_TRACK__') "
                        "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id;")
            heartbeat_thread_id = cur.fetchone()[0]
            threads_conn.commit()
        print(f"✅ Metadata sync active. Allocated tracking ID: {heartbeat_thread_id}")
    except Exception as e:
        print(f"⚠️ Metadata DB Sync Warning: {str(e)}")
        heartbeat_thread_id = None

    print("🗄️ Triggering write sequences on Transactional Log DB...")
    if heartbeat_thread_id:
        try:
            msg_conn = psycopg2.connect(messages_db_url)
            with msg_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO messages (thread_id, role, content) VALUES (%s, 'system', "
                    "'CRON_HEARTBEAT_VALIDATION_STREAM_TOKEN_UTILIZATION_NET_ZERO_CYCLE_RUNNING');",
                    (heartbeat_thread_id,)
                )
                msg_conn.commit()
            msg_conn.close()
            print("✅ Transactional storage blocks processed successfully.")
        except Exception as e:
            print(f"⚠️ Transactional DB Sync Warning: {str(e)}")

    print("🧹 Executing deep storage data purge...")
    if heartbeat_thread_id:
        try:
            msg_conn = psycopg2.connect(messages_db_url)
            with msg_conn.cursor() as cur:
                cur.execute("DELETE FROM messages WHERE thread_id = %s;", (heartbeat_thread_id,))
                msg_conn.commit()
            msg_conn.close()

            with threads_conn.cursor() as cur:
                cur.execute("DELETE FROM threads WHERE id = %s;", (heartbeat_thread_id,))
                threads_conn.commit()
            threads_conn.close()
            
            print("✅ Storage optimization clean. Net-zero balance maintained.")
        except Exception as e:
            print(f"❌ Purge execution aborted mid-cycle: {str(e)}")
            sys.exit(1)
            
    print("🎉 Infrastructure keep-alive cycle complete. All provider dormancy timers reset.")

if __name__ == "__main__":
    run_heartbeat()
