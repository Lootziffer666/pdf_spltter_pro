from pathlib import Path

p = Path("pdf_splitter_pro.py")

raw = p.read_bytes()

# fallback decoding (Windows typisch)
text = raw.decode("cp1252", errors="replace")

# Speichern als sauberes UTF-8
p.write_text(text, encoding="utf-8", newline="\n")

print("? Datei jetzt UTF-8 clean")
