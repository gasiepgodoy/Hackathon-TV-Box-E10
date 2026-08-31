import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.utils.academic_db import get_academic_context
ctx = get_academic_context()
print("--- DATABASE CONTEXT ---")
print(ctx)
print("--- OK ---")
