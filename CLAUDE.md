# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python FastAPI-based application that creates an OpenAI-compatible API proxy for Vertical Studio's AI models. The application allows clients to interact with Claude models through the standard OpenAI API format while routing requests to Vertical Studio's backend.

## Key Commands

### Running the Application
```bash
python main.py
```
The server will start on `http://0.0.0.0:8000` by default.

### Development with Uvicorn
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Architecture

### Core Components

- **FastAPI Application** (`main.py`): Single-file application containing all logic
- **Authentication System**: Two-layer authentication:
  - Client API keys for accessing the proxy service
  - Vertical Studio auth tokens for backend API calls
- **Model Configuration**: JSON-based model definitions with thinking/non-thinking variants
- **Conversation Caching**: LRU cache system for maintaining conversation context
- **Stream Processing**: Real-time streaming support with OpenAI SSE format

### Key Files

- `main.py`: Main application with all FastAPI endpoints, auth, caching, and streaming logic
- `models.json`: Model configuration mapping model IDs to Vertical Studio endpoints
- `client_api_keys.json`: Array of valid client API keys for proxy access
- `vertical.txt`: Vertical Studio authentication tokens (base64 encoded)

### Important Classes

- `ChatCompletionRequest`/`ChatCompletionResponse`: OpenAI-compatible request/response models
- `StreamResponse`/`StreamChoice`: Streaming response format models
- `ModelInfo`/`ModelList`: Model listing endpoint models

### Authentication Flow

1. Client sends request with Bearer token in Authorization header
2. Proxy validates client API key against `client_api_keys.json`
3. Proxy rotates through Vertical Studio tokens from `vertical.txt`
4. Backend requests are made with selected Vertical token

### Conversation Management

- Fingerprint-based message comparison for cache hits
- System prompt hashing for conversation grouping
- LRU eviction with configurable max size (`CONVERSATION_CACHE_MAX_SIZE`)
- Thread-safe cache operations with locking

### Stream Processing

- Parses Vertical API's custom streaming format (`0:"content"`, `g:"reasoning"`, `d:event`)
- Converts to OpenAI Server-Sent Events format
- Handles both reasoning and final content streams
- Supports both streaming and non-streaming response modes

## Configuration Notes

- Missing `vertical_client` module is imported but not found in codebase
- Application creates example `client_api_keys.json` if missing on startup
- Token rotation is thread-safe for concurrent requests
- Model variants with `-thinking` suffix expose reasoning steps

## API Endpoints

- `GET /v1/models` - List available models
- `POST /v1/chat/completions` - Create chat completions (OpenAI compatible)