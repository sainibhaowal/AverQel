import psycopg2  # type: ignore[import-untyped]

conn = psycopg2.connect("dbname=averqel_db user=admin password=admin host=localhost port=1005")
cur = conn.cursor()

cur.execute("""
    SELECT content
    FROM document_chunks
    WHERE document_id = '019cafe0-2cd5-7fa0-b0ff-69ca70b8ea36'
    ORDER BY chunk_index ASC
""")

full_text = []
for row in cur.fetchall():
    full_text.append(row[0])

text = "\n\n".join(full_text)

# Find where Section 4.5 starts
start_idx = text.find("4.5")
if start_idx != -1:
    print(text[max(0, start_idx - 200) : start_idx + 2000])
else:
    print("Substring '4.5' not found.")

cur.close()
conn.close()
