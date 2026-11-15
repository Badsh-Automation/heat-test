"""heat_state.json -> heat_state.b64  (isi ka content GitHub secret HEAT_STATE me paste karo)"""
import base64
import sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\heat_state.json")
dst = Path("heat_state.b64")
dst.write_text(base64.b64encode(src.read_bytes()).decode(), encoding="utf-8")
print(f"Done: {dst.resolve()}  (is file ka poora content HEAT_STATE secret me paste karo)")
