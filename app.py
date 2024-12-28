import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,  # Enable auto-reload during development
        workers=1  # Limit to a single worker  TODO: this is not a fix for undo/redo transactions
    )