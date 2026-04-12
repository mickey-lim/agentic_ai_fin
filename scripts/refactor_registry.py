import re

def update_registry():
    with open("src/agentic_poc/registry.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update init_registry schema
    schema_code = """
        # File Source Registry (Phase 7)
        await db.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS file_registry (
                file_id TEXT PRIMARY KEY,
                owner_id TEXT,
                stored_path TEXT,
                original_filename TEXT,
                size_bytes INTEGER,
                content_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_hash TEXT,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        \"\"\")
        
        # M:N File Relation
        await db.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS workflow_source_files (
                thread_id TEXT,
                file_id TEXT,
                sort_order INTEGER,
                PRIMARY KEY (thread_id, file_id)
            )
        \"\"\")
"""
    content = re.sub(
        r'# File Source Registry \(Phase 7\).*?\"\"\"\)', 
        schema_code.strip(), 
        content, 
        flags=re.DOTALL
    )

    # 2. Update upsert_workflow signature & logic
    content = content.replace("source_file_id: str = \"\",", "source_file_id: str = \"\",\n    source_file_ids: Optional[List[str]] = None,")
    
    upsert_db_exec = """
        if row is None:
            # Insert
            await db.execute(\"\"\"
                INSERT INTO workflow_registry 
                (thread_id, workflow_id, owner_id, status, next_task, process_family, input_request_summary, source_file_id, last_error, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            \"\"\", (
                thread_id, workflow_id, owner_id, status, next_task, 
                process_family, input_request_summary, source_file_id, last_error, now, now
            ))
        else:
"""
    
    # We add handling for source_file_ids at the end of the transaction
    upsert_finish_logic = """
            query = f"UPDATE workflow_registry SET {', '.join(updates)} WHERE thread_id = ?"
            await db.execute(query, params)
            
        if source_file_ids is not None:
            await db.execute("DELETE FROM workflow_source_files WHERE thread_id = ?", (thread_id,))
            for i, fid in enumerate(source_file_ids):
                await db.execute("INSERT INTO workflow_source_files (thread_id, file_id, sort_order) VALUES (?, ?, ?)", (thread_id, fid, i))
                
        await db.commit()
"""
    content = re.sub(
        r'query = f"UPDATE workflow_registry SET \{.*?\n\s+await db\.execute\(query, params\)\n\s+await db\.commit\(\)',
        upsert_finish_logic.strip(),
        content,
        flags=re.DOTALL
    )

    # 3. Update get_workflows
    get_wf_query_replace = """
        query = "SELECT w.*, (SELECT GROUP_CONCAT(file_id) FROM workflow_source_files WHERE thread_id = w.thread_id ORDER BY sort_order) as source_file_ids FROM workflow_registry w WHERE w.owner_id = ?"
        params = [owner_id]
        
        if not include_deleted:
            query += " AND w.status NOT IN ('deleted', 'purging', 'purged')"
            
        if status_filter:
            query += " AND w.status = ?"
            params.append(status_filter)
            
        if cursor:
            # Decode cursor (format: 'updated_at_iso|thread_id')
            parts = cursor.split('|', 1)
            if len(parts) == 2:
                c_updated_at, c_thread_id = parts
                query += " AND (w.updated_at < ? OR (w.updated_at = ? AND w.thread_id < ?))"
                params.extend([c_updated_at, c_updated_at, c_thread_id])
                
        query += " ORDER BY w.updated_at DESC, w.thread_id DESC LIMIT ?"
        params.append(limit)
        
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                r_dict = dict(r)
                if r_dict.get("source_file_ids"):
                    r_dict["source_file_ids"] = r_dict["source_file_ids"].split(",")
                else:
                    r_dict["source_file_ids"] = []
                results.append(r_dict)
            return results
"""
    content = re.sub(
        r'query = "SELECT \* FROM workflow_registry WHERE owner_id = \?".*?return \[dict\(r\) for r in rows\]',
        get_wf_query_replace.strip(),
        content,
        flags=re.DOTALL
    )

    # Also fix any syntax or missing imports
    if "from typing import List, Dict, Any, Optional" not in content:
        content = "from typing import List, Dict, Any, Optional\n" + content

    with open("src/agentic_poc/registry.py", "w", encoding="utf-8") as f:
        f.write(content)
        
    print("Updated registry.py!")

if __name__ == "__main__":
    update_registry()
