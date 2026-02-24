#!/usr/bin/env python3
"""
HeartGuard AI - Local MedGemma API Server
Runs MedGemma 4B locally and exposes a simple HTTP API for the processor.
"""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger('medgemma-server')

MODEL_NAME = "google/medgemma-1.5-4b-it"
PORT = 8888

# Global model references
tokenizer = None
model = None
generate_lock = threading.Lock()


import os

def load_model():
    global tokenizer, model
    logger.info(f"Loading {MODEL_NAME} (bfloat16, full precision)...")
    hf_token = os.environ.get('HF_TOKEN')
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, token=hf_token)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        dtype=torch.bfloat16,
        device_map="auto",
        token=hf_token
    )
    logger.info("Model loaded successfully!")
    logger.info(f"GPU memory used: {torch.cuda.memory_allocated() / 1e9:.1f} GB")


def generate(prompt, max_tokens: int = 512, temperature: float = 0.3) -> str:
    with generate_lock:
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = prompt
            
        inputs = tokenizer.apply_chat_template(
            messages, return_tensors="pt", return_dict=True, add_generation_prompt=True
        )
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                do_sample=True,
            )

        response = tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )
        return response


class MedGemmaHandler(BaseHTTPRequestHandler):
    # Increase timeout for slow generation
    timeout = 300

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
            
            if self.path == '/chat':
                # Handle interactive chat requests
                prompt = data.get('prompt', '')
                history = data.get('history', [])
                
                # Build conversational messages natively for Gemma
                messages = []
                system_prefix = "You are an intelligent cardiology assistant. Answer the doctor's question concisely.\n\n"
                
                for idx, msg in enumerate(history):
                    role = "user" if msg["role"] == "user" else "model"
                    content = msg["content"]
                    if idx == 0 and role == "user":
                        content = system_prefix + content
                    messages.append({"role": role, "content": content})
                
                current_content = prompt
                if len(messages) == 0:
                    current_content = system_prefix + current_content
                
                messages.append({"role": "user", "content": current_content})
                
                logger.info(f"Chat request received. Context length: {len(history)} messages")
                response_text = generate(messages, max_tokens=1024, temperature=0.5)
                result = json.dumps({'generated_text': response_text})
                
            else:
                # Default /generate path (for the streaming pipeline)
                prompt = data.get('prompt', '')
                max_tokens = data.get('max_tokens', 512)
                temperature = data.get('temperature', 0.3)
    
                logger.info(f"Generating response (max_tokens={max_tokens})...")
                response_text = generate(prompt, max_tokens, temperature)
                logger.info(f"Generated {len(response_text)} chars")
                result = json.dumps({'generated_text': response_text})

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(result.encode())))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(result.encode())
            self.wfile.flush()

        except BrokenPipeError:
            logger.warning("Client disconnected before response was sent")
        except Exception as e:
            logger.error(f"Error: {e}")
            try:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            except BrokenPipeError:
                pass

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'model': MODEL_NAME}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default logging


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    load_model()
    server = ThreadedHTTPServer(('0.0.0.0', PORT), MedGemmaHandler)
    logger.info(f"MedGemma server running on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()
