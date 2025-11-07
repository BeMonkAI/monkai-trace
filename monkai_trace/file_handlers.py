"""Handle JSON file parsing and validation"""

import json
from typing import List, Union
from pathlib import Path
from .models import ConversationRecord, LogEntry


class FileHandler:
    """Handle JSON file parsing and validation"""
    
    @staticmethod
    def load_records_from_json(file_path: Union[str, Path]) -> List[ConversationRecord]:
        """
        Load conversation records from JSON file.
        Supports the format from record_query.json
        
        Args:
            file_path: Path to JSON file with records
            
        Returns:
            List of validated ConversationRecord objects
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both {"records": [...]} and direct array
        if isinstance(data, dict) and 'records' in data:
            records_data = data['records']
        elif isinstance(data, list):
            records_data = data
        else:
            raise ValueError("JSON must contain 'records' key or be an array")
        
        # Parse and validate each record
        records = []
        for record_data in records_data:
            try:
                record = ConversationRecord(**record_data)
                records.append(record)
            except Exception as e:
                print(f"Warning: Skipping invalid record: {e}")
                continue
        
        return records
    
    @staticmethod
    def load_logs_from_json(file_path: Union[str, Path]) -> List[LogEntry]:
        """
        Load logs from JSON file.
        Supports the format from logs.json
        
        Args:
            file_path: Path to JSON file with logs
            
        Returns:
            List of validated LogEntry objects
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both {"logs": [...]} and direct array
        if isinstance(data, dict) and 'logs' in data:
            logs_data = data['logs']
        elif isinstance(data, list):
            logs_data = data
        else:
            raise ValueError("JSON must contain 'logs' key or be an array")
        
        # Parse and validate each log
        logs = []
        for log_data in logs_data:
            try:
                # Remove 'id' if present (server-generated)
                log_data.pop('id', None)
                log = LogEntry(**log_data)
                logs.append(log)
            except Exception as e:
                print(f"Warning: Skipping invalid log: {e}")
                continue
        
        return logs
    
    @staticmethod
    def validate_json_structure(file_path: Union[str, Path], 
                                 expected_type: str = 'records') -> bool:
        """
        Validate JSON file structure before processing.
        
        Args:
            file_path: Path to JSON file
            expected_type: 'records' or 'logs'
            
        Returns:
            True if valid, False otherwise
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if expected_type == 'records':
                if isinstance(data, dict):
                    return 'records' in data
                elif isinstance(data, list):
                    return len(data) > 0 and 'agent' in data[0]
            elif expected_type == 'logs':
                if isinstance(data, dict):
                    return 'logs' in data
                elif isinstance(data, list):
                    return len(data) > 0 and 'level' in data[0]
            
            return False
        except Exception:
            return False
