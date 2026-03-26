#!/usr/bin/env python3
# scripts/scan_credentials.py
"""
Script to scan for potential credential leaks in the codebase.
"""

import os
import re
import sys
from pathlib import Path

# Patterns to detect potential credentials
CREDENTIAL_PATTERNS = [
    # API keys
    (r'["\']?(api[_-]?key|API[_-]?KEY)["\']?[\s]*[=:][\s]*["\'][a-zA-Z0-9_\-]{10,}["\']', 'API Key'),
    # Passwords
    (r'["\']?(password|PASSWORD)["\']?[\s]*[=:][\s]*["\'][^\s]{5,}["\']', 'Password'),
    # Tokens
    (r'["\']?(token|TOKEN)["\']?[\s]*[=:][\s]*["\'][a-zA-Z0-9_\-]{10,}["\']', 'Token'),
    # Secrets
    (r'["\']?(secret|SECRET)["\']?[\s]*[=:][\s]*["\'][a-zA-Z0-9_\-]{10,}["\']', 'Secret'),
    # Private keys
    (r'-----BEGIN[ A-Z]*PRIVATE KEY-----', 'Private Key'),
    # Slack tokens
    (r'xox[baprs]-[a-zA-Z0-9]{10,}', 'Slack Token'),
    # GitHub tokens
    (r'gh[pousr]_[a-zA-Z0-9]{36,}', 'GitHub Token'),
    # AWS keys
    (r'AKIA[A-Z0-9]{16,}', 'AWS Key'),
]

# File extensions to scan
SCAN_EXTENSIONS = {'.py', '.js', '.ts', '.json', '.yaml', '.yml', '.env', '.cfg', '.conf', '.ini', '.toml'}

# Directories to exclude
EXCLUDE_DIRS = {'__pycache__', '.git', 'node_modules', 'venv', '.venv', 'build', 'dist'}

def scan_file(file_path):
    """Scan a file for potential credential leaks."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return []

    issues = []
    for pattern, description in CREDENTIAL_PATTERNS:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            line_num = content[:match.start()].count('\n') + 1
            issues.append((file_path, line_num, description, match.group()))
    
    return issues

def scan_directory(directory):
    """Recursively scan a directory for potential credential leaks."""
    issues = []
    for root, dirs, files in os.walk(directory):
        # Remove excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix in SCAN_EXTENSIONS:
                issues.extend(scan_file(file_path))
    
    return issues

def main():
    """Main function to scan the codebase for credential leaks."""
    project_root = Path(__file__).parent.parent
    issues = scan_directory(project_root)
    
    if issues:
        print("Potential credential leaks detected:")
        for file_path, line_num, description, match in issues:
            print(f"  {file_path}:{line_num} - {description}: {match}")
        sys.exit(1)
    else:
        print("No potential credential leaks detected.")
        sys.exit(0)

if __name__ == "__main__":
    main()