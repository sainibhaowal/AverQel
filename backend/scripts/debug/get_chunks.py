import uuid

from app.documents.repositories.chunks import ChunksRepository
from app.platform.database.session import get_session_factory

db = get_session_factory()()
tenant_id = uuid.UUID("019caed9-ae3e-7335-9961-55201e1a4941")
document_id = uuid.UUID("019cafe0-2cd5-7fa0-b0ff-69ca70b8ea36")

repo = ChunksRepository(db)
chunks = repo.get_by_document_id(tenant_id=tenant_id, document_id=document_id, limit=1000)

full_text = "\n\n".join([c.content for c in chunks])
idx = full_text.find("4.5 ")
if idx == -1:
    idx = full_text.find("4.5\n")
if idx == -1:
    idx = full_text.find("4.5")

if idx != -1:
    print(full_text[max(0, int(idx) - 200) : int(idx) + 2000])
else:
    print("Not found in chunks. Chunk count:", len(chunks))

db.close()
