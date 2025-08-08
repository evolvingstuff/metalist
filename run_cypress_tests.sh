#!/bin/bash

echo "🧪 Starting server in test mode..."

# Kill any existing server on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Start from the project root directory
cd "$(dirname "$0")"

# Activate virtual environment and start server in test mode
source .venv/bin/activate
TEST_MODE=1 uvicorn app.main:app --port 8000 > server.log 2>&1 &
SERVER_PID=$!

# Wait for server to be ready
echo "⏳ Waiting for server to start..."
for i in {1..10}; do
  if curl -s http://localhost:8000 > /dev/null; then
    echo "✅ Server is ready!"
    break
  fi
  sleep 1
done

# Run Cypress tests
echo "🏃 Running Cypress tests..."
cd tests/ui
npx cypress run

# Capture test result
TEST_RESULT=$?

# Kill the test server
echo "🛑 Stopping test server..."
kill $SERVER_PID 2>/dev/null

# Show server log if tests failed
if [ $TEST_RESULT -ne 0 ]; then
  echo "❌ Tests failed. Server log:"
  tail -20 server.log
fi

# Exit with test result code
exit $TEST_RESULT