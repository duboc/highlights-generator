"""
 Copyright 2024 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""

import os
import json
import logging
from typing import Optional, List, Union, Dict, Tuple
from dataclasses import dataclass
from tenacity import retry, stop_after_attempt, wait_exponential
from google import genai
from google.genai import types
import tiktoken
import re
from dotenv import load_dotenv

@dataclass
class TokenCount:
    """Token count information for a response."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class GeminiClient:
    """A client for interacting with Gemini API with region fallback capabilities."""
    
    def __init__(self, project_id: Optional[str] = None, logger: Optional[logging.Logger] = None):
        """
        Initialize the GeminiClient.
        
        Args:
            project_id (str, optional): Google Cloud Project ID. If None, will try to get from environment.
            logger (logging.Logger, optional): Custom logger instance. If None, will create a new one.
        """
        load_dotenv()  # Load environment variables from .env file
        self.project_id = project_id or os.environ.get("GCP_PROJECT")
        if not self.project_id:
            raise ValueError("Project ID must be provided or set in GCP_PROJECT environment variable in .env file")
            
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize tokenizer
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding, close to Gemini
        except Exception as e:
            self.logger.warning(f"Failed to initialize tokenizer: {str(e)}")
            self.tokenizer = None
        
        # List of regions to try
        self.regions = [
            "us-central1",
            "europe-west2",
            "europe-west3", 
            "asia-northeast1",
            "australia-southeast1",
            "asia-south1"
        ]
        
        # Default safety settings
        self.safety_settings = [
            types.SafetySetting(
                category="HARM_CATEGORY_HATE_SPEECH",
                threshold="OFF"
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_DANGEROUS_CONTENT",
                threshold="OFF"
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                threshold="OFF"
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_HARASSMENT",
                threshold="OFF"
            )
        ]
        
        # Default generation config
        self.default_generation_config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            max_output_tokens=8192,
            response_modalities=["TEXT"],
            safety_settings=self.safety_settings
        )

    def _initialize_client(self, region: str):
        """Initialize Gemini client with the specified region."""
        return genai.Client(
            vertexai=True,
            project=self.project_id,
            location=region
        )

    def count_tokens(self, contents: List[types.Content]) -> TokenCount:
        """
        Count tokens in the input contents.
        
        Args:
            contents: List of Content objects to count tokens for
            
        Returns:
            TokenCount: Object containing token count information
            
        Raises:
            Exception: If token counting fails
        """
        try:
            if not self.tokenizer:
                raise ValueError("Tokenizer not initialized. Install tiktoken package.")
            
            # Extract text from contents
            total_text = ""
            for content in contents:
                for part in content.parts:
                    if hasattr(part, 'text'):
                        total_text += part.text + " "
            
            # Count tokens
            token_count = len(self.tokenizer.encode(total_text))
            
            return TokenCount(
                prompt_tokens=token_count,
                completion_tokens=0,  # Will be updated after generation
                total_tokens=token_count
            )
        except Exception as e:
            self.logger.error(f"Token counting failed: {str(e)}")
            raise

    def _parse_response(self, response) -> Dict:
        """Parse response into a structured dictionary."""
        if hasattr(response, 'text'):
            try:
                # Clean up the text
                text = response.text.strip()
                
                # Handle markdown code blocks
                if '```json' in text:
                    # Extract JSON from code block
                    start = text.find('```json') + 7
                    end = text.find('```', start)
                    if end != -1:
                        text = text[start:end].strip()
                
                # Try to parse as JSON
                if text.startswith('{') and text.endswith('}'):
                    return json.loads(text)
                elif text.startswith('[') and text.endswith(']'):
                    return json.loads(text)
                
                # If text contains embedded JSON object/array, try to extract it
                json_pattern = r'\{[^{}]*\}|\[[^\[\]]*\]'
                matches = re.finditer(json_pattern, text)
                for match in matches:
                    try:
                        return json.loads(match.group())
                    except json.JSONDecodeError:
                        continue
            except json.JSONDecodeError:
                pass
            except Exception as e:
                self.logger.warning(f"JSON parsing failed: {str(e)}")
            
            # Return as regular text if not JSON
            return {"text": response.text}
        return {"text": str(response)}

    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    def generate_content(self, 
                        contents: List[types.Content],
                        stream: bool = False,
                        generation_config: Optional[types.GenerateContentConfig] = None,
                        model: str = "gemini-2.0-flash-exp",
                        return_json: bool = False,
                        json_schema: Optional[Dict] = None,
                        count_tokens: bool = False) -> Union[str, Dict, Tuple[Union[str, Dict], TokenCount]]:
        """
        Generate content using Gemini model with region fallback.
        
        Args:
            contents: List of Content objects containing the prompt
            stream: Whether to stream the response
            generation_config: Optional custom generation config
            model: Model name to use
            return_json: Whether to return response as JSON using SDK's JSON capability
            json_schema: Optional JSON schema for structured responses
            count_tokens: Whether to count tokens and return token usage
            
        Returns:
            Union[str, Dict]: Generated content as string or JSON if return_json=True
            If count_tokens=True, returns a tuple of (content, TokenCount)
            
        Raises:
            Exception: If all regions fail
        """
        last_error = None
        gen_config = generation_config or self.default_generation_config
        token_count = None
        
        if return_json:
            if not json_schema:
                json_schema = {"type": "OBJECT", "properties": {"response": {"type": "STRING"}}}
            gen_config.response_mime_type = "application/json"
            gen_config.response_schema = json_schema

        if count_tokens:
            token_count = self.count_tokens(contents)

        for region in self.regions:
            try:
                client = self._initialize_client(region)
                
                if stream:
                    response = client.models.generate_content_stream(
                        model=model,
                        contents=contents,
                        config=gen_config
                    )
                    if count_tokens:
                        # Update token count with completion tokens
                        token_count.completion_tokens = sum(len(chunk.text.split()) for chunk in response)
                        token_count.total_tokens = token_count.prompt_tokens + token_count.completion_tokens
                    return (response, token_count) if count_tokens else response
                else:
                    response = client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=gen_config
                    )
                    
                    if count_tokens:
                        # Update token count with completion tokens
                        token_count.completion_tokens = len(response.text.split())
                        token_count.total_tokens = token_count.prompt_tokens + token_count.completion_tokens
                    
                    result = response.text
                    return (result, token_count) if count_tokens else result
                    
            except Exception as e:
                self.logger.warning(f"Error with region {region}: {str(e)}")
                last_error = e
                continue
        
        raise Exception(f"All regions failed. Last error: {str(last_error)}") from last_error

def example_usage():
    """Example usage of the GeminiClient"""
    client = GeminiClient()
    
    # Prepare the prompt
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text("Tell me a short story about a robot.")]
        )
    ]
    
    # Generate content
    try:
        # Non-streaming response
        response = client.generate_content(contents)
        print("Regular response:", response)
        
        # Streaming response
        stream = client.generate_content(contents, stream=True)
        print("\nStreaming response:")
        for chunk in stream:
            print(chunk, end="")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    example_usage()