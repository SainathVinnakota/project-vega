import os
from dotenv import load_dotenv

load_dotenv()  # Load .env before anything else

# Purge empty string environment variables to prevent client libraries from throwing credential errors
for _k, _v in list(os.environ.items()):
    if _v == "":
        os.environ.pop(_k, None)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
