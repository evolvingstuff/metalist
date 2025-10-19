import logging
import os

import uvicorn


class FilterCheckUpdates(logging.Filter):
    NOISY_PATTERNS = (
        'POST /api/notes/check-updates',
        'POST /api/notes/acquire-lock',
        'GET /api/auth/sessions',
    )

    def filter(self, record):
        message = record.getMessage()
        return not any(pattern in message for pattern in self.NOISY_PATTERNS)


def main():
    os.environ.setdefault('CRASH_SERVER_ON_FAIL', '1')
    os.environ.setdefault('DEV_ENFORCE_INTEGRITY_CHECKS', '1')

    logging.getLogger("uvicorn.access").addFilter(FilterCheckUpdates())

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
