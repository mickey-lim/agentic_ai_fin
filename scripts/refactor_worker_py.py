import re

def update_worker():
    with open("src/agentic_poc/nodes/worker.py", "r", encoding="utf-8") as f:
        content = f.read()

    # We need to replace the single source_file_id line in the task="collect" block
    old_collect = """
                        source_file_id = state.get("source_file_id")
                        df = adapter.collect(source_file_id)
                        df.to_excel(target_file, index=False)
                        
                        output_data["collected_path"] = str(target_file)
                        evidence_list.append(str(target_file))
                        parser_type = getattr(df, "attrs", {}).get("parser_type", "excel/csv")
                        
                        # Preserve existing provenance, update with sequence logic
                        current_prov = dict(state.get("provenance", {}))
                        current_prov.update({
                            "adapter": adapter.adapter_id, 
                            "operation": "collect",
                            "parser_type": parser_type
                        })
"""
    new_collect = """
                        source_file_ids = state.get("source_file_ids", [])
                        dfs = []
                        parser_types = []
                        import pandas as pd
                        
                        if not source_file_ids:
                            df = adapter.collect(None)
                            parser_types.append("mock")
                        else:
                            for fid in source_file_ids:
                                try:
                                    df_part = adapter.collect(fid)
                                    df_part["_source_file_id"] = fid
                                    parser_types.append(getattr(df_part, "attrs", {}).get("parser_type", "excel/csv"))
                                    dfs.append(df_part)
                                except Exception as e:
                                    raise ValueError(f"Partial failure parsing {fid}: {str(e)}")
                            
                            df = pd.concat(dfs, ignore_index=True) if dfs else adapter.collect(None)
                            
                        df.to_excel(target_file, index=False)
                        
                        output_data["collected_path"] = str(target_file)
                        evidence_list.append(str(target_file))
                        
                        # Preserve existing provenance, update with sequence logic
                        current_prov = dict(state.get("provenance", {}))
                        current_prov.update({
                            "adapter": adapter.adapter_id, 
                            "operation": "collect",
                            "parser_type": parser_types[0] if len(set(parser_types)) == 1 else "mixed",
                            "parsed_file_count": len(dfs)
                        })
"""
    content = content.replace(old_collect.strip(), new_collect.strip())

    with open("src/agentic_poc/nodes/worker.py", "w", encoding="utf-8") as f:
        f.write(content)
        
    print("Updated worker.py!")

if __name__ == "__main__":
    update_worker()
