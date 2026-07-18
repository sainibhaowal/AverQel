import os

import uvicorn

from app.main import app

# Ensure the 'backend' directory is in sys.path if needed
# But since we are in backend/, app.main should work if we run from here

if __name__ == "__main__":
    port = int(os.environ.get("BACKEND_PORT", 1000))
    # In desktop mode, we only want to listen on localhost
    uvicorn.run(app, host="127.0.0.1", port=port)
