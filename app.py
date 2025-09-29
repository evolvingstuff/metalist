import uvicorn
import logging

class FilterCheckUpdates(logging.Filter):
    NOISY_PATTERNS = (
        'POST /api/notes/check-updates',
        'POST /api/notes/acquire-lock',
        'GET /api/auth/sessions',
    )

    def filter(self, record):
        message = record.getMessage()
        return not any(pattern in message for pattern in self.NOISY_PATTERNS)

if __name__ == "__main__":
    # Configure logging to filter out check-updates
    logging.getLogger("uvicorn.access").addFilter(FilterCheckUpdates())
    
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,  # Disable auto-reload
        workers=1  # Limit to a single worker  
    )
