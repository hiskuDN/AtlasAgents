"""Model router for LLM integration."""

import os
import json
from typing import Dict, Any, Optional, List
from enum import Enum
import logging
import ollama
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    """Supported model providers."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class ModelConfig:
    """Configuration for a model."""
    provider: ModelProvider
    model_name: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    options: Dict[str, Any] = None


class ModelRouter:
    """Routes requests to appropriate LLM providers."""

    def __init__(self, default_provider: ModelProvider = ModelProvider.OLLAMA):
        """Initialize the model router.

        Args:
            default_provider: Default provider to use
        """
        self.default_provider = default_provider
        self.clients = {}
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize available LLM clients."""
        # Initialize Ollama client
        try:
            # Get Ollama host from environment variable or use default
            ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
            # Create client with timeout
            import httpx
            timeout = httpx.Timeout(
                timeout=300.0,  # 5 minutes total timeout
                connect=10.0,   # 10 seconds to connect
                read=60.0       # 60 seconds per read chunk
            )
            self.clients[ModelProvider.OLLAMA] = ollama.Client(
                host=ollama_host,
                timeout=timeout
            )
            # Test connection with short timeout
            test_client = ollama.Client(host=ollama_host, timeout=5.0)
            test_client.list()
            logger.info("Ollama client initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Ollama client: {e}")

    def generate(
        self,
        prompt: str,
        model_config: Optional[ModelConfig] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> str:
        """Generate text using specified model.

        Args:
            prompt: The prompt to generate from
            model_config: Model configuration
            system_prompt: Override system prompt
            temperature: Override temperature
            max_tokens: Override max tokens
            stream: Whether to stream response

        Returns:
            Generated text
        """
        if not model_config:
            model_config = ModelConfig(
                provider=self.default_provider,
                model_name="phi4:latest"
            )

        provider = model_config.provider
        if provider not in self.clients:
            raise ValueError(f"Provider {provider} not available")

        # Override parameters if provided
        temp = temperature if temperature is not None else model_config.temperature
        max_tok = max_tokens if max_tokens is not None else model_config.max_tokens
        sys_prompt = system_prompt if system_prompt else model_config.system_prompt

        if provider == ModelProvider.OLLAMA:
            return self._generate_ollama(
                prompt=prompt,
                model=model_config.model_name,
                system_prompt=sys_prompt,
                temperature=temp,
                max_tokens=max_tok,
                stream=stream,
                options=model_config.options
            )
        else:
            raise NotImplementedError(f"Provider {provider} not implemented")

    def _generate_ollama(
        self,
        prompt: str,
        model: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate using Ollama.

        Args:
            prompt: The prompt
            model: Model name
            system_prompt: System prompt
            temperature: Temperature
            max_tokens: Max tokens
            stream: Whether to stream
            options: Additional options

        Returns:
            Generated text
        """

        client = self.clients[ModelProvider.OLLAMA]

        messages = []
        if system_prompt:
            messages.append({
                'role': 'system',
                'content': system_prompt
            })
        messages.append({
            'role': 'user',
            'content': prompt
        })

        # Build options
        opts = {
            'temperature': temperature,
            **(options or {})
        }
        if max_tokens:
            opts['num_predict'] = max_tokens

        try:

            import time
            start_time = time.time()

            # For long prompts, use streaming to avoid timeout
            use_stream = stream or len(prompt) > 1000

            if use_stream:
                response = client.chat(
                    model=model,
                    messages=messages,
                    options=opts,
                    stream=True
                )

                # Collect streamed response with size limit
                full_response = []
                chunk_count = 0
                total_chars = 0
                max_response_chars = 10000  # Maximum 10k characters

                for chunk in response:
                    if 'message' in chunk and 'content' in chunk['message']:
                        content = chunk['message']['content']
                        full_response.append(content)
                        chunk_count += 1
                        total_chars += len(content)


                        # Early termination if response is too long
                        if total_chars > max_response_chars:
                            logger.warning(f"Response exceeded {max_response_chars} chars, terminating early at {total_chars} chars")
                            full_response.append("\n\n[Response truncated due to length limit]")
                            break

                        # Also check time limit
                        if time.time() - start_time > 120:  # 2 minutes max
                            logger.warning(f"Response generation exceeded 2 minutes, terminating")
                            full_response.append("\n\n[Response truncated due to time limit]")
                            break

                result = ''.join(full_response)
                return result
            else:
                response = client.chat(
                    model=model,
                    messages=messages,
                    options=opts,
                    stream=False
                )

                result = response['message']['content']
                return result

        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

            # Check for specific error types
            if "timeout" in str(e).lower():
                raise TimeoutError(f"LLM request timed out: {e}")
            elif "connection" in str(e).lower():
                raise ConnectionError(f"Failed to connect to Ollama: {e}")
            else:
                raise RuntimeError(f"LLM generation failed: {e}")

    def list_models(self, provider: Optional[ModelProvider] = None) -> List[str]:
        """List available models.

        Args:
            provider: Provider to list models from

        Returns:
            List of model names
        """
        provider = provider or self.default_provider

        if provider == ModelProvider.OLLAMA:
            try:
                client = self.clients[ModelProvider.OLLAMA]
                models_response = client.list()
                # The ollama library returns model objects directly
                return [model.model for model in models_response['models']]
            except Exception as e:
                logger.error(f"Failed to list Ollama models: {e}")
                return []
        else:
            return []

    def test_connection(self, provider: Optional[ModelProvider] = None) -> bool:
        """Test connection to provider.

        Args:
            provider: Provider to test

        Returns:
            True if connection successful
        """
        provider = provider or self.default_provider

        if provider == ModelProvider.OLLAMA:
            try:
                client = self.clients[ModelProvider.OLLAMA]
                client.list()
                return True
            except:
                return False
        else:
            return False