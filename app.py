import uvicorn
import logging

class FilterCheckUpdates(logging.Filter):
    def filter(self, record):
        return 'POST /api/notes/check-updates' not in record.getMessage()

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