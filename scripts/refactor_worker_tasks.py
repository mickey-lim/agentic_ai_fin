import re

def update_files():
    # 1. Update worker_tasks.py
    with open("src/agentic_poc/application/worker_tasks.py", "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("source_file_id: str = None,", "source_file_ids: list = None,")
    content = content.replace("async_start_workflow(input_request, thread_id, owner_id, source_file_id, process_family_override)", "async_start_workflow(input_request, thread_id, owner_id, source_file_ids, process_family_override)")

    content = content.replace("async def async_start_workflow(input_request: str, thread_id: str, owner_id: str, source_file_id: str, process_family_override: str):", "async def async_start_workflow(input_request: str, thread_id: str, owner_id: str, source_file_ids: list, process_family_override: str):")
    
    # Change initial agent state building
    content = content.replace("\"source_file_id\": source_file_id,", "\"source_file_ids\": source_file_ids if source_file_ids else [],")

    with open("src/agentic_poc/application/worker_tasks.py", "w", encoding="utf-8") as f:
        f.write(content)

    # 2. Update api.py sync_registry_state
    with open("src/agentic_poc/application/api.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Change how sync_registry_state calls upsert_workflow
    content = content.replace("source_file_id=vals.get(\"source_file_id\", \"\"),", "source_file_ids=vals.get(\"source_file_ids\", []),")

    with open("src/agentic_poc/application/api.py", "w", encoding="utf-8") as f:
        f.write(content)

    print("Updated worker_tasks.py and api.py!")

if __name__ == "__main__":
    update_files()
